"""Garmin Connect sync engine, rate-limiter, and SQLite cache warmer for FORGE."""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Ensure garmin_mcp src/ is importable
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from garminconnect import Garmin
from garmin_mcp import init_api, load_credentials

from .db import DEFAULT_DB_PATH, get_conn, log_sync_run, utcnow_iso

_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional[Garmin] = None

_SYNC_LOCK = threading.Lock()
_SYNC_STATE: Dict[str, Any] = {
    "running": False,
    "scope": None,
    "progress": 0,
    "total": 0,
    "current_step": "idle",
    "last_sync_at": None,
    "last_error": None,
    "consecutive_failures": 0,
    "circuit_open": False,
}


def get_sync_state() -> Dict[str, Any]:
    return dict(_SYNC_STATE)


_CLIENTS: Dict[str, Garmin] = {}


def get_garmin_client(force_reinit: bool = False, token_dir: Optional[Path] = None) -> Garmin:
    """Return an authenticated Garmin client for the active (or specified) account's token_dir."""
    from dashboard.api.accounts import get_active_account

    acc = get_active_account()
    t_dir = (token_dir or acc.token_dir).expanduser()
    key = str(t_dir)
    with _CLIENT_LOCK:
        if key in _CLIENTS and not force_reinit:
            return _CLIENTS[key]
        client = Garmin()
        if t_dir.exists() and any(p.name != "account_meta.json" for p in t_dir.glob("*.json")):
            client.login(str(t_dir))
            _CLIENTS[key] = client
            return client
        email, password = load_credentials()
        if email and password:
            fallback = init_api(email, password)
            if fallback is not None:
                _CLIENTS[key] = fallback
                return fallback
        raise RuntimeError(
            "Garmin account is not authenticated yet. Please sign in from the sidebar."
        )


def format_duration_sec(seconds: Optional[float]) -> str:
    if seconds is None or seconds <= 0:
        return "0:00"
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_pace(duration_sec: Optional[float], distance_m: Optional[float]) -> Optional[str]:
    if not duration_sec or not distance_m or distance_m <= 10:
        return None
    sec_per_km = duration_sec / (distance_m / 1000.0)
    if sec_per_km <= 0 or sec_per_km > 3600:
        return None
    mins = int(sec_per_km // 60)
    secs = int(round(sec_per_km % 60))
    if secs == 60:
        mins += 1
        secs = 0
    return f"{mins}:{secs:02d} /km"


def _timed_call(
    conn,
    scope: str,
    endpoint: str,
    fn: Callable[..., Any],
    *args: Any,
    default: Any = None,
    **kwargs: Any,
) -> Any:
    """Execute a Garmin API call, measure latency, and log into sync_runs."""
    started = utcnow_iso()
    t0 = time.monotonic()
    try:
        res = fn(*args, **kwargs)
        latency_ms = int((time.monotonic() - t0) * 1000)
        ended = utcnow_iso()
        count = len(res) if isinstance(res, list) else (1 if res else 0)
        log_sync_run(conn, started, ended, scope, endpoint, "ok", count, latency_ms)
        _SYNC_STATE["consecutive_failures"] = 0
        _SYNC_STATE["circuit_open"] = False
        return default if res is None else res
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        ended = utcnow_iso()
        err_msg = str(exc)[:400]
        log_sync_run(conn, started, ended, scope, endpoint, "error", 0, latency_ms, err_msg)
        _SYNC_STATE["consecutive_failures"] += 1
        if _SYNC_STATE["consecutive_failures"] >= 5:
            _SYNC_STATE["circuit_open"] = True
        _SYNC_STATE["last_error"] = f"{endpoint}: {err_msg}"
        return default


def _save_raw(conn, source_key: str, entity_key: str, payload: Any) -> None:
    if payload is None:
        return
    conn.execute(
        """
        INSERT INTO raw_payloads (source_key, entity_key, payload_json, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source_key, entity_key) DO UPDATE SET
            payload_json=excluded.payload_json,
            fetched_at=excluded.fetched_at
        """,
        (source_key, str(entity_key), json.dumps(payload, default=str), utcnow_iso()),
    )


def _extract_hr_zones(client: Garmin, conn, scope: str) -> Any:
    """Fetch Garmin HR zone configs across sports via connectapi."""
    return _timed_call(
        conn,
        scope,
        "hr_zones",
        client.connectapi,
        "/biometric-service/heartRateZones",
        default=[],
    )


def sync_profile_and_benchmarks(
    client: Garmin,
    conn,
    scope: str = "incremental",
    today: Optional[date] = None,
) -> None:
    today = today or datetime.now().date()
    today_s = today.isoformat()
    start_30 = (today - timedelta(days=30)).isoformat()
    start_90 = (today - timedelta(days=90)).isoformat()

    full_name = _timed_call(conn, scope, "get_full_name", client.get_full_name, default="Athlete")
    profile_raw = _timed_call(conn, scope, "get_user_profile", client.get_user_profile, default={})
    devices_raw = _timed_call(conn, scope, "get_devices", client.get_devices, default=[])
    hr_zones_raw = _extract_hr_zones(client, conn, scope)
    race_raw = _timed_call(conn, scope, "get_race_predictions", client.get_race_predictions, default={})
    prs_raw = _timed_call(conn, scope, "get_personal_record", client.get_personal_record, default=[])
    badges_raw = _timed_call(conn, scope, "get_earned_badges", client.get_earned_badges, default=[])
    fitness_age_raw = _timed_call(conn, scope, "get_fitnessage_data", client.get_fitnessage_data, today_s, default={})
    lactate_raw = _timed_call(conn, scope, "get_lactate_threshold", client.get_lactate_threshold, default={})
    endurance_raw = _timed_call(conn, scope, "get_endurance_score", client.get_endurance_score, start_30, today_s, default={})
    hill_raw = _timed_call(conn, scope, "get_hill_score", client.get_hill_score, start_30, today_s, default={})
    body_comp_raw = _timed_call(conn, scope, "get_body_composition", client.get_body_composition, start_90, today_s, default={})

    _save_raw(conn, "user_profile", "profile", profile_raw)
    _save_raw(conn, "devices", "devices", devices_raw)
    _save_raw(conn, "hr_zones", "all", hr_zones_raw)
    _save_raw(conn, "race_predictions", today_s, race_raw)
    _save_raw(conn, "personal_records", today_s, prs_raw)
    _save_raw(conn, "badges", today_s, badges_raw)
    _save_raw(conn, "fitness_age", today_s, fitness_age_raw)
    _save_raw(conn, "lactate_threshold", today_s, lactate_raw)
    _save_raw(conn, "endurance_score", today_s, endurance_raw)
    _save_raw(conn, "hill_score", today_s, hill_raw)
    _save_raw(conn, "body_composition", today_s, body_comp_raw)

    user_data = (profile_raw or {}).get("userData") or {}
    weight_g = user_data.get("weight")
    height_cm = user_data.get("height")
    lt_speed = user_data.get("lactateThresholdSpeed")
    lt_pace = None
    if lt_speed and lt_speed > 0:
        speed_mps = lt_speed * 10.0 if lt_speed < 1.0 else lt_speed
        lt_pace = format_pace(1000.0, speed_mps * 1000.0)

    lt_power = None
    if isinstance(lactate_raw, dict):
        lt_power = (lactate_raw.get("power") or {}).get("functionalThresholdPower")

    primary_device = "Forerunner 965"
    for dev in devices_raw or []:
        if isinstance(dev, dict):
            name = dev.get("productDisplayName") or dev.get("deviceName") or dev.get("applicationKey")
            if name:
                primary_device = name
                break

    conn.execute(
        """
        INSERT INTO athlete_profile (
            id, full_name, device_name, gender, birth_date, height_cm, weight_kg,
            vo2_max_running, lactate_threshold_hr, lactate_threshold_pace, lactate_threshold_power,
            unit_system, profile_json, hr_zones_json, race_predictions_json,
            personal_records_json, badges_json, fitness_age_json, endurance_json, hill_json, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            full_name=excluded.full_name,
            device_name=excluded.device_name,
            gender=excluded.gender,
            birth_date=excluded.birth_date,
            height_cm=excluded.height_cm,
            weight_kg=excluded.weight_kg,
            vo2_max_running=excluded.vo2_max_running,
            lactate_threshold_hr=excluded.lactate_threshold_hr,
            lactate_threshold_pace=excluded.lactate_threshold_pace,
            lactate_threshold_power=excluded.lactate_threshold_power,
            unit_system=excluded.unit_system,
            profile_json=excluded.profile_json,
            hr_zones_json=excluded.hr_zones_json,
            race_predictions_json=excluded.race_predictions_json,
            personal_records_json=excluded.personal_records_json,
            badges_json=excluded.badges_json,
            fitness_age_json=excluded.fitness_age_json,
            endurance_json=excluded.endurance_json,
            hill_json=excluded.hill_json,
            updated_at=excluded.updated_at
        """,
        (
            full_name or "Athlete",
            primary_device,
            user_data.get("gender"),
            user_data.get("birthDate"),
            round(float(height_cm), 1) if height_cm else None,
            round(float(weight_g) / 1000.0, 2) if weight_g else None,
            user_data.get("vo2MaxRunning"),
            user_data.get("lactateThresholdHeartRate"),
            lt_pace,
            lt_power,
            user_data.get("measurementSystem") or "metric",
            json.dumps(profile_raw, default=str),
            json.dumps(hr_zones_raw, default=str),
            json.dumps(race_raw, default=str),
            json.dumps(prs_raw, default=str),
            json.dumps(badges_raw, default=str),
            json.dumps(fitness_age_raw, default=str),
            json.dumps(endurance_raw, default=str),
            json.dumps(hill_raw, default=str),
            utcnow_iso(),
        ),
    )

    # Ingest Garmin body composition weigh-ins if not already stored
    for entry in (body_comp_raw or {}).get("dateWeightList") or []:
        cdate = entry.get("calendarDate")
        w_g = entry.get("weight")
        if not cdate or not w_g:
            continue
        w_kg = round(float(w_g) / 1000.0, 2)
        bf = entry.get("bodyFat")
        src = entry.get("sourceType") or "GARMIN"
        ts_ms = entry.get("timestampGMT")
        rec_at = (
            datetime.fromtimestamp(ts_ms / 1000.0).isoformat(timespec="seconds")
            if ts_ms
            else f"{cdate}T08:00:00"
        )
        exists = conn.execute(
            "SELECT id FROM body_measurements WHERE calendar_date=? AND ABS(weight_kg - ?) < 0.05",
            (cdate, w_kg),
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO body_measurements
                (calendar_date, recorded_at, weight_kg, body_fat_pct, body_fat_source, source, synced_to_garmin)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (cdate, rec_at, w_kg, bf, src if bf is not None else None, f"garmin:{src}"),
            )


def _upsert_activity_row(conn, a: Dict[str, Any]) -> int:
    aid = int(a["activityId"])
    type_key = (a.get("activityType") or {}).get("typeKey") or "other"
    event_key = (a.get("eventType") or {}).get("typeKey") or "uncategorized"
    start_local = a.get("startTimeLocal") or ""
    cal_date = start_local[:10] if len(start_local) >= 10 else ""

    existing = conn.execute(
        "SELECT sets_fetched FROM activities WHERE activity_id = ?", (aid,)
    ).fetchone()
    sets_fetched = existing["sets_fetched"] if existing else 0

    conn.execute(
        """
        INSERT INTO activities (
            activity_id, name, type, event_type, start_time_local, calendar_date,
            duration_s, moving_duration_s, distance_m, calories, avg_hr, max_hr,
            te_aerobic, te_anaerobic, te_label, training_load, avg_cadence, avg_power,
            norm_power, avg_stride_cm, avg_gct_ms, avg_vo_cm, elevation_gain,
            vo2_max, bb_impact, rpe, feel,
            hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s, has_splits, sets_fetched, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(activity_id) DO UPDATE SET
            name=excluded.name,
            type=excluded.type,
            event_type=excluded.event_type,
            start_time_local=excluded.start_time_local,
            calendar_date=excluded.calendar_date,
            duration_s=excluded.duration_s,
            moving_duration_s=excluded.moving_duration_s,
            distance_m=excluded.distance_m,
            calories=excluded.calories,
            avg_hr=excluded.avg_hr,
            max_hr=excluded.max_hr,
            te_aerobic=excluded.te_aerobic,
            te_anaerobic=excluded.te_anaerobic,
            te_label=excluded.te_label,
            training_load=excluded.training_load,
            avg_cadence=excluded.avg_cadence,
            avg_power=excluded.avg_power,
            norm_power=excluded.norm_power,
            avg_stride_cm=excluded.avg_stride_cm,
            avg_gct_ms=excluded.avg_gct_ms,
            avg_vo_cm=excluded.avg_vo_cm,
            elevation_gain=excluded.elevation_gain,
            vo2_max=excluded.vo2_max,
            bb_impact=excluded.bb_impact,
            rpe=COALESCE(excluded.rpe, activities.rpe),
            feel=COALESCE(excluded.feel, activities.feel),
            hr_z1_s=excluded.hr_z1_s,
            hr_z2_s=excluded.hr_z2_s,
            hr_z3_s=excluded.hr_z3_s,
            hr_z4_s=excluded.hr_z4_s,
            hr_z5_s=excluded.hr_z5_s,
            has_splits=excluded.has_splits,
            raw_json=excluded.raw_json
        """,
        (
            aid,
            a.get("activityName") or "Workout",
            type_key,
            event_key,
            start_local,
            cal_date,
            a.get("duration") or 0.0,
            a.get("movingDuration") or 0.0,
            a.get("distance") or 0.0,
            a.get("calories") or 0.0,
            a.get("averageHR"),
            a.get("maxHR"),
            a.get("aerobicTrainingEffect") or 0.0,
            a.get("anaerobicTrainingEffect") or 0.0,
            a.get("trainingEffectLabel"),
            a.get("activityTrainingLoad") or 0.0,
            a.get("averageRunningCadenceInStepsPerMinute"),
            a.get("avgPower"),
            a.get("normPower"),
            a.get("avgStrideLength"),
            a.get("avgGroundContactTime"),
            a.get("avgVerticalOscillation"),
            a.get("elevationGain") or 0.0,
            a.get("vO2MaxValue"),
            a.get("differenceBodyBattery"),
            a.get("workoutRpe"),
            a.get("workoutFeel"),
            a.get("hrTimeInZone_1") or 0.0,
            a.get("hrTimeInZone_2") or 0.0,
            a.get("hrTimeInZone_3") or 0.0,
            a.get("hrTimeInZone_4") or 0.0,
            a.get("hrTimeInZone_5") or 0.0,
            1 if a.get("hasSplits") else 0,
            sets_fetched,
            json.dumps(a, default=str),
        ),
    )
    return aid


def sync_exercise_sets_for_activity(
    client: Garmin,
    conn,
    activity_id: int,
    scope: str = "incremental",
    preserve_user_edits: bool = True,
) -> int:
    raw = _timed_call(
        conn,
        scope,
        "get_activity_exercise_sets",
        client.get_activity_exercise_sets,
        activity_id,
        default={},
    )
    if not isinstance(raw, dict):
        return 0
    _save_raw(conn, "exercise_sets", str(activity_id), raw)
    sets_list = raw.get("exerciseSets") or []

    # Preserve local user corrections if requested
    existing_corrected: Dict[int, sqlite3.Row] = {}
    if preserve_user_edits:
        rows = conn.execute(
            "SELECT * FROM exercise_sets WHERE activity_id = ? AND user_corrected = 1",
            (activity_id,),
        ).fetchall()
        for r in rows:
            existing_corrected[int(r["set_index"])] = r

    conn.execute("DELETE FROM exercise_sets WHERE activity_id = ?", (activity_id,))
    written = 0
    for idx, s in enumerate(sets_list):
        set_type = s.get("setType") or "ACTIVE"
        ex_list = s.get("exercises") or []
        top_ex = ex_list[0] if ex_list else {}
        cat = (top_ex.get("category") or ("REST" if set_type == "REST" else "UNKNOWN")).upper()
        ex_name = top_ex.get("name")
        prob = top_ex.get("probability")
        reps = s.get("repetitionCount")
        raw_w = s.get("weight")
        weight_kg = round(float(raw_w) / 1000.0, 2) if (raw_w is not None and float(raw_w) > 0) else 0.0
        dur_s = s.get("duration")

        rest_s = None
        if set_type == "ACTIVE" and idx + 1 < len(sets_list):
            nxt = sets_list[idx + 1]
            if nxt.get("setType") == "REST":
                rest_s = nxt.get("duration")

        # Restore local override if present
        user_corr = 0
        orig_cat, orig_name, orig_reps, orig_w = cat, ex_name, reps, weight_kg
        if idx in existing_corrected:
            c_row = existing_corrected[idx]
            cat = c_row["category"]
            ex_name = c_row["exercise_name"]
            reps = c_row["reps"]
            weight_kg = c_row["weight_kg"]
            user_corr = 1

        conn.execute(
            """
            INSERT INTO exercise_sets (
                activity_id, set_index, set_type, category, exercise_name, probability,
                reps, weight_kg, duration_s, rest_s, start_time, user_corrected,
                orig_category, orig_exercise_name, orig_reps, orig_weight_kg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                activity_id,
                idx,
                set_type,
                cat,
                ex_name,
                prob,
                reps,
                weight_kg,
                dur_s,
                rest_s,
                s.get("startTime"),
                user_corr,
                orig_cat,
                orig_name,
                orig_reps,
                orig_w,
            ),
        )
        written += 1

    conn.execute("UPDATE activities SET sets_fetched = 1 WHERE activity_id = ?", (activity_id,))
    return written


def sync_activities(
    client: Garmin,
    conn,
    limit: int = 100,
    scope: str = "incremental",
    refresh_sets_days: int = 7,
) -> int:
    acts = _timed_call(conn, scope, "get_activities", client.get_activities, 0, min(limit, 100), default=[])
    if not isinstance(acts, list):
        return 0
    _save_raw(conn, "activities_list", f"0_{limit}", acts)

    cutoff = (datetime.now().date() - timedelta(days=refresh_sets_days)).isoformat()
    strength_to_fetch: List[int] = []

    for a in acts:
        if not isinstance(a, dict) or not a.get("activityId"):
            continue
        aid = _upsert_activity_row(conn, a)
        type_key = (a.get("activityType") or {}).get("typeKey") or ""
        cal_date = (a.get("startTimeLocal") or "")[:10]
        if type_key == "strength_training":
            row = conn.execute(
                "SELECT sets_fetched FROM activities WHERE activity_id = ?", (aid,)
            ).fetchone()
            if not row or not row["sets_fetched"] or cal_date >= cutoff:
                strength_to_fetch.append(aid)

    for aid in strength_to_fetch:
        if _SYNC_STATE["circuit_open"]:
            break
        sync_exercise_sets_for_activity(client, conn, aid, scope=scope)
        time.sleep(0.15)

    return len(acts)


def _extract_training_status_fields(status_raw: Any) -> Dict[str, Any]:
    if not isinstance(status_raw, dict) or not status_raw:
        return {}
    recent = status_raw.get("mostRecentTrainingStatus") or {}
    latest_map = recent.get("latestTrainingStatusData") or {}
    dev_data: Dict[str, Any] = {}
    for _, val in latest_map.items():
        if isinstance(val, dict) and val:
            dev_data = val
            if val.get("primaryTrainingDevice"):
                break
    acwr_dto = dev_data.get("acuteTrainingLoadDTO") or {}

    vo2_generic = ((status_raw.get("mostRecentVO2Max") or {}).get("generic") or {})
    load_bal_map = (
        (status_raw.get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap")
        or {}
    )
    load_data: Dict[str, Any] = {}
    for _, val in load_bal_map.items():
        if isinstance(val, dict) and val:
            load_data = val
            break

    return {
        "training_status": dev_data.get("trainingStatusFeedbackPhrase"),
        "acute_load": acwr_dto.get("dailyTrainingLoadAcute"),
        "chronic_load": acwr_dto.get("dailyTrainingLoadChronic"),
        "acwr": acwr_dto.get("dailyAcuteChronicWorkloadRatio"),
        "acwr_status": acwr_dto.get("acwrStatus"),
        "acwr_percent": acwr_dto.get("acwrPercent"),
        "vo2_max": vo2_generic.get("vo2MaxPreciseValue") or vo2_generic.get("vo2MaxValue"),
        "load_aerobic_low": load_data.get("monthlyLoadAerobicLow"),
        "load_aerobic_high": load_data.get("monthlyLoadAerobicHigh"),
        "load_anaerobic": load_data.get("monthlyLoadAnaerobic"),
        "load_balance_feedback": load_data.get("trainingBalanceFeedbackPhrase"),
    }


def sync_daily_window(
    client: Garmin,
    conn,
    start_date: date,
    end_date: date,
    scope: str = "incremental",
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    """Sync daily wellness, sleep, HRV, readiness, training status, hydration, and body battery."""
    s_str = start_date.isoformat()
    e_str = end_date.isoformat()

    bb_list = _timed_call(conn, scope, "get_body_battery", client.get_body_battery, s_str, e_str, default=[])
    bb_map: Dict[str, Dict[str, Any]] = {}
    if isinstance(bb_list, list):
        for item in bb_list:
            if isinstance(item, dict) and item.get("date"):
                bb_map[item["date"]] = item

    # Sync newest dates first so Today / 7D / 14D telemetry populates within seconds
    dates = [end_date - timedelta(days=i) for i in range((end_date - start_date).days + 1)]
    total = len(dates)
    written = 0

    for idx, d in enumerate(dates):
        if _SYNC_STATE["circuit_open"]:
            break
        ds = d.isoformat()
        if progress_cb:
            progress_cb(idx + 1, total, f"Syncing {ds}")

        summary = _timed_call(conn, scope, "get_user_summary", client.get_user_summary, ds, default={}) or {}
        sleep_raw = _timed_call(conn, scope, "get_sleep_data", client.get_sleep_data, ds, default={}) or {}
        hrv_raw = _timed_call(conn, scope, "get_hrv_data", client.get_hrv_data, ds, default={}) or {}
        hydration = _timed_call(conn, scope, "get_hydration_data", client.get_hydration_data, ds, default={}) or {}
        resp = _timed_call(conn, scope, "get_respiration_data", client.get_respiration_data, ds, default={}) or {}
        readiness_list = _timed_call(conn, scope, "get_training_readiness", client.get_training_readiness, ds, default=[]) or []
        status_raw = _timed_call(conn, scope, "get_training_status", client.get_training_status, ds, default={}) or {}

        _save_raw(conn, "user_summary", ds, summary)
        if sleep_raw:
            _save_raw(conn, "sleep_data", ds, sleep_raw)
        if hrv_raw:
            _save_raw(conn, "hrv_data", ds, hrv_raw)
        if readiness_list:
            _save_raw(conn, "training_readiness", ds, readiness_list)

        sleep_dto = (sleep_raw.get("dailySleepDTO") or {}) if isinstance(sleep_raw, dict) else {}
        hrv_sum = (hrv_raw.get("hrvSummary") or {}) if isinstance(hrv_raw, dict) else {}
        sleep_scores = sleep_dto.get("sleepScores") or {}
        overall_sleep = sleep_scores.get("overall") or {}

        bb_entry = bb_map.get(ds) or {}
        bb_vals = [
            item[1]
            for item in (bb_entry.get("bodyBatteryValuesArray") or [])
            if isinstance(item, (list, tuple)) and len(item) >= 2 and item[1] is not None
        ]
        bb_peak = max(bb_vals) if bb_vals else summary.get("bodyBatteryHighestValue")
        bb_low = min(bb_vals) if bb_vals else summary.get("bodyBatteryLowestValue")
        bb_charged = bb_entry.get("charged") if bb_entry.get("charged") is not None else summary.get("bodyBatteryChargedValue")
        bb_drained = bb_entry.get("drained") if bb_entry.get("drained") is not None else summary.get("bodyBatteryDrainedValue")

        # Readiness entries (multiple intraday resets possible!)
        latest_r: Dict[str, Any] = {}
        if isinstance(readiness_list, list) and readiness_list:
            # Garmin returns newest first or sorted by timestamp; sort chronologically
            sorted_r = sorted(
                [r for r in readiness_list if isinstance(r, dict)],
                key=lambda x: x.get("timestamp") or "",
            )
            latest_r = sorted_r[-1] if sorted_r else {}
            for r in sorted_r:
                ts_r = r.get("timestamp")
                if not ts_r:
                    continue
                rec_min = r.get("recoveryTime")
                rec_h = round(float(rec_min) / 60.0, 1) if rec_min is not None else None
                conn.execute(
                    """
                    INSERT INTO readiness_entries (
                        calendar_date, timestamp, context, score, level, feedback,
                        recovery_time_h, sleep_score, hrv_weekly_avg, acute_load, factors_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(calendar_date, timestamp) DO UPDATE SET
                        context=excluded.context,
                        score=excluded.score,
                        level=excluded.level,
                        feedback=excluded.feedback,
                        recovery_time_h=excluded.recovery_time_h,
                        sleep_score=excluded.sleep_score,
                        hrv_weekly_avg=excluded.hrv_weekly_avg,
                        acute_load=excluded.acute_load,
                        factors_json=excluded.factors_json
                    """,
                    (
                        ds,
                        ts_r,
                        r.get("inputContext"),
                        r.get("score"),
                        r.get("level"),
                        r.get("feedbackShort"),
                        rec_h,
                        r.get("sleepScore"),
                        r.get("hrvWeeklyAverage"),
                        r.get("acuteLoad"),
                        json.dumps(
                            {
                                "sleep_pct": r.get("sleepScoreFactorPercent"),
                                "sleep_fb": r.get("sleepScoreFactorFeedback"),
                                "recovery_pct": r.get("recoveryTimeFactorPercent"),
                                "recovery_fb": r.get("recoveryTimeFactorFeedback"),
                                "load_pct": r.get("acwrFactorPercent"),
                                "load_fb": r.get("acwrFactorFeedback"),
                                "hrv_pct": r.get("hrvFactorPercent"),
                                "hrv_fb": r.get("hrvFactorFeedback"),
                                "stress_pct": r.get("stressHistoryFactorPercent"),
                                "stress_fb": r.get("stressHistoryFactorFeedback"),
                                "sleep_hist_pct": r.get("sleepHistoryFactorPercent"),
                            }
                        ),
                    ),
                )

        ts_fields = _extract_training_status_fields(status_raw)
        rec_min = latest_r.get("recoveryTime")
        rec_h = round(float(rec_min) / 60.0, 1) if rec_min is not None else None

        intake_raw = hydration.get("valueInML") if isinstance(hydration, dict) else None
        intake_ml = round(float(intake_raw), 0) if intake_raw is not None else 0.0
        goal_ml = round(float((hydration or {}).get("goalInML") or 3500.0), 0)
        sweat_ml = round(float((hydration or {}).get("sweatLossInML") or 0.0), 0)

        conn.execute(
            """
            INSERT INTO daily_wellness (
                calendar_date, steps, step_goal, distance_km, active_kcal, total_kcal, bmr_kcal,
                floors, im_moderate, im_vigorous, rhr, min_hr, max_hr, stress_avg, stress_max,
                bb_charged, bb_drained, bb_peak, bb_low,
                sleep_s, nap_s, sleep_score, sleep_qualifier, deep_s, rem_s, light_s, awake_s,
                sleep_start_ms, sleep_end_ms, avg_sleep_stress,
                hrv_night, hrv_5min_high, hrv_weekly, hrv_status,
                hydration_intake_ml, hydration_goal_ml, hydration_sweat_ml,
                resp_sleep, resp_wake, spo2_avg,
                vo2_max, vo2_carried_forward, acute_load, chronic_load, acwr, acwr_status,
                acwr_percent, training_status, load_aerobic_low, load_aerobic_high,
                load_anaerobic, load_balance_feedback,
                readiness_score, readiness_level, readiness_context, readiness_recovery_h, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(calendar_date) DO UPDATE SET
                steps=excluded.steps,
                step_goal=excluded.step_goal,
                distance_km=excluded.distance_km,
                active_kcal=excluded.active_kcal,
                total_kcal=excluded.total_kcal,
                bmr_kcal=excluded.bmr_kcal,
                floors=excluded.floors,
                im_moderate=excluded.im_moderate,
                im_vigorous=excluded.im_vigorous,
                rhr=COALESCE(excluded.rhr, daily_wellness.rhr),
                min_hr=COALESCE(excluded.min_hr, daily_wellness.min_hr),
                max_hr=COALESCE(excluded.max_hr, daily_wellness.max_hr),
                stress_avg=COALESCE(excluded.stress_avg, daily_wellness.stress_avg),
                stress_max=COALESCE(excluded.stress_max, daily_wellness.stress_max),
                bb_charged=COALESCE(excluded.bb_charged, daily_wellness.bb_charged),
                bb_drained=COALESCE(excluded.bb_drained, daily_wellness.bb_drained),
                bb_peak=COALESCE(excluded.bb_peak, daily_wellness.bb_peak),
                bb_low=COALESCE(excluded.bb_low, daily_wellness.bb_low),
                sleep_s=COALESCE(excluded.sleep_s, daily_wellness.sleep_s),
                nap_s=COALESCE(excluded.nap_s, daily_wellness.nap_s),
                sleep_score=COALESCE(excluded.sleep_score, daily_wellness.sleep_score),
                sleep_qualifier=COALESCE(excluded.sleep_qualifier, daily_wellness.sleep_qualifier),
                deep_s=COALESCE(excluded.deep_s, daily_wellness.deep_s),
                rem_s=COALESCE(excluded.rem_s, daily_wellness.rem_s),
                light_s=COALESCE(excluded.light_s, daily_wellness.light_s),
                awake_s=COALESCE(excluded.awake_s, daily_wellness.awake_s),
                sleep_start_ms=COALESCE(excluded.sleep_start_ms, daily_wellness.sleep_start_ms),
                sleep_end_ms=COALESCE(excluded.sleep_end_ms, daily_wellness.sleep_end_ms),
                avg_sleep_stress=COALESCE(excluded.avg_sleep_stress, daily_wellness.avg_sleep_stress),
                hrv_night=COALESCE(excluded.hrv_night, daily_wellness.hrv_night),
                hrv_5min_high=COALESCE(excluded.hrv_5min_high, daily_wellness.hrv_5min_high),
                hrv_weekly=COALESCE(excluded.hrv_weekly, daily_wellness.hrv_weekly),
                hrv_status=COALESCE(excluded.hrv_status, daily_wellness.hrv_status),
                hydration_intake_ml=excluded.hydration_intake_ml,
                hydration_goal_ml=excluded.hydration_goal_ml,
                hydration_sweat_ml=excluded.hydration_sweat_ml,
                resp_sleep=COALESCE(excluded.resp_sleep, daily_wellness.resp_sleep),
                resp_wake=COALESCE(excluded.resp_wake, daily_wellness.resp_wake),
                spo2_avg=COALESCE(excluded.spo2_avg, daily_wellness.spo2_avg),
                vo2_max=COALESCE(excluded.vo2_max, daily_wellness.vo2_max),
                acute_load=COALESCE(excluded.acute_load, daily_wellness.acute_load),
                chronic_load=COALESCE(excluded.chronic_load, daily_wellness.chronic_load),
                acwr=COALESCE(excluded.acwr, daily_wellness.acwr),
                acwr_status=COALESCE(excluded.acwr_status, daily_wellness.acwr_status),
                acwr_percent=COALESCE(excluded.acwr_percent, daily_wellness.acwr_percent),
                training_status=COALESCE(excluded.training_status, daily_wellness.training_status),
                load_aerobic_low=COALESCE(excluded.load_aerobic_low, daily_wellness.load_aerobic_low),
                load_aerobic_high=COALESCE(excluded.load_aerobic_high, daily_wellness.load_aerobic_high),
                load_anaerobic=COALESCE(excluded.load_anaerobic, daily_wellness.load_anaerobic),
                load_balance_feedback=COALESCE(excluded.load_balance_feedback, daily_wellness.load_balance_feedback),
                readiness_score=COALESCE(excluded.readiness_score, daily_wellness.readiness_score),
                readiness_level=COALESCE(excluded.readiness_level, daily_wellness.readiness_level),
                readiness_context=COALESCE(excluded.readiness_context, daily_wellness.readiness_context),
                readiness_recovery_h=COALESCE(excluded.readiness_recovery_h, daily_wellness.readiness_recovery_h),
                updated_at=excluded.updated_at
            """,
            (
                ds,
                summary.get("totalSteps") or 0,
                summary.get("dailyStepGoal") or 10000,
                round((summary.get("totalDistanceMeters") or 0) / 1000.0, 2),
                round(summary.get("activeKilocalories") or 0.0, 0),
                round(summary.get("totalKilocalories") or 0.0, 0),
                round(summary.get("bmrKilocalories") or 0.0, 0),
                round(summary.get("floorsAscended") or 0.0, 1),
                summary.get("moderateIntensityMinutes") or 0,
                summary.get("vigorousIntensityMinutes") or 0,
                summary.get("restingHeartRate"),
                summary.get("minHeartRate"),
                summary.get("maxHeartRate"),
                summary.get("averageStressLevel"),
                summary.get("maxStressLevel"),
                bb_charged,
                bb_drained,
                bb_peak,
                bb_low,
                sleep_dto.get("sleepTimeSeconds"),
                sleep_dto.get("napTimeSeconds") or 0,
                overall_sleep.get("value"),
                overall_sleep.get("qualifierKey"),
                sleep_dto.get("deepSleepSeconds"),
                sleep_dto.get("remSleepSeconds"),
                sleep_dto.get("lightSleepSeconds"),
                sleep_dto.get("awakeSleepSeconds"),
                sleep_dto.get("sleepStartTimestampGMT"),
                sleep_dto.get("sleepEndTimestampGMT"),
                sleep_dto.get("avgSleepStress"),
                hrv_sum.get("lastNightAvg") or summary.get("avgOvernightHrv"),
                hrv_sum.get("lastNight5MinHigh"),
                hrv_sum.get("weeklyAvg"),
                hrv_sum.get("status"),
                intake_ml,
                goal_ml,
                sweat_ml,
                (resp or {}).get("avgSleepRespirationValue") or summary.get("avgSleepRespirationValue"),
                (resp or {}).get("avgWakingRespirationValue") or summary.get("avgWakingRespirationValue"),
                summary.get("averageSpo2"),
                ts_fields.get("vo2_max"),
                ts_fields.get("acute_load"),
                ts_fields.get("chronic_load"),
                ts_fields.get("acwr"),
                ts_fields.get("acwr_status"),
                ts_fields.get("acwr_percent"),
                ts_fields.get("training_status"),
                ts_fields.get("load_aerobic_low"),
                ts_fields.get("load_aerobic_high"),
                ts_fields.get("load_anaerobic"),
                ts_fields.get("load_balance_feedback"),
                latest_r.get("score"),
                latest_r.get("level"),
                latest_r.get("inputContext"),
                rec_h,
                utcnow_iso(),
            ),
        )
        conn.commit()
        written += 1
        time.sleep(0.08)

    return written


def run_sync(
    scope: str = "incremental",
    days: int = 7,
    activity_limit: int = 100,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Run incremental or backfill sync synchronously (under _SYNC_LOCK)."""
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "already_running", "state": get_sync_state()}

    _SYNC_STATE.update(
        {
            "running": True,
            "scope": scope,
            "progress": 0,
            "total": days + 2,
            "current_step": "Authenticating with Garmin",
            "last_error": None,
        }
    )

    try:
        client = get_garmin_client()
        today = datetime.now().date()
        start_date = today - timedelta(days=max(1, days) - 1)

        with get_conn(db_path) as conn:
            _SYNC_STATE["current_step"] = "Syncing profile, HR zones & PRs"
            sync_profile_and_benchmarks(client, conn, scope=scope, today=today)
            conn.commit()
            _SYNC_STATE["progress"] = 1

            _SYNC_STATE["current_step"] = "Syncing activities & strength exercise sets"
            acts_n = sync_activities(
                client,
                conn,
                limit=activity_limit,
                scope=scope,
                refresh_sets_days=max(7, days if scope == "backfill" else 7),
            )
            conn.commit()
            _SYNC_STATE["progress"] = 2

            def _prog(i: int, tot: int, msg: str) -> None:
                _SYNC_STATE["progress"] = 2 + i
                _SYNC_STATE["total"] = 2 + tot
                _SYNC_STATE["current_step"] = msg

            days_n = sync_daily_window(
                client, conn, start_date, today, scope=scope, progress_cb=_prog
            )

        _SYNC_STATE["last_sync_at"] = utcnow_iso()
        _SYNC_STATE["current_step"] = "idle"
        return {
            "status": "ok",
            "scope": scope,
            "activities_synced": acts_n,
            "days_synced": days_n,
            "synced_at": _SYNC_STATE["last_sync_at"],
        }
    except Exception as exc:
        _SYNC_STATE["last_error"] = str(exc)
        _SYNC_STATE["current_step"] = f"error: {exc}"
        return {"status": "error", "error": str(exc)}
    finally:
        _SYNC_STATE["running"] = False
        _SYNC_LOCK.release()


def trigger_background_sync(
    scope: str = "incremental",
    days: int = 7,
    activity_limit: int = 100,
    db_path: Path = DEFAULT_DB_PATH,
) -> bool:
    """Kick off sync in a daemon thread if not already running."""
    if _SYNC_STATE["running"]:
        return False
    t = threading.Thread(
        target=run_sync,
        kwargs={
            "scope": scope,
            "days": days,
            "activity_limit": activity_limit,
            "db_path": db_path,
        },
        daemon=True,
    )
    t.start()
    return True


def fetch_intraday_cached(
    ds: str,
    refresh: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Fetch 24h intraday telemetry for ds with persistent raw cache."""
    today_str = datetime.now().date().isoformat()
    with get_conn(db_path) as conn:
        if not refresh:
            row = conn.execute(
                "SELECT payload_json, fetched_at FROM raw_payloads WHERE source_key='intraday_bundle' AND entity_key=?",
                (ds,),
            ).fetchone()
            if row:
                # Cache completed days permanently; refresh today if older than 5 min
                if ds < today_str:
                    return json.loads(row["payload_json"])
                try:
                    fetched = datetime.fromisoformat(row["fetched_at"])
                    age = (datetime.now(fetched.tzinfo) - fetched).total_seconds()
                    if age < 300:
                        return json.loads(row["payload_json"])
                except Exception:
                    return json.loads(row["payload_json"])

    client = get_garmin_client()
    with get_conn(db_path) as conn:
        hr_raw = _timed_call(conn, "intraday", "get_heart_rates", client.get_heart_rates, ds, default={}) or {}
        stress_raw = _timed_call(conn, "intraday", "get_stress_data", client.get_stress_data, ds, default={}) or {}
        bb_raw = _timed_call(conn, "intraday", "get_body_battery", client.get_body_battery, ds, ds, default=[]) or []
        resp_raw = _timed_call(conn, "intraday", "get_respiration_data", client.get_respiration_data, ds, default={}) or {}
        sleep_raw = _timed_call(conn, "intraday", "get_sleep_data", client.get_sleep_data, ds, default={}) or {}
        tr_raw = _timed_call(conn, "intraday", "get_training_readiness", client.get_training_readiness, ds, default=[]) or []

        def _hhmm(ts_ms: float) -> str:
            return datetime.fromtimestamp(ts_ms / 1000.0).strftime("%H:%M")

        hr_points = [
            {"t": _hhmm(p[0]), "ts": p[0], "v": p[1]}
            for p in (hr_raw.get("heartRateValues") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 2 and p[1] is not None and p[1] > 0
        ]
        stress_points = [
            {"t": _hhmm(p[0]), "ts": p[0], "v": p[1]}
            for p in (stress_raw.get("stressValuesArray") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 2 and p[1] is not None and p[1] >= 0
        ]
        bb_points = [
            {"t": _hhmm(p[0]), "ts": p[0], "v": p[2]}
            for p in (stress_raw.get("bodyBatteryValuesArray") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 3 and p[2] is not None
        ]
        resp_points = [
            {"t": _hhmm(p[0]), "ts": p[0], "v": p[1]}
            for p in (resp_raw.get("respirationValuesArray") or [])
            if isinstance(p, (list, tuple)) and len(p) >= 2 and p[1] is not None and p[1] > 0
        ]

        bb_day = bb_raw[0] if isinstance(bb_raw, list) and bb_raw else {}
        bb_events = [
            {
                "eventType": ev.get("eventType"),
                "impact": ev.get("bodyBatteryImpact"),
                "durationMin": round((ev.get("durationInMilliseconds") or 0) / 60000.0),
                "shortFeedback": ev.get("shortFeedback"),
                "feedbackType": ev.get("feedbackType"),
            }
            for ev in (bb_day.get("bodyBatteryActivityEvent") or [])
        ]

        readiness_timeline = []
        if isinstance(tr_raw, list):
            for r in sorted([x for x in tr_raw if isinstance(x, dict)], key=lambda x: x.get("timestamp") or ""):
                readiness_timeline.append(
                    {
                        "timestamp": r.get("timestamp"),
                        "timeLabel": (r.get("timestamp") or "")[11:16],
                        "context": r.get("inputContext"),
                        "score": r.get("score"),
                        "level": r.get("level"),
                        "recoveryTimeH": round(float(r.get("recoveryTime") or 0) / 60.0, 1),
                    }
                )

        sleep_dto = sleep_raw.get("dailySleepDTO") or {}
        bundle = {
            "date": ds,
            "summary": {
                "restingHr": hr_raw.get("restingHeartRate"),
                "minHr": hr_raw.get("minHeartRate"),
                "maxHr": hr_raw.get("maxHeartRate"),
                "avgStress": stress_raw.get("avgStressLevel"),
                "maxStress": stress_raw.get("maxStressLevel"),
                "bbCharged": bb_day.get("charged"),
                "bbDrained": bb_day.get("drained"),
                "respWakingAvg": resp_raw.get("avgWakingRespirationValue"),
                "respSleepAvg": resp_raw.get("avgSleepRespirationValue"),
                "respLowest": resp_raw.get("lowestRespirationValue"),
                "respHighest": resp_raw.get("highestRespirationValue"),
                "sleepScore": (sleep_dto.get("sleepScores") or {}).get("overall", {}).get("value"),
                "sleepHours": round((sleep_dto.get("sleepTimeSeconds") or 0) / 3600.0, 2)
                if sleep_dto.get("sleepTimeSeconds")
                else None,
                "readinessScore": readiness_timeline[-1]["score"] if readiness_timeline else None,
            },
            "heartRate": hr_points,
            "stress": stress_points,
            "bodyBattery": bb_points,
            "respiration": resp_points,
            "bodyBatteryEvents": bb_events,
            "readinessTimeline": readiness_timeline,
        }
        _save_raw(conn, "intraday_bundle", ds, bundle)
        return bundle


def _extract_route(details_raw: Any, location_name: Optional[str] = None) -> Dict[str, Any]:
    """Extract compact GPS polyline route from Garmin activity details."""
    if not isinstance(details_raw, dict):
        return {"hasRoute": False, "points": [], "locationName": location_name}
    geo = details_raw.get("geoPolylineDTO")
    if not isinstance(geo, dict):
        return {"hasRoute": False, "points": [], "locationName": location_name}
    raw_pts = [
        p
        for p in (geo.get("polyline") or [])
        if isinstance(p, dict) and p.get("valid", True) and p.get("lat") is not None and p.get("lon") is not None
    ]
    if not raw_pts:
        return {"hasRoute": False, "points": [], "locationName": location_name}

    # Downsample to <= 350 points for fast modal/card rendering
    step = max(1, len(raw_pts) // 350)
    sampled = raw_pts[::step]
    if sampled[-1] is not raw_pts[-1]:
        sampled.append(raw_pts[-1])

    points = [
        [
            round(float(p["lat"]), 6),
            round(float(p["lon"]), 6),
            round(float(p["speed"]), 2) if p.get("speed") is not None else None,
        ]
        for p in sampled
    ]
    sp = geo.get("startPoint") or {}
    ep = geo.get("endPoint") or {}
    return {
        "hasRoute": True,
        "locationName": location_name,
        "totalRawPoints": len(raw_pts),
        "points": points,
        "startPoint": [sp.get("lat"), sp.get("lon")] if sp.get("lat") is not None else points[0][:2],
        "endPoint": [ep.get("lat"), ep.get("lon")] if ep.get("lat") is not None else points[-1][:2],
        "bounds": [
            geo.get("minLat"),
            geo.get("maxLat"),
            geo.get("minLon"),
            geo.get("maxLon"),
        ],
    }


def fetch_activity_detail_cached(
    activity_id: int,
    refresh: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Fetch activity HR zones, lap splits, weather (in C for metric), GPS route, plus stored sets."""
    with get_conn(db_path) as conn:
        if not refresh:
            row = conn.execute(
                "SELECT payload_json FROM raw_payloads WHERE source_key='activity_detail' AND entity_key=?",
                (str(activity_id),),
            ).fetchone()
            if row:
                detail = json.loads(row["payload_json"])
                if "route" in detail:
                    # Always attach latest local DB activity metadata + sets
                    act_row = conn.execute(
                        "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
                    ).fetchone()
                    sets_rows = conn.execute(
                        "SELECT * FROM exercise_sets WHERE activity_id = ? ORDER BY set_index ASC",
                        (activity_id,),
                    ).fetchall()
                    detail["activity"] = dict(act_row) if act_row else None
                    if detail["activity"]:
                        detail["activity"].pop("raw_json", None)
                    detail["exerciseSets"] = [dict(r) for r in sets_rows]
                    return detail

    client = get_garmin_client()
    with get_conn(db_path) as conn:
        zones_raw = _timed_call(conn, "activity", "get_activity_hr_in_timezones", client.get_activity_hr_in_timezones, activity_id, default=[]) or []
        splits_raw = _timed_call(conn, "activity", "get_activity_splits", client.get_activity_splits, activity_id, default={}) or {}
        weather_raw = _timed_call(conn, "activity", "get_activity_weather", client.get_activity_weather, activity_id, default={}) or {}

        act_row = conn.execute("SELECT * FROM activities WHERE activity_id = ?", (activity_id,)).fetchone()
        try:
            act_raw_json = json.loads(act_row["raw_json"]) if act_row and act_row["raw_json"] else {}
        except Exception:
            act_raw_json = {}
        has_poly = bool(act_raw_json.get("hasPolyline"))
        location_name = act_raw_json.get("locationName")
        route_obj: Dict[str, Any] = {"hasRoute": False, "points": [], "locationName": location_name}
        if has_poly or (act_row and act_row["type"] in ("running", "trail_running", "walking", "hiking", "cycling")):
            details_raw = _timed_call(conn, "activity", "get_activity_details", client.get_activity_details, activity_id, default={})
            route_obj = _extract_route(details_raw, location_name=location_name)

        total_zone_sec = sum((z.get("secsInZone") or 0.0) for z in zones_raw) or 1.0
        zones = [
            {
                "zoneNumber": z.get("zoneNumber"),
                "lowBoundary": z.get("zoneLowBoundary"),
                "secsInZone": round(z.get("secsInZone") or 0.0, 1),
                "durationFormatted": format_duration_sec(z.get("secsInZone") or 0.0),
                "percent": round(((z.get("secsInZone") or 0.0) / total_zone_sec) * 100.0, 1),
            }
            for z in zones_raw
        ]

        laps = []
        for idx, lap in enumerate(splits_raw.get("lapDTOs") or [], start=1):
            dist_m = lap.get("distance") or 0.0
            dur_s = lap.get("duration") or 0.0
            laps.append(
                {
                    "lap": idx,
                    "distanceKm": round(dist_m / 1000.0, 2),
                    "durationSec": round(dur_s, 1),
                    "durationFormatted": format_duration_sec(dur_s),
                    "paceFormatted": format_pace(dur_s, dist_m),
                    "paceSecPerKm": round(dur_s / (dist_m / 1000.0), 1)
                    if dist_m > 10 and dur_s > 0
                    else None,
                    "avgHr": round(lap.get("averageHR"), 0) if lap.get("averageHR") else None,
                    "maxHr": round(lap.get("maxHR"), 0) if lap.get("maxHR") else None,
                    "cadence": round(lap.get("averageRunCadence"), 0)
                    if lap.get("averageRunCadence")
                    else None,
                    "power": round(lap.get("averagePower"), 0) if lap.get("averagePower") else None,
                    "elevationGain": round(lap.get("elevationGain") or 0.0, 1),
                    "calories": round(lap.get("calories") or 0.0, 0),
                }
            )

        weather = None
        if isinstance(weather_raw, dict) and weather_raw.get("temp") is not None:
            raw_f = weather_raw.get("temp")
            # Garmin weather returns Fahrenheit (per garmin_mcp activity_management.py)
            temp_c = round((float(raw_f) - 32.0) * 5.0 / 9.0, 1)
            weather = {
                "tempC": temp_c,
                "tempF": raw_f,
                "humidity": weather_raw.get("relativeHumidity"),
                "windSpeedKmh": weather_raw.get("windSpeed"),
                "desc": (weather_raw.get("weatherTypeDTO") or {}).get("desc"),
            }

        detail_base = {
            "activityId": activity_id,
            "hrZones": zones,
            "laps": laps,
            "weather": weather,
            "route": route_obj,
        }
        _save_raw(conn, "activity_detail", str(activity_id), detail_base)

        if act_row and act_row["type"] == "strength_training" and not act_row["sets_fetched"]:
            sync_exercise_sets_for_activity(client, conn, activity_id, scope="activity")

        sets_rows = conn.execute(
            "SELECT * FROM exercise_sets WHERE activity_id = ? ORDER BY set_index ASC",
            (activity_id,),
        ).fetchall()
        act_dict = dict(act_row) if act_row else None
        if act_dict:
            act_dict.pop("raw_json", None)

        return {
            **detail_base,
            "activity": act_dict,
            "exerciseSets": [dict(r) for r in sets_rows],
        }


def fetch_garmin_reports_cached(
    db_path: Path,
    target_date: str,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Fetch and cache Garmin Connect reports (fitness age, endurance, hill, race predictions, LT, PRs, badges)."""
    with get_conn(db_path) as conn:
        if not force_refresh:
            row = conn.execute(
                "SELECT payload_json FROM raw_cache WHERE endpoint = ? AND entity_key = ?",
                ("garmin_reports", target_date),
            ).fetchone()
            if row and row["payload_json"]:
                try:
                    cached = json.loads(row["payload_json"])
                    if isinstance(cached, dict) and "fitnessAge" in cached:
                        return cached
                except Exception:
                    pass

    client = get_garmin_client()
    yesterday_str = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    thirty_days_ago = (date.fromisoformat(target_date) - timedelta(days=30)).isoformat()
    with get_conn(db_path) as conn:
        fitness_age = _timed_call(conn, "reports", "get_fitnessage_data", client.get_fitnessage_data, target_date, default={}) or {}
        endurance = _timed_call(conn, "reports", "get_endurance_score", client.get_endurance_score, target_date, default={}) or {}
        if not endurance.get("overallScore"):
            endurance = _timed_call(conn, "reports", "get_endurance_score", client.get_endurance_score, yesterday_str, default={}) or {}
        hill = _timed_call(conn, "reports", "get_hill_score", client.get_hill_score, target_date, default={}) or {}
        if not hill.get("overallScore"):
            hill = _timed_call(conn, "reports", "get_hill_score", client.get_hill_score, yesterday_str, default={}) or {}
        readiness = _timed_call(conn, "reports", "get_training_readiness", client.get_training_readiness, target_date, default=[]) or []
        if not readiness:
            readiness = _timed_call(conn, "reports", "get_training_readiness", client.get_training_readiness, yesterday_str, default=[]) or []
        status = _timed_call(conn, "reports", "get_training_status", client.get_training_status, target_date, default={}) or {}
        if not status.get("mostRecentTrainingStatus"):
            status = _timed_call(conn, "reports", "get_training_status", client.get_training_status, yesterday_str, default={}) or {}
        progress_30d = _timed_call(conn, "reports", "get_progress_summary_between_dates", client.get_progress_summary_between_dates, thirty_days_ago, target_date, default=[]) or []
        sleep_raw = _timed_call(conn, "reports", "get_sleep_data", client.get_sleep_data, target_date, default={}) or {}
        if not ((sleep_raw.get("dailySleepDTO") or {}).get("sleepTimeSeconds")):
            sleep_raw = _timed_call(conn, "reports", "get_sleep_data", client.get_sleep_data, yesterday_str, default={}) or {}
        user_summary = _timed_call(conn, "reports", "get_user_summary", client.get_user_summary, target_date, default={}) or {}
        if not user_summary.get("totalSteps"):
            user_summary = _timed_call(conn, "reports", "get_user_summary", client.get_user_summary, yesterday_str, default={}) or {}
        race_pred = _timed_call(conn, "reports", "get_race_predictions", client.get_race_predictions, default={}) or {}
        lactate = _timed_call(conn, "reports", "get_lactate_threshold", client.get_lactate_threshold, default={}) or {}
        prs = _timed_call(conn, "reports", "get_personal_record", client.get_personal_record, default=[]) or []
        badges = _timed_call(conn, "reports", "get_earned_badges", client.get_earned_badges, default=[]) or []

        payload = {
            "date": target_date,
            "fitnessAge": fitness_age if isinstance(fitness_age, dict) else {},
            "enduranceScore": endurance if isinstance(endurance, dict) else {},
            "hillScore": hill if isinstance(hill, dict) else {},
            "trainingReadiness": readiness[0] if isinstance(readiness, list) and readiness else (readiness if isinstance(readiness, dict) else {}),
            "trainingStatus": status if isinstance(status, dict) else {},
            "progress30d": progress_30d if isinstance(progress_30d, list) else [],
            "sleepData": sleep_raw if isinstance(sleep_raw, dict) else {},
            "userSummary": user_summary if isinstance(user_summary, dict) else {},
            "racePredictions": race_pred if isinstance(race_pred, dict) else {},
            "lactateThreshold": lactate if isinstance(lactate, dict) else {},
            "personalRecords": prs if isinstance(prs, list) else [],
            "earnedBadges": badges[:12] if isinstance(badges, list) else [],
        }
        _save_raw(conn, "garmin_reports", target_date, payload)
        return payload
