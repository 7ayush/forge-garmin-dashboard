"""Derived hybrid-athlete metrics, rules engine, and screen view-model builders for FORGE."""

from __future__ import annotations

import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .db import DEFAULT_DB_PATH, get_conn, get_settings, load_muscle_map
from .exercise_taxonomy import MUSCLE_GROUPS, MUSCLE_META, TRIAGE_PRESETS, resolve_muscle_mapping
from .garmin_sync import format_duration_sec, format_pace, get_sync_state

CARDIO_TYPES = {
    "running",
    "treadmill_running",
    "trail_running",
    "track_running",
    "cycling",
    "indoor_cycling",
    "swimming",
    "walking",
    "hiking",
    "elliptical",
}
RUN_TYPES = {"running", "treadmill_running", "trail_running", "track_running"}
LOWER_MUSCLES = {"quads", "hamstrings", "glutes", "calves"}
PUSH_MUSCLES = {"chest", "shoulders", "triceps"}
PULL_MUSCLES = {"back", "rear_delts", "biceps", "traps"}
UPPER_MUSCLES = PUSH_MUSCLES | PULL_MUSCLES
CORE_MUSCLES_KEY = ["chest", "back", "shoulders", "rear_delts", "biceps", "triceps", "quads", "hamstrings", "glutes", "calves"]
LOADED_CATEGORIES = {
    "BENCH_PRESS",
    "CHEST_PRESS",
    "FLYE",
    "PULL_UP",
    "ROW",
    "LAT_PULLDOWN",
    "SHOULDER_PRESS",
    "LATERAL_RAISE",
    "SHRUG",
    "CURL",
    "TRICEPS_EXTENSION",
    "SQUAT",
    "LUNGE",
    "LEG_PRESS",
    "LEG_CURL",
    "DEADLIFT",
    "HIP_RAISE",
    "CALF_RAISE",
}


def monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _safe_json(text: Optional[str], default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def compute_e1rm(weight_kg: float, reps: int, formula: str = "epley") -> Optional[float]:
    if weight_kg <= 0 or reps < 1 or reps > 10:
        return None
    if reps == 1:
        return round(weight_kg, 1)
    if formula == "brzycki":
        return round(weight_kg * 36.0 / (37.0 - reps), 1)
    return round(weight_kg * (1.0 + reps / 30.0), 1)


def _flag_warmups(sets: List[Dict[str, Any]]) -> Dict[int, bool]:
    """Identify likely warmup sets (<50% of session's max working weight for same exercise)."""
    max_by_ex: Dict[str, float] = defaultdict(float)
    for s in sets:
        if s["set_type"] != "ACTIVE" or s["category"] == "CARDIO":
            continue
        key = s.get("exercise_name") or s["category"]
        w = float(s.get("weight_kg") or 0)
        if w > max_by_ex[key]:
            max_by_ex[key] = w

    flags: Dict[int, bool] = {}
    for s in sets:
        key = s.get("exercise_name") or s["category"]
        w = float(s.get("weight_kg") or 0)
        top_w = max_by_ex.get(key, 0.0)
        flags[s["id"]] = bool(top_w > 0 and 0 < w < 0.5 * top_w)
    return flags


def _detect_session_triage_issues(sets: List[Dict[str, Any]]) -> Dict[int, List[str]]:
    """Return quality issue flags per set id within one strength session."""
    active = [s for s in sets if s["set_type"] == "ACTIVE" and s["category"] != "CARDIO"]
    issues: Dict[int, List[str]] = defaultdict(list)
    if not active:
        return issues

    rep_counts = Counter(s["reps"] for s in active if s["reps"] is not None and s["reps"] > 0)
    suspicious_rep_val: Optional[int] = None
    if len(active) >= 5 and rep_counts:
        top_rep, top_cnt = rep_counts.most_common(1)[0]
        if (top_cnt / len(active)) >= 0.60 and not any(s.get("user_corrected") for s in active if s["reps"] == top_rep):
            suspicious_rep_val = top_rep

    for s in active:
        if s.get("user_corrected"):
            continue
        cat = (s.get("category") or "UNKNOWN").upper()
        prob = s.get("probability")
        reps = s.get("reps")
        w = float(s.get("weight_kg") or 0)
        if cat == "UNKNOWN":
            issues[s["id"]].append("unclassified_exercise")
        if prob is not None and prob < 80:
            issues[s["id"]].append("low_confidence")
        if suspicious_rep_val is not None and reps == suspicious_rep_val:
            issues[s["id"]].append("suspicious_default_reps")
        if reps is None or reps == 0:
            issues[s["id"]].append("zero_or_missing_reps")
        if cat in LOADED_CATEGORIES and w <= 0:
            issues[s["id"]].append("zero_weight_on_loaded_lift")

    return issues


def analyze_strength(conn, settings: Dict[str, Any], week_start: Optional[date] = None) -> Dict[str, Any]:
    """Compute complete Hypertrophy Lab analytics across all strength activities."""
    today = datetime.now().date()
    target_week_start = week_start or monday_of_week(today)
    target_week_end = target_week_start + timedelta(days=6)
    muscle_map = load_muscle_map(conn)
    formula = settings.get("e1rm_formula", "epley")
    exclude_warmups = bool(settings.get("exclude_warmups", True))
    set_min = int(settings.get("muscle_set_min", 10))
    set_max = int(settings.get("muscle_set_max", 20))

    acts = conn.execute(
        "SELECT * FROM activities WHERE type = 'strength_training' ORDER BY start_time_local DESC"
    ).fetchall()
    act_list = [dict(a) for a in acts]
    for a in act_list:
        a.pop("raw_json", None)

    all_sets_rows = conn.execute(
        """
        SELECT es.*, a.name AS activity_name, a.calendar_date, a.start_time_local, a.duration_s AS activity_duration_s
        FROM exercise_sets es
        JOIN activities a ON a.activity_id = es.activity_id
        ORDER BY a.start_time_local ASC, es.set_index ASC
        """
    ).fetchall()
    all_sets = [dict(r) for r in all_sets_rows]

    sets_by_activity: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for s in all_sets:
        sets_by_activity[s["activity_id"]].append(s)

    warmup_flags: Dict[int, bool] = {}
    triage_map: Dict[int, List[str]] = {}
    for aid, s_list in sets_by_activity.items():
        warmup_flags.update(_flag_warmups(s_list))
        triage_map.update(_detect_session_triage_issues(s_list))

    # Weekly & all-time accumulators
    direct_week: Dict[str, float] = defaultdict(float)
    fractional_week: Dict[str, float] = defaultdict(float)
    direct_all: Dict[str, float] = defaultdict(float)
    last_trained: Dict[str, str] = {}
    weekly_tonnage: Dict[str, float] = defaultdict(float)
    session_summaries: List[Dict[str, Any]] = []
    triage_queue: List[Dict[str, Any]] = []

    # e1RM & progressive overload tracking
    ex_sessions: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    ex_non_qualifying: Counter = Counter()
    ex_total_sets: Counter = Counter()

    total_active_sets = 0
    total_verified_sets = 0
    total_tonnage_all = 0.0
    rest_samples: List[float] = []

    for aid, s_list in sets_by_activity.items():
        act_info = next((a for a in act_list if a["activity_id"] == aid), None)
        if not act_info:
            continue
        cal_date = act_info["calendar_date"]
        d_obj = date.fromisoformat(cal_date)
        wk_s = monday_of_week(d_obj).isoformat()
        in_target_week = target_week_start <= d_obj <= target_week_end

        sess_tonnage = 0.0
        sess_sets = 0
        sess_muscles: Dict[str, float] = defaultdict(float)
        sess_issues = 0

        for s in s_list:
            if s["set_type"] != "ACTIVE":
                continue
            cat = (s["category"] or "UNKNOWN").upper()
            ex_name = s.get("exercise_name")
            primary, secondary = resolve_muscle_mapping(cat, ex_name, muscle_map)
            if primary == "cardio":
                continue

            total_active_sets += 1
            is_warmup = warmup_flags.get(s["id"], False)
            issues = triage_map.get(s["id"], [])
            if not issues:
                total_verified_sets += 1
            else:
                sess_issues += 1
                triage_queue.append(
                    {
                        "id": s["id"],
                        "activity_id": aid,
                        "activity_name": act_info["name"],
                        "calendar_date": cal_date,
                        "set_index": s["set_index"],
                        "category": cat,
                        "exercise_name": ex_name,
                        "probability": s.get("probability"),
                        "reps": s.get("reps"),
                        "weight_kg": s.get("weight_kg"),
                        "duration_s": s.get("duration_s"),
                        "issues": issues,
                    }
                )

            reps = int(s.get("reps") or 0)
            w_kg = float(s.get("weight_kg") or 0.0)
            if s.get("rest_s"):
                rest_samples.append(float(s["rest_s"]))

            tonnage = reps * w_kg
            sess_tonnage += tonnage
            total_tonnage_all += tonnage
            weekly_tonnage[wk_s] += tonnage

            if exclude_warmups and is_warmup:
                continue

            sess_sets += 1
            if primary != "unknown":
                direct_all[primary] += 1.0
                sess_muscles[primary] += 1.0
                if cal_date > last_trained.get(primary, ""):
                    last_trained[primary] = cal_date
                if in_target_week:
                    direct_week[primary] += 1.0
                    fractional_week[primary] += 1.0
                for sec in secondary:
                    if in_target_week:
                        fractional_week[sec] += 0.5
                    if cal_date > last_trained.get(sec, ""):
                        last_trained[sec] = cal_date

            # e1RM per exercise
            ex_key = ex_name or cat
            if ex_key != "UNKNOWN":
                ex_total_sets[ex_key] += 1
                e1 = compute_e1rm(w_kg, reps, formula=formula)
                entry = ex_sessions[ex_key].setdefault(
                    f"{cal_date}_{aid}",
                    {
                        "date": cal_date,
                        "activity_id": aid,
                        "best_e1rm": 0.0,
                        "best_weight": 0.0,
                        "best_reps": 0,
                        "best_volume_set": 0.0,
                        "sets": 0,
                    },
                )
                entry["sets"] += 1
                if e1 is not None:
                    if e1 > entry["best_e1rm"]:
                        entry["best_e1rm"] = e1
                        entry["best_weight"] = w_kg
                        entry["best_reps"] = reps
                else:
                    ex_non_qualifying[ex_key] += 1
                    if tonnage > entry["best_volume_set"]:
                        entry["best_volume_set"] = tonnage
                        if entry["best_e1rm"] == 0.0:
                            entry["best_weight"] = w_kg
                            entry["best_reps"] = reps

        dur_min = max((act_info.get("duration_s") or 60.0) / 60.0, 1.0)
        session_summaries.append(
            {
                "activity_id": aid,
                "name": act_info["name"],
                "calendar_date": cal_date,
                "start_time_local": act_info["start_time_local"],
                "duration_min": round(dur_min, 1),
                "avg_hr": act_info.get("avg_hr"),
                "working_sets": sess_sets,
                "tonnage_kg": round(sess_tonnage, 1),
                "density_kg_per_min": round(sess_tonnage / dur_min, 1),
                "issue_count": sess_issues,
                "muscles": dict(sess_muscles),
            }
        )

    # Muscle volume table for target week
    muscle_volume = []
    for m in MUSCLE_GROUPS:
        mid = m["id"]
        d_sets = round(direct_week.get(mid, 0.0), 1)
        f_sets = round(fractional_week.get(mid, 0.0), 1)
        lt_date = last_trained.get(mid)
        days_since = (today - date.fromisoformat(lt_date)).days if lt_date else None
        status = (
            "optimal"
            if set_min <= f_sets <= set_max
            else ("over" if f_sets > set_max else ("low" if f_sets > 0 else "untrained"))
        )
        muscle_volume.append(
            {
                "muscle": mid,
                "label": m["label"],
                "region": m["region"],
                "pattern": m["pattern"],
                "direct_sets": d_sets,
                "fractional_sets": f_sets,
                "all_time_direct": round(direct_all.get(mid, 0.0), 1),
                "target_min": set_min,
                "target_max": set_max,
                "last_trained": lt_date,
                "days_since": days_since,
                "status": status,
            }
        )

    # Balance ratios (using target week fractional sets, and fallback all-time)
    def _ratio_block(src: Dict[str, float]) -> Dict[str, Any]:
        push = sum(src.get(m, 0.0) for m in PUSH_MUSCLES)
        pull = sum(src.get(m, 0.0) for m in PULL_MUSCLES)
        upper = sum(src.get(m, 0.0) for m in UPPER_MUSCLES)
        lower = sum(src.get(m, 0.0) for m in LOWER_MUSCLES)
        quads = src.get("quads", 0.0)
        hams = src.get("hamstrings", 0.0)
        return {
            "push_sets": round(push, 1),
            "pull_sets": round(pull, 1),
            "push_pull_ratio": round(push / pull, 2) if pull > 0 else None,
            "upper_sets": round(upper, 1),
            "lower_sets": round(lower, 1),
            "upper_lower_ratio": round(upper / lower, 2) if lower > 0 else None,
            "quads_sets": round(quads, 1),
            "hamstrings_sets": round(hams, 1),
            "quad_ham_ratio": round(quads / hams, 2) if hams > 0 else None,
        }

    # Build e1RM & Overload report
    cutoff_28 = (today - timedelta(days=28)).isoformat()
    exercises_progress: List[Dict[str, Any]] = []
    for ex_key, sess_dict in ex_sessions.items():
        series = sorted(sess_dict.values(), key=lambda x: x["date"])
        qualifying = [x for x in series if x["best_e1rm"] > 0]
        best_ever = max((x["best_e1rm"] for x in qualifying), default=None)
        best_28d = max((x["best_e1rm"] for x in qualifying if x["date"] >= cutoff_28), default=None)

        # Overload status across >= 2 sessions
        overload_status = "building_baseline"
        if len(series) >= 2:
            latest = series[-1]
            prior_best_e1rm = max((x["best_e1rm"] for x in series[:-1]), default=0.0)
            prior_best_vol = max((x["best_volume_set"] for x in series[:-1]), default=0.0)
            if latest["best_e1rm"] > 0 and latest["best_e1rm"] > prior_best_e1rm:
                overload_status = "pr"
            elif latest["best_volume_set"] > 0 and latest["best_volume_set"] > prior_best_vol and prior_best_e1rm == 0:
                overload_status = "pr"
            elif len(series) >= 3:
                # Check last 3 sessions had no improvement over sessions before them
                if len(series) >= 4:
                    prev_max = max((x["best_e1rm"] or x["best_volume_set"] for x in series[:-3]), default=0)
                    last3_max = max((x["best_e1rm"] or x["best_volume_set"] for x in series[-3:]), default=0)
                    if last3_max <= prev_max:
                        overload_status = "stalled"
                else:
                    vals = [x["best_e1rm"] or x["best_volume_set"] for x in series[-3:]]
                    if vals[2] <= vals[0] and vals[1] <= vals[0]:
                        overload_status = "stalled"

        exercises_progress.append(
            {
                "exercise": ex_key,
                "total_sets": ex_total_sets[ex_key],
                "non_qualifying_sets": ex_non_qualifying[ex_key],
                "best_e1rm": best_ever,
                "rolling_28d_e1rm": best_28d,
                "latest_weight": series[-1]["best_weight"],
                "latest_reps": series[-1]["best_reps"],
                "overload_status": overload_status,
                "series": series,
                "note": (
                    f"No qualifying sets (1–10 reps); {ex_non_qualifying[ex_key]} sets logged at >10 reps"
                    if best_ever is None and ex_non_qualifying[ex_key] > 0
                    else None
                ),
            }
        )
    exercises_progress.sort(key=lambda x: (x["best_e1rm"] or 0.0, x["total_sets"]), reverse=True)

    # Session template comparison (latest vs previous of same name)
    by_name: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ss in sorted(session_summaries, key=lambda x: x["start_time_local"], reverse=True):
        by_name[ss["name"]].append(ss)
    comparisons = []
    for name, lst in by_name.items():
        if len(lst) >= 2:
            cur, prev = lst[0], lst[1]
            comparisons.append(
                {
                    "template": name,
                    "current": cur,
                    "previous": prev,
                    "tonnage_delta_kg": round(cur["tonnage_kg"] - prev["tonnage_kg"], 1),
                    "sets_delta": cur["working_sets"] - prev["working_sets"],
                }
            )

    # Relative strength standards against latest weight
    bw_kg = _latest_weight_kg(conn) or 73.0
    def _best_for_keywords(keywords: List[str]) -> Optional[float]:
        vals = [
            e["best_e1rm"]
            for e in exercises_progress
            if e["best_e1rm"] and any(k in e["exercise"] for k in keywords)
        ]
        return max(vals) if vals else None

    standards = [
        {"lift": "Bench Press", "e1rm": _best_for_keywords(["BENCH_PRESS"]), "novice": 0.75, "inter": 1.0, "adv": 1.25},
        {"lift": "Squat", "e1rm": _best_for_keywords(["SQUAT", "LEG_PRESS"]), "novice": 1.0, "inter": 1.5, "adv": 1.75},
        {"lift": "Deadlift", "e1rm": _best_for_keywords(["DEADLIFT"]), "novice": 1.25, "inter": 2.0, "adv": 2.25},
        {"lift": "Row", "e1rm": _best_for_keywords(["ROW"]), "novice": 0.7, "inter": 0.95, "adv": 1.2},
        {"lift": "Overhead Press", "e1rm": _best_for_keywords(["SHOULDER_PRESS"]), "novice": 0.5, "inter": 0.7, "adv": 0.9},
    ]
    for st in standards:
        st["bw_ratio"] = round(st["e1rm"] / bw_kg, 2) if st["e1rm"] else None

    # Missing-volume planner for target week
    missing_plan = [
        {
            "muscle": mv["muscle"],
            "label": mv["label"],
            "done": mv["fractional_sets"],
            "needed": round(max(0.0, set_min - mv["fractional_sets"]), 1),
        }
        for mv in muscle_volume
        if mv["muscle"] in CORE_MUSCLES_KEY and mv["fractional_sets"] < set_min
    ]
    missing_plan.sort(key=lambda x: -x["needed"])

    # Available weeks list (Mondays)
    available_weeks = sorted(
        {monday_of_week(date.fromisoformat(a["calendar_date"])).isoformat() for a in act_list}
        | {monday_of_week(today).isoformat()},
        reverse=True,
    )

    verified_pct = round((total_verified_sets / total_active_sets) * 100.0, 1) if total_active_sets else 100.0

    return {
        "week_start": target_week_start.isoformat(),
        "week_end": target_week_end.isoformat(),
        "available_weeks": available_weeks,
        "e1rm_formula": formula,
        "exclude_warmups": exclude_warmups,
        "summary": {
            "total_sessions": len(act_list),
            "sessions_this_week": sum(
                1 for a in act_list if target_week_start.isoformat() <= a["calendar_date"] <= target_week_end.isoformat()
            ),
            "total_active_sets": total_active_sets,
            "verified_sets": total_verified_sets,
            "verified_pct": verified_pct,
            "unclassified_count": sum(1 for q in triage_queue if "unclassified_exercise" in q["issues"]),
            "total_triage_count": len(triage_queue),
            "total_tonnage_kg": round(total_tonnage_all, 0),
            "avg_rest_sec": round(statistics.mean(rest_samples), 0) if rest_samples else None,
        },
        "muscle_volume": muscle_volume,
        "balance_week": _ratio_block(fractional_week),
        "balance_all_time": _ratio_block(direct_all),
        "triage_queue": triage_queue,
        "triage_presets": TRIAGE_PRESETS,
        "exercises_progress": exercises_progress,
        "weekly_tonnage": [
            {"week_start": wk, "tonnage_kg": round(val, 0)}
            for wk, val in sorted(weekly_tonnage.items())
        ],
        "session_summaries": sorted(session_summaries, key=lambda x: x["start_time_local"], reverse=True),
        "session_comparisons": comparisons,
        "relative_strength": standards,
        "missing_volume_plan": missing_plan,
        "bodyweight_kg": bw_kg,
    }


def _latest_weight_kg(conn) -> Optional[float]:
    row = conn.execute(
        "SELECT weight_kg FROM body_measurements WHERE weight_kg IS NOT NULL ORDER BY calendar_date DESC, recorded_at DESC LIMIT 1"
    ).fetchone()
    if row and row["weight_kg"]:
        return float(row["weight_kg"])
    prof = conn.execute("SELECT weight_kg FROM athlete_profile WHERE id = 1").fetchone()
    return float(prof["weight_kg"]) if prof and prof["weight_kg"] else None


def analyze_engine(conn, settings: Dict[str, Any], days: int = 30) -> Dict[str, Any]:
    """Compute Engine (Cardio & Running) analytics, Z2 discipline, ACWR, and interference warnings."""
    today = datetime.now().date()
    start_s = (today - timedelta(days=days - 1)).isoformat()
    week_start = monday_of_week(today).isoformat()

    acts_rows = conn.execute(
        "SELECT * FROM activities WHERE calendar_date >= ? ORDER BY start_time_local DESC",
        (start_s,),
    ).fetchall()
    all_acts = [dict(r) for r in acts_rows]
    for a in all_acts:
        a.pop("raw_json", None)

    cardio_acts = [a for a in all_acts if a["type"] in CARDIO_TYPES]
    run_acts = [a for a in all_acts if a["type"] in RUN_TYPES]
    week_runs = [a for a in run_acts if a["calendar_date"] >= week_start]

    def _zone_totals(lst: List[Dict[str, Any]]) -> Dict[str, Any]:
        z = [sum(float(a.get(f"hr_z{i}_s") or 0.0) for a in lst) for i in range(1, 6)]
        tot = sum(z)
        z2_pct = round(((z[0] + z[1]) / tot) * 100.0, 1) if tot > 0 else None
        z45_min = round((z[3] + z[4]) / 60.0, 1)
        return {
            "zones_sec": [round(x, 1) for x in z],
            "zones_pct": [round((x / tot) * 100.0, 1) if tot > 0 else 0.0 for x in z],
            "total_zone_min": round(tot / 60.0, 1),
            "z2_discipline_pct": z2_pct,
            "z4_z5_min": z45_min,
        }

    zones_window = _zone_totals(run_acts)
    zones_week = _zone_totals(week_runs)

    # Interference guard: hard cardio within ±6h of lower-body strength session
    window_h = float(settings.get("interference_window_hours", 6.0))
    lower_strength_rows = conn.execute(
        """
        SELECT DISTINCT a.activity_id, a.name, a.start_time_local, a.calendar_date
        FROM activities a
        JOIN exercise_sets es ON es.activity_id = a.activity_id
        WHERE a.type = 'strength_training' AND es.set_type = 'ACTIVE'
        """
    ).fetchall()
    muscle_map = load_muscle_map(conn)
    lower_sessions: List[Dict[str, Any]] = []
    for row in lower_strength_rows:
        sets = conn.execute(
            "SELECT category, exercise_name FROM exercise_sets WHERE activity_id = ? AND set_type = 'ACTIVE'",
            (row["activity_id"],),
        ).fetchall()
        hits_lower = any(
            resolve_muscle_mapping(s["category"], s["exercise_name"], muscle_map)[0] in LOWER_MUSCLES
            for s in sets
        )
        if hits_lower:
            lower_sessions.append(dict(row))

    interference_events: List[Dict[str, Any]] = []
    for c in cardio_acts:
        hard = (c.get("te_aerobic") or 0) >= 3.5 or ((c.get("hr_z4_s") or 0) + (c.get("hr_z5_s") or 0)) >= 1200
        if not hard or not c.get("start_time_local"):
            continue
        try:
            c_dt = datetime.fromisoformat(c["start_time_local"][:19])
        except ValueError:
            continue
        for ls in lower_sessions:
            try:
                l_dt = datetime.fromisoformat(ls["start_time_local"][:19])
            except ValueError:
                continue
            diff_h = abs((c_dt - l_dt).total_seconds()) / 3600.0
            if diff_h <= window_h:
                interference_events.append(
                    {
                        "cardio_name": c["name"],
                        "cardio_date": c["start_time_local"][:16],
                        "strength_name": ls["name"],
                        "strength_date": ls["start_time_local"][:16],
                        "gap_hours": round(diff_h, 1),
                        "te_aerobic": c.get("te_aerobic"),
                    }
                )

    # Wellness load / VO2 trend
    daily_rows = conn.execute(
        "SELECT * FROM daily_wellness WHERE calendar_date >= ? ORDER BY calendar_date ASC",
        ((today - timedelta(days=89)).isoformat(),),
    ).fetchall()
    daily = [dict(r) for r in daily_rows]
    latest_ts = next(
        (d for d in reversed(daily) if d.get("acute_load") is not None or d.get("training_status") is not None),
        {},
    )

    vo2_trend = [
        {"date": d["calendar_date"], "vo2_max": d["vo2_max"], "carried_forward": bool(d["vo2_carried_forward"])}
        for d in daily
        if d.get("vo2_max") is not None
    ]
    load_trend = [
        {
            "date": d["calendar_date"],
            "acute_load": d["acute_load"],
            "chronic_load": d["chronic_load"],
            "acwr": d["acwr"],
            "training_status": d["training_status"],
        }
        for d in daily
        if d.get("acute_load") is not None or d.get("chronic_load") is not None
    ]

    # Aerobic efficiency & running dynamics
    efficiency_series = []
    for a in sorted(run_acts, key=lambda x: x["start_time_local"]):
        dist = float(a.get("distance_m") or 0)
        dur = float(a.get("duration_s") or 0)
        hr = float(a.get("avg_hr") or 0)
        if dist >= 1500 and dur > 0 and hr > 0:
            speed_m_min = (dist / dur) * 60.0
            eff = round(speed_m_min / hr, 3)
            efficiency_series.append(
                {
                    "date": a["calendar_date"],
                    "name": a["name"],
                    "distance_km": round(dist / 1000.0, 2),
                    "pace": format_pace(dur, dist),
                    "avg_hr": round(hr, 0),
                    "efficiency_index": eff,
                    "power_hr": round(float(a["avg_power"]) / hr, 2) if a.get("avg_power") else None,
                    "cadence": a.get("avg_cadence"),
                    "gct_ms": a.get("avg_gct_ms"),
                    "vo_cm": a.get("avg_vo_cm"),
                    "stride_cm": a.get("avg_stride_cm"),
                }
            )

    prof = conn.execute("SELECT * FROM athlete_profile WHERE id = 1").fetchone()
    prof_d = dict(prof) if prof else {}
    race_raw = _safe_json(prof_d.get("race_predictions_json"), {})
    prs_raw = _safe_json(prof_d.get("personal_records_json"), [])
    endurance_raw = _safe_json(prof_d.get("endurance_json"), {})
    hill_raw = _safe_json(prof_d.get("hill_json"), {})

    race_predictions = {}
    for key, dist_km, label in [
        ("time5K", 5.0, "5K"),
        ("time10K", 10.0, "10K"),
        ("timeHalfMarathon", 21.0975, "Half Marathon"),
        ("timeMarathon", 42.195, "Marathon"),
    ]:
        sec = race_raw.get(key) if isinstance(race_raw, dict) else None
        if sec:
            race_predictions[label] = {
                "seconds": sec,
                "formatted": format_duration_sec(sec),
                "pace": format_pace(sec, dist_km * 1000.0),
            }

    pr_labels = {
        1: ("Fastest 1K", "time"),
        2: ("Fastest 1 Mile", "time"),
        3: ("Fastest 5K", "time"),
        4: ("Fastest 10K", "time"),
        5: ("Fastest Half Marathon", "time"),
        6: ("Fastest Marathon", "time"),
        7: ("Longest Run", "distance"),
        12: ("Most Steps (Day)", "steps"),
        13: ("Most Steps (Week)", "steps"),
        14: ("Most Steps (Month)", "steps"),
        15: ("Longest Daily Streak", "days"),
    }
    formatted_prs = []
    for pr in prs_raw or []:
        tid = pr.get("typeId")
        val = pr.get("value")
        if tid not in pr_labels or val is None:
            continue
        label, kind = pr_labels[tid]
        if kind == "time":
            disp = format_duration_sec(val)
        elif kind == "distance":
            disp = f"{round(val / 1000.0, 2)} km"
        elif kind == "steps":
            disp = f"{int(round(val)):,} steps"
        else:
            disp = f"{int(round(val))} days"
        formatted_prs.append(
            {
                "typeId": tid,
                "label": label,
                "displayValue": disp,
                "activityName": pr.get("activityName") or "Daily Milestone",
                "date": (pr.get("actStartDateTimeInGMTFormatted") or "")[:10],
            }
        )

    endurance_dto = (endurance_raw.get("enduranceScoreDTO") or {}) if isinstance(endurance_raw, dict) else {}
    hill_list = (hill_raw.get("hillScoreDTOList") or []) if isinstance(hill_raw, dict) else []
    latest_hill = hill_list[0] if hill_list else {}

    formatted_acts = []
    for a in all_acts:
        dist_m = a.get("distance_m") or 0
        dur_s = a.get("duration_s") or 0
        raw_act = _safe_json(a.get("raw_json"), {})
        formatted_acts.append(
            {
                "activityId": a["activity_id"],
                "name": a["name"],
                "type": a["type"],
                "startTimeLocal": a["start_time_local"],
                "date": a["calendar_date"],
                "hasPolyline": bool(raw_act.get("hasPolyline")) or (a.get("type") in ("running", "trail_running", "walking", "hiking", "cycling")),
                "locationName": raw_act.get("locationName"),
                "distanceKm": round(dist_m / 1000.0, 2),
                "durationSec": round(dur_s, 1),
                "durationFormatted": format_duration_sec(dur_s),
                "paceFormatted": format_pace(dur_s, dist_m) if a["type"] in RUN_TYPES or a["type"] == "walking" else None,
                "calories": round(a.get("calories") or 0),
                "avgHr": round(a["avg_hr"]) if a.get("avg_hr") else None,
                "maxHr": round(a["max_hr"]) if a.get("max_hr") else None,
                "aerobicTe": round(a.get("te_aerobic") or 0.0, 1),
                "anaerobicTe": round(a.get("te_anaerobic") or 0.0, 1),
                "trainingLoad": round(a.get("training_load") or 0.0, 1),
                "avgPower": round(a["avg_power"]) if a.get("avg_power") else None,
                "normPower": round(a["norm_power"]) if a.get("norm_power") else None,
                "avgCadence": round(a["avg_cadence"]) if a.get("avg_cadence") else None,
                "rpe": a.get("rpe"),
                "feel": a.get("feel"),
                "z1_2_pct": round(
                    ((a["hr_z1_s"] + a["hr_z2_s"]) / max(a["hr_z1_s"] + a["hr_z2_s"] + a["hr_z3_s"] + a["hr_z4_s"] + a["hr_z5_s"], 1.0)) * 100.0,
                    1,
                )
                if (a["hr_z1_s"] + a["hr_z2_s"] + a["hr_z3_s"] + a["hr_z4_s"] + a["hr_z5_s"]) > 0
                else None,
            }
        )

    # Interference warnings summary
    warnings: List[str] = []
    if zones_week["z2_discipline_pct"] is not None and zones_week["z2_discipline_pct"] < float(settings.get("z2_target_pct", 75)):
        warnings.append(
            f"Weekly Z2 discipline is {zones_week['z2_discipline_pct']}% (target ≥ {settings.get('z2_target_pct', 75)}%). Too much Z4–Z5 intensity can blunt hypertrophy recovery."
        )
    if latest_ts.get("load_balance_feedback") == "AEROBIC_LOW_SHORTAGE":
        warnings.append("Garmin Load Focus reports AEROBIC_LOW_SHORTAGE — add 1–2 easy Z2 base runs/walks.")
    if interference_events:
        warnings.append(f"{len(interference_events)} hard cardio session(s) occurred within ±{window_h}h of lower-body lifting.")

    return {
        "days": days,
        "z2_target_pct": settings.get("z2_target_pct", 75),
        "zones_window": zones_window,
        "zones_week": zones_week,
        "training_status": {
            "status": latest_ts.get("training_status"),
            "acute_load": latest_ts.get("acute_load"),
            "chronic_load": latest_ts.get("chronic_load"),
            "acwr": latest_ts.get("acwr"),
            "acwr_status": latest_ts.get("acwr_status"),
            "acwr_percent": latest_ts.get("acwr_percent"),
            "load_aerobic_low": latest_ts.get("load_aerobic_low"),
            "load_aerobic_high": latest_ts.get("load_aerobic_high"),
            "load_anaerobic": latest_ts.get("load_anaerobic"),
            "load_balance_feedback": latest_ts.get("load_balance_feedback"),
        },
        "vo2_trend": vo2_trend,
        "load_trend": load_trend,
        "efficiency_series": efficiency_series,
        "interference_events": interference_events,
        "interference_warnings": warnings,
        "endurance": {
            "overall": endurance_dto.get("overallScore") or endurance_raw.get("avg"),
            "avg": endurance_raw.get("avg"),
            "max": endurance_raw.get("max"),
        },
        "hill": {
            "overall": latest_hill.get("overallScore") or hill_raw.get("maxScore"),
            "strength": latest_hill.get("strengthScore"),
            "endurance": latest_hill.get("enduranceScore"),
        },
        "lactate": {
            "lthr": prof_d.get("lactate_threshold_hr"),
            "pace": prof_d.get("lactate_threshold_pace"),
            "power_watts": prof_d.get("lactate_threshold_power"),
        },
        "race_predictions": race_predictions,
        "personal_records": formatted_prs,
        "activities": formatted_acts,
    }


def analyze_recovery(conn, settings: Dict[str, Any], days: int = 14) -> Dict[str, Any]:
    """Compute Sleep debt, bedtime consistency SD, HRV baseline, RHR spike watch, stress & BB."""
    today = datetime.now().date()
    start_28 = (today - timedelta(days=27)).isoformat()
    start_win = (today - timedelta(days=days - 1)).isoformat()
    sleep_target_h = float(settings.get("sleep_target_h", 7.0))

    rows_28 = conn.execute(
        "SELECT * FROM daily_wellness WHERE calendar_date >= ? ORDER BY calendar_date ASC",
        (start_28,),
    ).fetchall()
    d28 = [dict(r) for r in rows_28]
    d_win = [d for d in d28 if d["calendar_date"] >= start_win]

    # 7-day sleep debt (over tracked nights only; missing nights never treated as 0h)
    last7 = d28[-7:]
    sleep_nights_7 = [d["sleep_s"] / 3600.0 for d in last7 if d.get("sleep_s")]
    sleep_debt_7d = round(sum(max(0.0, sleep_target_h - h) for h in sleep_nights_7), 2)

    # 14-day bedtime consistency SD (minutes relative to 18:00 local IST = UTC+5:30)
    bed_offsets: List[float] = []
    for d in d28[-14:]:
        ms = d.get("sleep_start_ms")
        if not ms:
            continue
        dt_local = datetime.fromtimestamp(ms / 1000.0)
        mins_day = dt_local.hour * 60 + dt_local.minute
        # Wrap around 18:00 (1080 min) so 23:30 = 330, 01:00 = 420
        rel = (mins_day - 18 * 60) % (24 * 60)
        bed_offsets.append(float(rel))
    bedtime_sd_min = round(statistics.pstdev(bed_offsets), 0) if len(bed_offsets) >= 3 else None

    rhr_vals_28 = [d["rhr"] for d in d28 if d.get("rhr") is not None]
    rhr_baseline = round(statistics.mean(rhr_vals_28), 1) if rhr_vals_28 else None
    latest_rhr = next((d["rhr"] for d in reversed(d28) if d.get("rhr") is not None), None)
    rhr_spike = bool(rhr_baseline and latest_rhr and latest_rhr >= rhr_baseline + 5)

    hrv_vals_28 = [d["hrv_night"] for d in d28 if d.get("hrv_night") is not None]
    hrv_baseline = round(statistics.mean(hrv_vals_28), 1) if hrv_vals_28 else None
    latest_hrv = next((d for d in reversed(d28) if d.get("hrv_night") is not None), {})

    spo2_present = any(d.get("spo2_avg") is not None for d in d28)

    daily_series = []
    for d in d_win:
        dt_obj = date.fromisoformat(d["calendar_date"])
        daily_series.append(
            {
                "date": d["calendar_date"],
                "shortLabel": dt_obj.strftime("%b %-d"),
                "sleepHours": round(d["sleep_s"] / 3600.0, 2) if d.get("sleep_s") else None,
                "sleepScore": d.get("sleep_score"),
                "sleepQualifier": d.get("sleep_qualifier"),
                "deepHours": round((d.get("deep_s") or 0) / 3600.0, 2),
                "remHours": round((d.get("rem_s") or 0) / 3600.0, 2),
                "lightHours": round((d.get("light_s") or 0) / 3600.0, 2),
                "awakeHours": round((d.get("awake_s") or 0) / 3600.0, 2),
                "hrvNight": d.get("hrv_night"),
                "hrvWeekly": d.get("hrv_weekly"),
                "hrv5MinHigh": d.get("hrv_5min_high"),
                "hrvStatus": d.get("hrv_status"),
                "rhr": d.get("rhr"),
                "stressAvg": d.get("stress_avg"),
                "stressMax": d.get("stress_max"),
                "bbCharged": d.get("bb_charged"),
                "bbDrained": d.get("bb_drained"),
                "bbPeak": d.get("bb_peak"),
                "bbLow": d.get("bb_low"),
                "respSleep": d.get("resp_sleep"),
                "respWake": d.get("resp_wake"),
                "vigorousMin": d.get("im_vigorous") or 0,
            }
        )

    return {
        "days": days,
        "sleep_target_h": sleep_target_h,
        "summary": {
            "avg_sleep_h": round(statistics.mean(sleep_nights_7), 2) if sleep_nights_7 else None,
            "nights_tracked_7d": len(sleep_nights_7),
            "nights_under_5h_win": sum(1 for d in d_win if d.get("sleep_s") and d["sleep_s"] < 5 * 3600),
            "sleep_debt_7d_h": sleep_debt_7d,
            "bedtime_sd_min": bedtime_sd_min,
            "avg_sleep_score": round(
                statistics.mean([d["sleep_score"] for d in d_win if d.get("sleep_score") is not None]), 0
            )
            if any(d.get("sleep_score") is not None for d in d_win)
            else None,
            "rhr_latest": latest_rhr,
            "rhr_baseline_28d": rhr_baseline,
            "rhr_spike_alert": rhr_spike,
            "hrv_latest": latest_hrv.get("hrv_night"),
            "hrv_weekly": latest_hrv.get("hrv_weekly"),
            "hrv_status": latest_hrv.get("hrv_status"),
            "hrv_baseline_28d": hrv_baseline,
            "spo2_available": spo2_present,
            "spo2_hint": None
            if spo2_present
            else "SpO2 is currently null — enable Pulse Ox (During Sleep) on your Forerunner 965 to capture overnight blood oxygen.",
        },
        "daily": daily_series,
    }


def analyze_body(conn, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Compute EWMA trend weight, 14-day rate, FFMI/nFFMI, Navy BF%, tape ratios, and photos."""
    prof = conn.execute("SELECT height_cm, weight_kg, gender FROM athlete_profile WHERE id = 1").fetchone()
    height_cm = float(prof["height_cm"]) if prof and prof["height_cm"] else 162.6
    height_m = height_cm / 100.0
    gender = (prof["gender"] if prof and prof["gender"] else "MALE").upper()

    rows = conn.execute(
        "SELECT * FROM body_measurements ORDER BY calendar_date ASC, recorded_at ASC"
    ).fetchall()
    entries = [dict(r) for r in rows]

    # Weight series (latest per date for EWMA)
    by_date_weight: Dict[str, Dict[str, Any]] = {}
    for e in entries:
        if e.get("weight_kg"):
            by_date_weight[e["calendar_date"]] = e

    weight_series = []
    ewma: Optional[float] = None
    alpha = 0.25
    for cdate in sorted(by_date_weight.keys()):
        w = float(by_date_weight[cdate]["weight_kg"])
        ewma = w if ewma is None else (alpha * w + (1.0 - alpha) * ewma)
        weight_series.append(
            {
                "date": cdate,
                "weight_kg": round(w, 2),
                "trend_kg": round(ewma, 2),
                "body_fat_pct": by_date_weight[cdate].get("body_fat_pct"),
                "source": by_date_weight[cdate].get("source"),
            }
        )

    latest_w = weight_series[-1]["weight_kg"] if weight_series else (float(prof["weight_kg"]) if prof and prof["weight_kg"] else 73.0)
    latest_trend = weight_series[-1]["trend_kg"] if weight_series else latest_w

    # 14-day linear rate gated on >= 4 weigh-ins in trailing 14 days
    cutoff_14 = (datetime.now().date() - timedelta(days=13)).isoformat()
    recent_w = [x for x in weight_series if x["date"] >= cutoff_14]
    rate_kg_week: Optional[float] = None
    rate_pct_month: Optional[float] = None
    if len(recent_w) >= 4:
        d0 = date.fromisoformat(recent_w[0]["date"])
        xs = [(date.fromisoformat(x["date"]) - d0).days for x in recent_w]
        ys = [x["trend_kg"] for x in recent_w]
        mx = statistics.mean(xs)
        my = statistics.mean(ys)
        denom = sum((x - mx) ** 2 for x in xs)
        if denom > 0:
            slope_day = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
            rate_kg_week = round(slope_day * 7.0, 2)
            rate_pct_month = round((slope_day * 30.0 / latest_trend) * 100.0, 2)

    # Latest tape measurements
    tapes = [
        e
        for e in reversed(entries)
        if any(e.get(k) is not None for k in ("waist_cm", "chest_cm", "arm_cm", "thigh_cm", "shoulder_cm", "neck_cm"))
    ]
    latest_tape = tapes[0] if tapes else {}

    # Body fat % (explicit measured or Navy estimate)
    measured_bf = next(
        ((e["body_fat_pct"], e.get("body_fat_source") or e["source"]) for e in reversed(entries) if e.get("body_fat_pct") is not None),
        (None, None),
    )
    navy_bf: Optional[float] = None
    if latest_tape.get("waist_cm") and latest_tape.get("neck_cm"):
        waist = float(latest_tape["waist_cm"])
        neck = float(latest_tape["neck_cm"])
        if waist > neck and height_cm > 0:
            if gender == "MALE":
                navy_bf = round(
                    495.0 / (1.0324 - 0.19077 * math.log10(waist - neck) + 0.15456 * math.log10(height_cm)) - 450.0,
                    1,
                )

    bf_val = measured_bf[0] if measured_bf[0] is not None else navy_bf
    bf_source = measured_bf[1] if measured_bf[0] is not None else ("navy_tape_estimate (±3.5%)" if navy_bf is not None else None)

    ffmi = None
    nffmi = None
    ffm_kg = None
    if bf_val is not None and 3.0 <= bf_val <= 55.0:
        ffm_kg = round(latest_trend * (1.0 - bf_val / 100.0), 1)
        ffmi = round(ffm_kg / (height_m ** 2), 1)
        nffmi = round(ffmi + 6.1 * (1.8 - height_m), 1)

    waist_arm = (
        round(float(latest_tape["waist_cm"]) / float(latest_tape["arm_cm"]), 2)
        if latest_tape.get("waist_cm") and latest_tape.get("arm_cm")
        else None
    )
    waist_chest = (
        round(float(latest_tape["waist_cm"]) / float(latest_tape["chest_cm"]), 2)
        if latest_tape.get("waist_cm") and latest_tape.get("chest_cm")
        else None
    )

    photos = [
        dict(p)
        for p in conn.execute(
            "SELECT * FROM progress_photos ORDER BY calendar_date DESC, id DESC"
        ).fetchall()
    ]

    return {
        "height_cm": height_cm,
        "latest_weight_kg": latest_w,
        "trend_weight_kg": latest_trend,
        "weigh_ins_14d": len(recent_w),
        "rate_kg_week": rate_kg_week,
        "rate_pct_month": rate_pct_month,
        "target_gain_pct_month": settings.get("gain_rate_pct_month", 0.75),
        "body_fat_pct": bf_val,
        "body_fat_source": bf_source,
        "navy_bf_pct": navy_bf,
        "ffm_kg": ffm_kg,
        "ffmi": ffmi,
        "nffmi": nffmi,
        "waist_arm_ratio": waist_arm,
        "waist_chest_ratio": waist_chest,
        "latest_tape": latest_tape,
        "tape_history": tapes[:12],
        "weight_series": weight_series,
        "photos": photos,
    }


def analyze_fuel(conn, settings: Dict[str, Any], days: int = 14) -> Dict[str, Any]:
    """Compute Protein compliance, Energy Balance, Adaptive TDEE, and Hydration vs Sweat Loss."""
    today = datetime.now().date()
    start_s = (today - timedelta(days=days - 1)).isoformat()
    week_start = monday_of_week(today).isoformat()

    bw_kg = _latest_weight_kg(conn) or 73.0
    protein_min_g = round(bw_kg * float(settings.get("protein_g_per_kg", 1.6)), 0)
    protein_max_g = round(bw_kg * float(settings.get("protein_max_g_per_kg", 2.2)), 0)
    cal_target = float(settings.get("calorie_target", 2600))

    nut_rows = conn.execute(
        """
        SELECT calendar_date,
               SUM(calories) AS calories,
               SUM(protein_g) AS protein_g,
               SUM(carbs_g) AS carbs_g,
               SUM(fat_g) AS fat_g,
               COUNT(*) AS entry_count
        FROM nutrition_logs
        WHERE calendar_date >= ?
        GROUP BY calendar_date
        ORDER BY calendar_date ASC
        """,
        (start_s,),
    ).fetchall()
    nut_map = {r["calendar_date"]: dict(r) for r in nut_rows}

    well_rows = conn.execute(
        """
        SELECT calendar_date, total_kcal, active_kcal, hydration_intake_ml, hydration_goal_ml, hydration_sweat_ml
        FROM daily_wellness
        WHERE calendar_date >= ?
        ORDER BY calendar_date ASC
        """,
        (start_s,),
    ).fetchall()
    well_map = {r["calendar_date"]: dict(r) for r in well_rows}

    dates = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
    daily_fuel = []
    protein_days_week = 0
    logged_days_win = 0
    for ds in dates:
        n = nut_map.get(ds) or {}
        w = well_map.get(ds) or {}
        p_g = round(float(n.get("protein_g") or 0.0), 1)
        kcal = round(float(n.get("calories") or 0.0), 0)
        has_log = (n.get("entry_count") or 0) > 0
        if has_log:
            logged_days_win += 1
        hit_protein = has_log and p_g >= protein_min_g
        if ds >= week_start and hit_protein:
            protein_days_week += 1
        daily_fuel.append(
            {
                "date": ds,
                "shortLabel": date.fromisoformat(ds).strftime("%b %-d"),
                "calories": kcal if has_log else None,
                "protein_g": p_g if has_log else None,
                "carbs_g": round(float(n.get("carbs_g") or 0.0), 1) if has_log else None,
                "fat_g": round(float(n.get("fat_g") or 0.0), 1) if has_log else None,
                "hit_protein": hit_protein,
                "burn_kcal": round(float(w.get("total_kcal") or 0.0), 0) or None,
                "active_kcal": round(float(w.get("active_kcal") or 0.0), 0) or None,
                "hydration_ml": round(float(w.get("hydration_intake_ml") or 0.0), 0),
                "hydration_goal_ml": round(float(w.get("hydration_goal_ml") or 3500.0), 0),
                "sweat_loss_ml": round(float(w.get("hydration_sweat_ml") or 0.0), 0),
            }
        )

    # Adaptive TDEE (PRD §7.9: requires >= 14 days with >= 80% logged + trend weight span)
    adaptive_tdee: Optional[int] = None
    body_info = analyze_body(conn, settings)
    w_series = body_info["weight_series"]
    tdee_coverage_pct = round((logged_days_win / max(days, 1)) * 100.0, 0)
    if days >= 14 and logged_days_win >= int(days * 0.8) and len(w_series) >= 4:
        cal_vals = [d["calories"] for d in daily_fuel if d["calories"] is not None]
        if cal_vals:
            avg_in = statistics.mean(cal_vals)
            delta_kg = w_series[-1]["trend_kg"] - w_series[0]["trend_kg"]
            span = max((date.fromisoformat(w_series[-1]["date"]) - date.fromisoformat(w_series[0]["date"])).days, 7)
            adaptive_tdee = round(avg_in - (delta_kg * 7700.0 / span))

    recent_logs = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM nutrition_logs ORDER BY calendar_date DESC, id DESC LIMIT 30"
        ).fetchall()
    ]

    prof = conn.execute("SELECT profile_json FROM athlete_profile WHERE id = 1").fetchone()
    prof_raw = _safe_json(prof["profile_json"] if prof else None, {})
    containers = ((prof_raw.get("userData") or {}).get("hydrationContainers") or [
        {"name": "Cup", "volume": 320, "unit": "milliliter"},
        {"name": "Bottle", "volume": 500, "unit": "milliliter"},
        {"name": "Shaker", "volume": 750, "unit": "milliliter"},
    ])

    return {
        "days": days,
        "bodyweight_kg": bw_kg,
        "protein_target_min_g": protein_min_g,
        "protein_target_max_g": protein_max_g,
        "calorie_target": cal_target,
        "protein_days_week": protein_days_week,
        "logged_days_window": logged_days_win,
        "tdee_coverage_pct": tdee_coverage_pct,
        "adaptive_tdee_kcal": adaptive_tdee,
        "adaptive_tdee_ready": adaptive_tdee is not None,
        "containers": containers,
        "daily": daily_fuel,
        "recent_logs": recent_logs,
    }


def evaluate_session_recommendation(
    today_wellness: Dict[str, Any],
    recovery: Dict[str, Any],
    strength: Dict[str, Any],
    engine: Dict[str, Any],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """PRD §7.6 ordered rule engine R0 -> R5."""
    illness = bool(settings.get("illness_mode", False))
    readiness = today_wellness.get("readiness_score")
    rec_h = today_wellness.get("readiness_recovery_h") or 0.0
    sleep_s = today_wellness.get("sleep_s")
    sleep_h = round(sleep_s / 3600.0, 2) if sleep_s else None
    hrv_status = today_wellness.get("hrv_status")
    rhr = today_wellness.get("rhr")
    rhr_base = recovery["summary"].get("rhr_baseline_28d")
    sleep_debt = recovery["summary"].get("sleep_debt_7d_h") or 0.0
    acwr = today_wellness.get("acwr") or engine["training_status"].get("acwr")

    missing_inputs: List[str] = []
    if readiness is None:
        missing_inputs.append("Training Readiness")
    if sleep_h is None:
        missing_inputs.append("Last Night's Sleep")
    if hrv_status is None:
        missing_inputs.append("HRV Status")

    confidence = "HIGH" if not missing_inputs else ("MEDIUM" if len(missing_inputs) == 1 else "LOW")

    # Pick lagging, rested (>= 48h / >= 2 days) target muscle
    candidates = [
        m
        for m in strength["muscle_volume"]
        if m["muscle"] in CORE_MUSCLES_KEY and (m["days_since"] is None or m["days_since"] >= 2)
    ]
    candidates.sort(key=lambda m: (m["fractional_sets"], -(m["days_since"] or 999)))
    target_muscle = candidates[0]["label"] if candidates else "Full Body"
    target_detail = (
        f"{candidates[0]['label']} ({candidates[0]['fractional_sets']}/{candidates[0]['target_min']} sets this week, "
        + (f"{candidates[0]['days_since']}d since last trained)" if candidates[0]["days_since"] is not None else "0 sessions logged yet)")
        if candidates
        else "All muscles hit recently"
    )

    reasons: List[str] = []
    if readiness is not None:
        reasons.append(f"Readiness {readiness}/100 ({today_wellness.get('readiness_level') or 'N/A'}, {today_wellness.get('readiness_context') or 'latest'})")
    if sleep_h is not None:
        reasons.append(f"Sleep {sleep_h}h (score {today_wellness.get('sleep_score') or '--'}), 7d debt {sleep_debt}h")
    if today_wellness.get("hrv_night"):
        reasons.append(f"HRV {today_wellness['hrv_night']} ms (weekly avg {today_wellness.get('hrv_weekly') or '--'}, {hrv_status or 'N/A'})")
    if rec_h:
        reasons.append(f"Garmin recovery time remaining: {rec_h}h")
    if acwr:
        reasons.append(f"ACWR {acwr} ({today_wellness.get('acwr_status') or 'N/A'})")

    rule_id = "R4"
    severity = "emerald"
    verdict = f"HEAVY LIFT: {target_muscle.upper()}"
    sub_verdict = "Push progressive overload. Hard cardio OK if separated from lower-body work by ≥ 6h."

    # R0
    if illness or (rhr_base and rhr and rhr >= rhr_base + 7 and hrv_status == "LOW"):
        rule_id = "R0"
        severity = "crimson"
        verdict = "FULL REST"
        sub_verdict = "Illness flag active or severe autonomic strain (RHR spike + LOW HRV). Focus on sleep, fluids, and food."
    # R1
    elif (readiness is not None and readiness < float(settings.get("readiness_rest_max", 25))) or (sleep_h is not None and sleep_h < 5.0):
        rule_id = "R1"
        severity = "crimson"
        verdict = "REST / MOBILITY ONLY"
        sub_verdict = "Readiness below 25 or severe sleep restriction (<5h). Save CNS & recovery for tomorrow."
    # R2
    elif (readiness is not None and readiness < float(settings.get("readiness_moderate_min", 50))) or rec_h > 36.0:
        rule_id = "R2"
        severity = "amber"
        verdict = "ACTIVE RECOVERY / Z2 ≤ 40 MIN (LIGHT UPPER PUMP OK)"
        sub_verdict = f"High residual fatigue ({rec_h}h recovery left). Avoid heavy axial loading or Z4+ running."
    # R3
    elif (
        (readiness is not None and readiness < float(settings.get("readiness_heavy_min", 70)))
        or hrv_status == "UNBALANCED"
        or sleep_debt > 5.0
    ):
        rule_id = "R3"
        severity = "amber"
        verdict = f"MODERATE LIFT: {target_muscle.upper()} (NO HARD CARDIO)"
        sub_verdict = f"Target lagging rested area: {target_detail}. Keep 1–2 reps in reserve; keep cardio in Z2."
    else:
        reasons.append(f"Target priority: {target_detail}")

    # R5 ACWR cap
    if acwr and float(acwr) > float(settings.get("acwr_danger", 1.5)) and severity == "emerald":
        rule_id = "R5"
        severity = "amber"
        verdict = f"CAP TO MODERATE: {target_muscle.upper()} (ACWR SPIKE {acwr})"
        sub_verdict = "Workload ratio > 1.5 increases injury & interference risk. Trim total volume ~20%."

    return {
        "rule_id": rule_id,
        "severity": severity,
        "verdict": verdict,
        "sub_verdict": sub_verdict,
        "target_muscle": target_muscle,
        "reasons": reasons[:5],
        "confidence": confidence,
        "missing_inputs": missing_inputs,
    }


def compute_weekly_forge_score(
    strength: Dict[str, Any],
    engine: Dict[str, Any],
    recovery: Dict[str, Any],
    fuel: Dict[str, Any],
    settings: Dict[str, Any],
) -> Dict[str, Any]:
    """PRD §3.3 & §7.8 Weekly Forge Score (0-100) with transparent re-weighting."""
    set_min = int(settings.get("muscle_set_min", 10))
    lift_target = int(settings.get("lifting_freq_target", 4))
    z2_target = float(settings.get("z2_target_pct", 75))
    sleep_target = float(settings.get("sleep_target_h", 7.0))

    # Train pillar (weight 40)
    core_muscles = [m for m in strength["muscle_volume"] if m["muscle"] in CORE_MUSCLES_KEY]
    muscles_hit = sum(1 for m in core_muscles if m["fractional_sets"] >= set_min)
    muscle_score = muscles_hit / max(len(core_muscles), 1)
    freq_score = min(1.0, strength["summary"]["sessions_this_week"] / max(lift_target, 1))
    z2_pct = engine["zones_week"]["z2_discipline_pct"]
    z2_score = min(1.0, (z2_pct or 0.0) / max(z2_target, 1.0)) if z2_pct is not None else 0.5
    train_pct = round((0.5 * muscle_score + 0.3 * freq_score + 0.2 * z2_score) * 100.0)

    # Recover pillar (weight 35)
    last7 = recovery["daily"][-7:]
    nights_hit = sum(1 for d in last7 if d["sleepHours"] is not None and d["sleepHours"] >= sleep_target)
    sleep_ratio = min(1.0, nights_hit / 5.0)
    hrv_st = recovery["summary"].get("hrv_status")
    hrv_score = 1.0 if hrv_st == "BALANCED" else (0.65 if hrv_st == "UNBALANCED" else (0.35 if hrv_st == "LOW" else 0.7))
    recover_pct = round((0.65 * sleep_ratio + 0.35 * hrv_score) * 100.0)

    # Fuel pillar (weight 25) - excluded & re-weighted if 0 nutrition logs in week
    fuel_logged_days = sum(1 for d in fuel["daily"][-7:] if d["calories"] is not None or d["protein_g"] is not None)
    excluded_pillars: List[str] = []
    if fuel_logged_days == 0:
        excluded_pillars.append("fuel")
        fuel_pct = None
        overall = round((train_pct * 40.0 + recover_pct * 35.0) / 75.0)
    else:
        fuel_pct = round(min(1.0, fuel["protein_days_week"] / 5.0) * 100.0)
        overall = round(train_pct * 0.40 + fuel_pct * 0.25 + recover_pct * 0.35)

    return {
        "overall": overall,
        "train_pct": train_pct,
        "fuel_pct": fuel_pct,
        "recover_pct": recover_pct,
        "excluded_pillars": excluded_pillars,
        "muscles_at_target": f"{muscles_hit}/{len(core_muscles)}",
        "lifts_this_week": f"{strength['summary']['sessions_this_week']}/{lift_target}",
        "sleep_nights_hit": f"{nights_hit}/7",
        "protein_days_hit": f"{fuel['protein_days_week']}/7",
    }


def audit_hr_zones(conn) -> Dict[str, Any]:
    """PRD §6.9 / §7.12: Compare configured Garmin HR zones vs measured 7d RHR, 90d max HR, LTHR."""
    prof = conn.execute("SELECT hr_zones_json, lactate_threshold_hr FROM athlete_profile WHERE id = 1").fetchone()
    zones = _safe_json(prof["hr_zones_json"] if prof else None, [])
    default_zone = next((z for z in zones if isinstance(z, dict) and z.get("sport") == "DEFAULT"), None) or (zones[0] if zones else {})

    today = datetime.now().date()
    r7 = conn.execute(
        "SELECT rhr FROM daily_wellness WHERE calendar_date >= ? AND rhr IS NOT NULL",
        ((today - timedelta(days=6)).isoformat(),),
    ).fetchall()
    rhr_7d = round(statistics.mean([r["rhr"] for r in r7])) if r7 else None

    obs_max_row = conn.execute(
        "SELECT MAX(max_hr) AS m FROM activities WHERE calendar_date >= ?",
        ((today - timedelta(days=89)).isoformat(),),
    ).fetchone()
    obs_max_90d = round(obs_max_row["m"]) if obs_max_row and obs_max_row["m"] else None

    used_rhr = default_zone.get("restingHeartRateUsed")
    used_max = default_zone.get("maxHeartRateUsed")
    lthr = default_zone.get("lactateThresholdHeartRateUsed") or (prof["lactate_threshold_hr"] if prof else None)
    method = default_zone.get("trainingMethod")

    rhr_stale = bool(used_rhr and rhr_7d and abs(used_rhr - rhr_7d) > 4)
    max_stale = bool(used_max and obs_max_90d and abs(used_max - obs_max_90d) > 5)

    return {
        "sport": default_zone.get("sport", "DEFAULT"),
        "training_method": method,
        "configured_rhr": used_rhr,
        "measured_rhr_7d": rhr_7d,
        "rhr_auto_update": default_zone.get("restingHrAutoUpdateUsed"),
        "configured_max_hr": used_max,
        "observed_max_hr_90d": obs_max_90d,
        "configured_lthr": lthr,
        "floors": [default_zone.get(f"zone{i}Floor") for i in range(1, 6)],
        "is_stale": rhr_stale or max_stale,
        "rhr_stale": rhr_stale,
        "max_stale": max_stale,
        "recommendation": (
            f"Switch to LTHR-based zones (LTHR {lthr or 186} bpm) or update RHR {used_rhr}→{rhr_7d} and Max HR {used_max}→{obs_max_90d}."
            if (rhr_stale or max_stale)
            else "HR zones align closely with recent physiological measurements."
        ),
    }


def build_today_payload(conn, db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """Assemble Today: Readiness Cockpit (PRD §6.1)."""
    settings = get_settings(conn)
    strength = analyze_strength(conn, settings)
    engine = analyze_engine(conn, settings, days=14)
    recovery = analyze_recovery(conn, settings, days=14)
    body = analyze_body(conn, settings)
    fuel = analyze_fuel(conn, settings, days=7)
    hr_audit = audit_hr_zones(conn)

    # Pick latest wellness day with data (prefer today if any readiness/summary exists)
    rows = conn.execute("SELECT * FROM daily_wellness ORDER BY calendar_date DESC LIMIT 28").fetchall()
    latest = dict(rows[0]) if rows else {}
    latest_date = latest.get("calendar_date") or datetime.now().date().isoformat()

    # If today's readiness or sleep is missing, also look up yesterday for fallback display while marking date
    latest_ready = next((dict(r) for r in rows if r["readiness_score"] is not None), latest)
    latest_sleep = next((dict(r) for r in rows if r["sleep_s"] is not None), latest)
    latest_hrv = next((dict(r) for r in rows if r["hrv_night"] is not None), latest)

    # Merge best current snapshot cleanly
    snap = dict(latest)
    if snap.get("readiness_score") is None and latest_ready:
        snap["readiness_score"] = latest_ready.get("readiness_score")
        snap["readiness_level"] = latest_ready.get("readiness_level")
        snap["readiness_context"] = latest_ready.get("readiness_context")
        snap["readiness_recovery_h"] = latest_ready.get("readiness_recovery_h")
    if snap.get("sleep_s") is None and latest_sleep:
        snap["sleep_s"] = latest_sleep.get("sleep_s")
        snap["sleep_score"] = latest_sleep.get("sleep_score")
    if snap.get("hrv_night") is None and latest_hrv:
        snap["hrv_night"] = latest_hrv.get("hrv_night")
        snap["hrv_weekly"] = latest_hrv.get("hrv_weekly")
        snap["hrv_status"] = latest_hrv.get("hrv_status")

    recommendation = evaluate_session_recommendation(snap, recovery, strength, engine, settings)
    forge_score = compute_weekly_forge_score(strength, engine, recovery, fuel, settings)

    # Bio-Health Index (preserves compatibility with original dashboard hero ring!)
    bio_sleep = recovery["summary"]["avg_sleep_score"] or 70
    hrv_st = recovery["summary"]["hrv_status"] or "BALANCED"
    bio_recovery = 90 if hrv_st == "BALANCED" else (68 if hrv_st == "UNBALANCED" else (45 if hrv_st == "LOW" else 75))
    d7 = [dict(r) for r in rows[:7]]
    tot_im = sum((d.get("im_moderate") or 0) + 2 * (d.get("im_vigorous") or 0) for d in d7)
    im_ratio = min(tot_im / 150.0, 1.15) if d7 else 0.5
    step_ratios = [min((d.get("steps") or 0) / max(d.get("step_goal") or 10000, 1), 1.2) for d in d7]
    bio_activity = round(min(100, (im_ratio * 0.55 + (statistics.mean(step_ratios) if step_ratios else 0.7) * 0.45) * 92))
    stress_vals = [d["stress_avg"] for d in d7 if d.get("stress_avg") is not None]
    bio_autonomic = round(max(20, min(100, 108 - (statistics.mean(stress_vals) if stress_vals else 30.0))))
    bio_overall = round((bio_sleep + bio_recovery + bio_activity + bio_autonomic) / 4.0)

    # Sparklines (7 days ascending)
    d7_asc = list(reversed(d7))
    spark = {
        "readiness": [d.get("readiness_score") for d in d7_asc],
        "sleep": [round(d["sleep_s"] / 3600.0, 2) if d.get("sleep_s") else None for d in d7_asc],
        "hrv": [d.get("hrv_night") for d in d7_asc],
        "rhr": [d.get("rhr") for d in d7_asc],
        "stress": [d.get("stress_avg") for d in d7_asc],
        "steps": [d.get("steps") for d in d7_asc],
    }

    # Data quality alerts (PRD §6.1 T-5)
    alerts: List[Dict[str, Any]] = []
    if strength["summary"]["total_triage_count"] > 0:
        alerts.append(
            {
                "id": "strength_triage",
                "severity": "amber",
                "title": f"{strength['summary']['total_triage_count']} strength sets need review ({strength['summary']['unclassified_count']} unclassified)",
                "cta": "Fix in Strength Lab",
                "route": "strength",
            }
        )
    if hr_audit["is_stale"]:
        alerts.append(
            {
                "id": "hr_zones_stale",
                "severity": "amber",
                "title": f"HR zones stale (configured RHR {hr_audit['configured_rhr']} vs measured {hr_audit['measured_rhr_7d']} bpm)",
                "cta": "Audit in Settings",
                "route": "settings",
            }
        )
    if body["weigh_ins_14d"] < 4:
        alerts.append(
            {
                "id": "weigh_ins_sparse",
                "severity": "cyan",
                "title": f"Only {body['weigh_ins_14d']}/4 weigh-ins in 14d — EWMA gain rate needs more data",
                "cta": "Log Weight",
                "route": "body",
            }
        )
    if fuel["logged_days_window"] == 0:
        alerts.append(
            {
                "id": "nutrition_empty",
                "severity": "cyan",
                "title": "0 nutrition logs — quick-log daily protein (1 tap) to unlock Fuel scoring",
                "cta": "Log Protein",
                "route": "fuel",
            }
        )
    if engine["interference_warnings"]:
        alerts.append(
            {
                "id": "interference",
                "severity": "amber",
                "title": engine["interference_warnings"][0],
                "cta": "Inspect Engine",
                "route": "engine",
            }
        )

    # Intraday readiness resets for latest date
    r_entries = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM readiness_entries WHERE calendar_date = ? ORDER BY timestamp ASC",
            (latest_ready.get("calendar_date") or latest_date,),
        ).fetchall()
    ]

    prof = conn.execute("SELECT * FROM athlete_profile WHERE id = 1").fetchone()
    prof_d = dict(prof) if prof else {}

    return {
        "date": latest_date,
        "athlete": {
            "name": prof_d.get("full_name") or "Ayush Kaushik",
            "device": prof_d.get("device_name") or "Forerunner 965",
            "weight_kg": body["latest_weight_kg"],
            "height_cm": prof_d.get("height_cm") or 162.6,
            "vo2_max": prof_d.get("vo2_max_running") or 44.0,
            "lthr": prof_d.get("lactate_threshold_hr") or 186,
            "lt_pace": prof_d.get("lactate_threshold_pace"),
        },
        "sync": get_sync_state(),
        "recommendation": recommendation,
        "forge_score": forge_score,
        "bio_health_index": {
            "overall": bio_overall,
            "pillars": {
                "sleep": bio_sleep,
                "recovery": bio_recovery,
                "activity": bio_activity,
                "autonomic": bio_autonomic,
            },
        },
        "vitals": {
            "readiness": snap.get("readiness_score"),
            "readiness_level": snap.get("readiness_level"),
            "readiness_context": snap.get("readiness_context"),
            "recovery_time_h": snap.get("readiness_recovery_h"),
            "sleep_h": round(snap["sleep_s"] / 3600.0, 2) if snap.get("sleep_s") else None,
            "sleep_score": snap.get("sleep_score"),
            "sleep_debt_7d_h": recovery["summary"]["sleep_debt_7d_h"],
            "hrv_night": snap.get("hrv_night"),
            "hrv_weekly": snap.get("hrv_weekly"),
            "hrv_status": snap.get("hrv_status"),
            "rhr": snap.get("rhr"),
            "rhr_baseline_28d": recovery["summary"]["rhr_baseline_28d"],
            "bb_peak": snap.get("bb_peak"),
            "bb_low": snap.get("bb_low"),
            "bb_charged": snap.get("bb_charged"),
            "bb_drained": snap.get("bb_drained"),
            "stress_avg": snap.get("stress_avg"),
            "acwr": engine["training_status"].get("acwr"),
            "acwr_status": engine["training_status"].get("acwr_status"),
            "acute_load": engine["training_status"].get("acute_load"),
            "steps_today": snap.get("steps"),
            "step_goal": snap.get("step_goal") or 10000,
        },
        "sparklines": spark,
        "muscle_recency": strength["muscle_volume"],
        "alerts": alerts,
        "readiness_timeline": r_entries,
        "recent_activities": engine["activities"][:6],
    }


def build_progress_payload(conn) -> Dict[str, Any]:
    """Assemble Progress: Weekly Review, Monthly Summary, Roadmap Phases, Streaks & Badges."""
    settings = get_settings(conn)
    strength = analyze_strength(conn, settings)
    engine = analyze_engine(conn, settings, days=30)
    recovery = analyze_recovery(conn, settings, days=30)
    body = analyze_body(conn, settings)
    fuel = analyze_fuel(conn, settings, days=14)
    forge_score = compute_weekly_forge_score(strength, engine, recovery, fuel, settings)

    # Wins & Misses
    wins: List[str] = []
    misses: List[str] = []
    focus_items: List[str] = []

    pr_exs = [e for e in strength["exercises_progress"] if e["overload_status"] == "pr"]
    if pr_exs:
        wins.append(f"New overload PR on {pr_exs[0]['exercise'].replace('_', ' ').title()}")
    if engine["training_status"].get("acwr_status") == "OPTIMAL":
        wins.append(f"Training load status is {engine['training_status'].get('training_status') or 'OPTIMAL'} (ACWR {engine['training_status'].get('acwr')})")
    if recovery["summary"].get("hrv_status") == "BALANCED":
        wins.append(f"Overnight HRV is BALANCED ({recovery['summary'].get('hrv_weekly')} ms weekly avg)")

    lagging = [m for m in strength["missing_volume_plan"] if m["done"] < 3]
    if lagging:
        top_lag = ", ".join(m["label"] for m in lagging[:4])
        misses.append(f"Zero or minimal sets on: {top_lag}")
        focus_items.append(f"Add a Lower/Delt/Arm session hitting {lagging[0]['label']} ({int(lagging[0]['needed'])} sets needed)")

    z2_pct = engine["zones_week"]["z2_discipline_pct"]
    if z2_pct is not None and z2_pct < float(settings.get("z2_target_pct", 75)):
        misses.append(f"Weekly Z2 discipline is {z2_pct}% vs {settings.get('z2_target_pct', 75)}% target")
        focus_items.append("Keep 2 easy runs strictly under Z3 ceiling (HR < 144 bpm) to build aerobic low load")

    avg_slp = recovery["summary"].get("avg_sleep_h")
    if avg_slp and avg_slp < float(settings.get("sleep_target_h", 7.0)):
        misses.append(f"7-day avg sleep is {avg_slp}h (debt {recovery['summary']['sleep_debt_7d_h']}h)")
        focus_items.append("Protect a consistent lights-out window to hit ≥ 7.0h/night")

    if body["weigh_ins_14d"] < 4 or fuel["logged_days_window"] < 5:
        focus_items.append("Use Quick Log 4×/week for morning weight + daily protein grams")

    # Roadmap (PRD §6.7 Phases 1–3)
    bw = body["latest_weight_kg"] or 73.0
    rel = {r["lift"]: r["bw_ratio"] for r in strength["relative_strength"]}
    vo2 = (engine["vo2_trend"][-1]["vo2_max"] if engine["vo2_trend"] else None) or 43.8
    roadmap = [
        {
            "phase": "Phase 1: Foundation",
            "window": "Months 0–6",
            "targets": [
                {"label": "Lifting Frequency ≥ 3–4/wk", "current": f"{strength['summary']['sessions_this_week']}/wk", "pct": min(100, round(strength["summary"]["sessions_this_week"] / 4 * 100))},
                {"label": "Sleep Avg ≥ 7.0 h", "current": f"{avg_slp or '--'} h", "pct": min(100, round(((avg_slp or 0) / 7.0) * 100))},
                {"label": "Z2 Running Discipline ≥ 75%", "current": f"{z2_pct or 0}%", "pct": min(100, round(((z2_pct or 0) / 75.0) * 100))},
                {"label": "Bench 0.75×BW / Squat 1.0×BW / DL 1.25×BW", "current": f"B:{rel.get('Bench Press') or '--'}x S:{rel.get('Squat') or '--'}x", "pct": min(100, round(((rel.get("Bench Press") or 0) / 0.75) * 100))},
                {"label": "VO2 Max ≥ 44", "current": f"{vo2}", "pct": min(100, round((vo2 / 44.0) * 100))},
            ],
        },
        {
            "phase": "Phase 2: Build",
            "window": "Months 6–18",
            "targets": [
                {"label": "All Major Muscles 10–20 sets/wk", "current": forge_score["muscles_at_target"], "pct": round(int(forge_score["muscles_at_target"].split("/")[0]) / 10 * 100)},
                {"label": "Bench 1.0×BW · Squat 1.5×BW · DL 2.0×BW", "current": f"{bw} kg BW", "pct": min(100, round(((rel.get("Bench Press") or 0) / 1.0) * 100))},
                {"label": "VO2 Max ≥ 47 & Sub-25:00 5K", "current": f"VO2 {vo2}", "pct": min(100, round((vo2 / 47.0) * 100))},
                {"label": "Normalized FFMI +1.5", "current": f"{body['nffmi'] or 'Needs BF%'}", "pct": 30 if body["nffmi"] else 0},
            ],
        },
        {
            "phase": "Phase 3: Hybrid Athlete",
            "window": "18+ Months",
            "targets": [
                {"label": "Bench 1.25×BW · Squat 1.75×BW · DL 2.25×BW", "current": "Long-horizon", "pct": min(100, round(((rel.get("Bench Press") or 0) / 1.25) * 100))},
                {"label": "Sub-1:55 Half Marathon / HYROX ready", "current": "HM PR 2:17:12", "pct": 55},
                {"label": "nFFMI ~23–24 lean physique", "current": f"{body['nffmi'] or 'Log BF%'}", "pct": min(100, round(((body["nffmi"] or 0) / 23.5) * 100)) if body["nffmi"] else 0},
            ],
        },
    ]

    # Habit streaks + Garmin badges
    last30 = recovery["daily"]
    sleep_streak = 0
    for d in reversed(last30):
        if d["sleepHours"] is not None and d["sleepHours"] >= float(settings.get("sleep_target_h", 7.0)):
            sleep_streak += 1
        elif d["sleepHours"] is not None:
            break

    prof = conn.execute("SELECT badges_json FROM athlete_profile WHERE id = 1").fetchone()
    badges_raw = _safe_json(prof["badges_json"] if prof else None, [])
    garmin_badges = [
        {
            "name": b.get("badgeName"),
            "date": (b.get("badgeEarnedDate") or "")[:10],
            "points": b.get("badgePoints"),
            "earned_count": b.get("badgeEarnedNumber"),
        }
        for b in (badges_raw or [])[:12]
        if isinstance(b, dict)
    ]

    # Monthly summary
    monthly_run_km = round(
        sum(a["distanceKm"] for a in engine["activities"] if a["type"] in RUN_TYPES), 1
    )
    monthly_tonnage = round(
        sum(s["tonnage_kg"] for s in strength["session_summaries"] if s["calendar_date"] >= (datetime.now().date() - timedelta(days=29)).isoformat()),
        0,
    )

    return {
        "forge_score": forge_score,
        "weekly_review": {
            "week_start": strength["week_start"],
            "week_end": strength["week_end"],
            "wins": wins or ["Consistent activity tracking online"],
            "misses": misses,
            "focus_items": focus_items[:3],
        },
        "monthly_summary": {
            "run_km_30d": monthly_run_km,
            "strength_tonnage_30d": monthly_tonnage,
            "avg_sleep_h": recovery["summary"]["avg_sleep_h"],
            "hrv_baseline_ms": recovery["summary"]["hrv_baseline_28d"],
            "vo2_latest": vo2,
            "trend_weight_kg": body["trend_weight_kg"],
        },
        "roadmap": roadmap,
        "streaks": {
            "sleep_7h_streak": sleep_streak,
            "protein_days_this_week": fuel["protein_days_week"],
            "lifts_this_week": strength["summary"]["sessions_this_week"],
        },
        "garmin_badges": garmin_badges,
    }


def build_legacy_overview(conn, days: int = 7) -> Dict[str, Any]:
    """Preserve /api/overview?days=7|14|30 contract for backward compatibility."""
    today = datetime.now().date()
    start_s = (today - timedelta(days=days - 1)).isoformat()
    recovery = analyze_recovery(conn, get_settings(conn), days=days)
    engine = analyze_engine(conn, get_settings(conn), days=days)
    fuel = analyze_fuel(conn, get_settings(conn), days=days)
    today_p = build_today_payload(conn)

    rows = conn.execute(
        "SELECT * FROM daily_wellness WHERE calendar_date >= ? ORDER BY calendar_date ASC",
        (start_s,),
    ).fetchall()
    daily = []
    for r in rows:
        d = dict(r)
        dt_obj = date.fromisoformat(d["calendar_date"])
        daily.append(
            {
                "date": d["calendar_date"],
                "label": dt_obj.strftime("%a, %b %-d"),
                "shortLabel": dt_obj.strftime("%b %-d"),
                "steps": d["steps"] or 0,
                "stepGoal": d["step_goal"] or 10000,
                "distanceKm": d["distance_km"] or 0.0,
                "activeCalories": d["active_kcal"] or 0,
                "totalCalories": d["total_kcal"] or 0,
                "bmrCalories": d["bmr_kcal"] or 0,
                "moderateMinutes": d["im_moderate"] or 0,
                "vigorousMinutes": d["im_vigorous"] or 0,
                "intensityMinutes": (d["im_moderate"] or 0) + 2 * (d["im_vigorous"] or 0),
                "restingHr": d["rhr"],
                "stressAvg": d["stress_avg"],
                "bodyBattery": {
                    "charged": d["bb_charged"],
                    "drained": d["bb_drained"],
                    "peak": d["bb_peak"],
                    "low": d["bb_low"],
                },
                "sleep": {
                    "durationHours": round(d["sleep_s"] / 3600.0, 2) if d.get("sleep_s") else None,
                    "score": d["sleep_score"],
                    "deepHours": round((d["deep_s"] or 0) / 3600.0, 2),
                    "remHours": round((d["rem_s"] or 0) / 3600.0, 2),
                    "lightHours": round((d["light_s"] or 0) / 3600.0, 2),
                    "awakeHours": round((d["awake_s"] or 0) / 3600.0, 2),
                },
                "hrv": {
                    "weeklyAvg": d["hrv_weekly"],
                    "lastNightAvg": d["hrv_night"],
                    "status": d["hrv_status"],
                },
                "hydration": {
                    "intakeMl": d["hydration_intake_ml"] or 0,
                    "logged": (d["hydration_intake_ml"] or 0) > 0,
                    "goalMl": d["hydration_goal_ml"] or 3500,
                    "sweatLossMl": d["hydration_sweat_ml"] or 0,
                },
            }
        )

    return {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "range": {
            "days": days,
            "startDate": start_s,
            "endDate": today.isoformat(),
            "todayDate": today.isoformat(),
        },
        "athlete": today_p["athlete"],
        "bioHealthIndex": today_p["bio_health_index"],
        "trainingReadiness": {
            "score": today_p["vitals"]["readiness"],
            "level": today_p["vitals"]["readiness_level"],
            "calendarDate": today_p["date"],
            "acuteLoad": today_p["vitals"]["acute_load"],
            "recoveryTimeMin": (today_p["vitals"]["recovery_time_h"] or 0) * 60,
        },
        "enduranceScore": engine["endurance"],
        "hillScore": engine["hill"],
        "daily": daily,
        "activities": engine["activities"],
        "racePredictions": engine["race_predictions"],
        "personalRecords": engine["personal_records"],
        "fuelSummary": {"proteinDaysWeek": fuel["protein_days_week"]},
        "recoverySummary": recovery["summary"],
    }


def _fmt_race_time(secs: Optional[float]) -> Optional[str]:
    if not secs or secs <= 0:
        return None
    total = int(round(secs))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _fmt_race_pace(secs: Optional[float], dist_km: float) -> Optional[str]:
    if not secs or secs <= 0 or dist_km <= 0:
        return None
    pace_s = int(round(secs / dist_km))
    m, s = divmod(pace_s, 60)
    return f"{m}:{s:02d}/km"


def analyze_tips(conn, settings: Dict[str, Any], reports: Dict[str, Any]) -> Dict[str, Any]:
    """Build Garmin Tips, Coach Signals, Fitness Age, Race Predictions, Endurance/Hill, LT, PRs & Badges."""
    recovery = analyze_recovery(conn, settings, days=14)
    summary = recovery.get("summary") or {}
    vitals = {
        "readiness": summary.get("readiness"),
        "readiness_level": summary.get("readiness_level"),
        "sleep_score": summary.get("sleep_score"),
        "hrv_status": summary.get("hrv_status"),
    }
    today_date = date.today().isoformat()

    tips: List[Dict[str, Any]] = []

    readiness_score = vitals.get("readiness")
    readiness_level = vitals.get("readiness_level") or "UNKNOWN"
    if readiness_score is not None:
        if readiness_score >= 70:
            tips.append({
                "id": "readiness-prime",
                "category": "Readiness",
                "tone": "emerald",
                "title": f"Prime Readiness ({readiness_score}/100 · {readiness_level})",
                "summary": "Your nervous system and recovery markers are primed for high-intensity hypertrophy or threshold cardio.",
                "action": "Push progressive overload on primary compound lifts or run a quality tempo/interval session.",
            })
        elif readiness_score >= 45:
            tips.append({
                "id": "readiness-moderate",
                "category": "Readiness",
                "tone": "amber",
                "title": f"Moderate Readiness ({readiness_score}/100 · {readiness_level})",
                "summary": "Recovery is adequate for controlled volume, but avoid maximal CNS fatigue.",
                "action": "Stick to RPE 7-8 working sets or Zone 2 aerobic base work.",
            })
        else:
            tips.append({
                "id": "readiness-low",
                "category": "Readiness",
                "tone": "rose",
                "title": f"Low Readiness ({readiness_score}/100 · {readiness_level})",
                "summary": "Elevated fatigue or incomplete recovery detected.",
                "action": "Prioritize sleep, hydration, mobility, or an active recovery walk.",
            })

    sleep_score = vitals.get("sleep_score")
    if sleep_score is not None:
        tips.append({
            "id": "sleep-signal",
            "category": "Sleep",
            "tone": "cyan" if sleep_score >= 75 else "amber",
            "title": f"Sleep Quality: {sleep_score}/100",
            "summary": "Deep and REM sleep drive muscle protein synthesis and HRV rebound.",
            "action": "Keep a consistent wake window and aim for 7.5-8.5h tonight." if sleep_score < 80 else "Maintain your current sleep hygiene.",
        })

    hrv_status = vitals.get("hrv_status")
    if hrv_status:
        tips.append({
            "id": "hrv-signal",
            "category": "HRV",
            "tone": "emerald" if str(hrv_status).upper() in ("BALANCED", "GOOD") else "amber",
            "title": f"HRV Status: {hrv_status}",
            "summary": "Autonomic nervous system balance relative to your 7-day baseline.",
            "action": "Balanced HRV supports normal training progression." if str(hrv_status).upper() == "BALANCED" else "Monitor stress and avoid back-to-back high-CNS days.",
        })

    tr_raw = reports.get("trainingReadiness") or {}
    if isinstance(tr_raw, dict) and (tr_raw.get("feedbackShort") or tr_raw.get("feedbackLong")):
        tips.append({
            "id": "garmin-readiness-feedback",
            "category": "Garmin Coach",
            "tone": "cyan",
            "title": str(tr_raw.get("feedbackShort") or "Garmin Readiness Feedback").replace("_", " ").title(),
            "summary": str(tr_raw.get("feedbackLong") or "").replace("_", " "),
            "action": f"Sleep factor: {tr_raw.get('sleepScoreFactorPercent', '--')}% · HRV factor: {tr_raw.get('hrvFactorPercent', '--')}% · Stress factor: {tr_raw.get('stressHistoryFactorPercent', '--')}%",
        })

    ts_raw = reports.get("trainingStatus") or {}
    m_status = (ts_raw.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}
    if isinstance(m_status, dict) and m_status:
        first_dev = next(iter(m_status.values()), {})
        if isinstance(first_dev, dict) and first_dev.get("trainingStatusFeedbackPhrase"):
            tips.append({
                "id": "garmin-training-status",
                "category": "Training Status",
                "tone": "emerald",
                "title": str(first_dev.get("trainingStatusFeedbackPhrase")).replace("_", " ").title(),
                "summary": "Garmin Connect training status & acute-to-chronic workload assessment.",
                "action": "Keep balancing low-aerobic base with high-aerobic and anaerobic stimuli.",
            })

    fa = reports.get("fitnessAge") or {}
    fitness_age_report = {
        "chronologicalAge": fa.get("chronologicalAge"),
        "fitnessAge": round(fa["fitnessAge"], 1) if isinstance(fa.get("fitnessAge"), (int, float)) else None,
        "achievableFitnessAge": round(fa["achievableFitnessAge"], 1) if isinstance(fa.get("achievableFitnessAge"), (int, float)) else None,
        "previousFitnessAge": round(fa["previousFitnessAge"], 1) if isinstance(fa.get("previousFitnessAge"), (int, float)) else None,
    }
    if fitness_age_report["fitnessAge"] and fitness_age_report["chronologicalAge"]:
        diff = round(fitness_age_report["chronologicalAge"] - fitness_age_report["fitnessAge"], 1)
        tips.append({
            "id": "fitness-age",
            "category": "Longevity",
            "tone": "emerald" if diff > 0 else "cyan",
            "title": f"Fitness Age {fitness_age_report['fitnessAge']} vs {fitness_age_report['chronologicalAge']} yrs",
            "summary": f"Your cardiovascular & body-composition profile is {abs(diff)} years {'younger' if diff >= 0 else 'older'} than your chronological age.",
            "action": f"Achievable target: {fitness_age_report['achievableFitnessAge']} yrs via consistent vigorous minutes & RHR optimization." if fitness_age_report["achievableFitnessAge"] else "Keep stacking Zone 2 and vigorous sessions.",
        })

    rp = reports.get("racePredictions") or {}
    race_predictions = [
        {"distance": "5K", "time": _fmt_race_time(rp.get("time5K")), "pace": _fmt_race_pace(rp.get("time5K"), 5.0)},
        {"distance": "10K", "time": _fmt_race_time(rp.get("time10K")), "pace": _fmt_race_pace(rp.get("time10K"), 10.0)},
        {"distance": "Half Marathon", "time": _fmt_race_time(rp.get("timeHalfMarathon")), "pace": _fmt_race_pace(rp.get("timeHalfMarathon"), 21.0975)},
        {"distance": "Marathon", "time": _fmt_race_time(rp.get("timeMarathon")), "pace": _fmt_race_pace(rp.get("timeMarathon"), 42.195)},
    ]

    endurance = reports.get("enduranceScore") or {}
    hill = reports.get("hillScore") or {}
    lt_raw = (reports.get("lactateThreshold") or {}).get("speed_and_heart_rate") or {}

    prs_raw = reports.get("personalRecords") or []
    personal_records = []
    for pr in prs_raw[:10]:
        if not isinstance(pr, dict):
            continue
        personal_records.append({
            "activityId": pr.get("activityId"),
            "activityName": pr.get("activityName") or "Personal Record",
            "activityType": pr.get("activityType") or "running",
            "typeId": pr.get("typeId"),
            "value": pr.get("value"),
            "date": str(pr.get("activityStartDateTimeLocal") or "")[:10],
        })

    badges_raw = reports.get("earnedBadges") or []
    badges = [
        {
            "name": b.get("badgeName") or b.get("badgeKey") or "Badge",
            "category": b.get("badgeCategoryName") or "",
            "earnedDate": (b.get("badgeEarnedDate") or "")[:10],
        }
        for b in badges_raw[:8]
        if isinstance(b, dict)
    ]

    sleep_data = reports.get("sleepData") or {}
    sleep_dto = sleep_data.get("dailySleepDTO") or {}
    sleep_scores = sleep_dto.get("sleepScores") or {}
    sleep_overall = sleep_scores.get("overall") or {}
    sleep_need = sleep_dto.get("sleepNeed") or {}
    sleep_sec = sleep_dto.get("sleepTimeSeconds")
    sleep_summary = {
        "score": sleep_overall.get("value"),
        "qualifier": sleep_overall.get("qualifierKey"),
        "durationHours": round(sleep_sec / 3600.0, 1) if isinstance(sleep_sec, (int, float)) and sleep_sec > 0 else None,
        "sleepNeedHours": round(sleep_need["actual"] / 60.0, 1) if isinstance(sleep_need.get("actual"), (int, float)) and sleep_need["actual"] > 0 else None,
        "feedback": sleep_need.get("feedback"),
        "overnightHrv": sleep_data.get("avgOvernightHrv"),
    }

    us = reports.get("userSummary") or {}
    health_summary = {
        "steps": us.get("totalSteps"),
        "stepGoal": us.get("dailyStepGoal"),
        "restingHr": us.get("restingHeartRate"),
        "stressAvg": us.get("averageStressLevel"),
        "bodyBatteryHigh": us.get("bodyBatteryHighestValue"),
        "bodyBatteryLow": us.get("bodyBatteryLowestValue"),
        "moderateMin": us.get("moderateIntensityMinutes"),
        "vigorousMin": us.get("vigorousIntensityMinutes"),
    }

    return {
        "date": today_date,
        "tips": tips,
        "fitnessAge": fitness_age_report,
        "racePredictions": race_predictions,
        "enduranceScore": {
            "overall": endurance.get("overallScore"),
            "classification": endurance.get("classification"),
        },
        "hillScore": {
            "overall": hill.get("overallScore"),
            "strength": hill.get("strengthScore"),
            "endurance": hill.get("enduranceScore"),
        },
        "lactateThreshold": {
            "heartRate": lt_raw.get("heartRate"),
            "speed": lt_raw.get("speed"),
            "date": (lt_raw.get("calendarDate") or "")[:10],
        },
        "personalRecords": personal_records,
        "badges": badges,
        "sleepSummary": sleep_summary,
        "healthSummary": health_summary,
    }
