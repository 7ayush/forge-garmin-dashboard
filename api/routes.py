"""Starlette HTTP API routes and SPA serving for FORGE Garmin Performance Dashboard."""

from __future__ import annotations

from dashboard.api.accounts import get_active_account, list_accounts, save_account_meta, set_active_account

import asyncio
import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
)
from starlette.routing import Route

from .analytics import (
    analyze_body,
    analyze_engine,
    analyze_tips,
    analyze_fuel,
    analyze_recovery,
    analyze_strength,
    audit_hr_zones,
    build_legacy_overview,
    build_progress_payload,
    build_today_payload,
)
from .db import (
    DEFAULT_DB_PATH,
    DEFAULT_SETTINGS,
    PHOTOS_DIR,
    get_conn,
    get_settings,
    log_audit,
    update_settings,
    utcnow_iso,
)
from .exercise_taxonomy import MUSCLE_GROUPS, MUSCLE_META
from .garmin_sync import (
    fetch_activity_detail_cached,
    fetch_garmin_reports_cached,
    fetch_intraday_cached,
    get_garmin_client,
    get_sync_state,
    run_sync,
    sync_exercise_sets_for_activity,
    trigger_background_sync,
)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _read_json(request: Request) -> Dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _int_param(request: Request, name: str, default: int, lo: int, hi: int) -> int:
    raw = request.query_params.get(name)
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, val))


def _date_param(request: Request, name: str) -> Optional[date]:
    raw = request.query_params.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _sync_active_workout_sets_to_garmin(
    client,
    conn,
    activity_id: int,
    confirm: bool,
) -> Dict[str, Any]:
    """Build Garmin exerciseSets PUT payload from DB + cached raw payload."""
    rows = conn.execute(
        "SELECT * FROM exercise_sets WHERE activity_id = ? ORDER BY set_index ASC",
        (activity_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"No cached exercise sets found for activity {activity_id}")

    raw_row = conn.execute(
        "SELECT payload_json FROM raw_payloads WHERE source_key = 'exercise_sets' AND entity_key = ?",
        (str(activity_id),),
    ).fetchone()
    raw_sets: List[Dict[str, Any]] = []
    if raw_row and raw_row["payload_json"]:
        try:
            raw_sets = json.loads(raw_row["payload_json"]).get("exerciseSets") or []
        except Exception:
            raw_sets = []

    raw_by_idx = {i: s for i, s in enumerate(raw_sets)}
    payload_sets: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []

    for r in rows:
        idx = int(r["set_index"])
        orig_raw = dict(raw_by_idx.get(idx) or {})
        set_type = r["set_type"]
        base_entry: Dict[str, Any] = {
            "setType": set_type,
            "startTime": orig_raw.get("startTime") or r["start_time"],
            "duration": orig_raw.get("duration") if orig_raw.get("duration") is not None else r["duration_s"],
            "wktStepIndex": orig_raw.get("wktStepIndex"),
        }

        if set_type == "ACTIVE":
            cat = (r["category"] or "UNKNOWN").upper()
            ex_name = r["exercise_name"]
            ex_obj: Dict[str, Any] = {
                "category": cat,
                "probability": float(r["probability"] or 100.0),
            }
            if ex_name:
                ex_obj["name"] = ex_name
            base_entry["exercises"] = [ex_obj]
            base_entry["repetitionCount"] = r["reps"]
            w_kg = float(r["weight_kg"] or 0.0)
            base_entry["weight"] = round(w_kg * 1000.0, 1) if w_kg > 0 else 0.0

            if (
                cat != (r["orig_category"] or "").upper()
                or (ex_name or "") != (r["orig_exercise_name"] or "")
                or r["reps"] != r["orig_reps"]
                or round(w_kg, 2) != round(float(r["orig_weight_kg"] or 0.0), 2)
            ):
                changes.append(
                    {
                        "set_index": idx,
                        "before": {
                            "category": r["orig_category"],
                            "exercise_name": r["orig_exercise_name"],
                            "reps": r["orig_reps"],
                            "weight_kg": r["orig_weight_kg"],
                        },
                        "after": {
                            "category": cat,
                            "exercise_name": ex_name,
                            "reps": r["reps"],
                            "weight_kg": w_kg,
                        },
                    }
                )
        else:
            base_entry["exercises"] = orig_raw.get("exercises") or []
            base_entry["repetitionCount"] = orig_raw.get("repetitionCount")
            base_entry["weight"] = orig_raw.get("weight")

        payload_sets.append(base_entry)

    if not confirm:
        return {
            "preview": True,
            "activity_id": activity_id,
            "changes_count": len(changes),
            "changes": changes,
            "total_sets": len(payload_sets),
        }

    if not changes:
        return {
            "ok": True,
            "preview": False,
            "activity_id": activity_id,
            "changes_pushed": 0,
            "message": "No pending local corrections to push.",
        }

    url = f"{client.garmin_connect_activity}/{activity_id}/exerciseSets"
    resp = client.connectapi(
        url,
        method="PUT",
        json={"activityId": activity_id, "exerciseSets": payload_sets},
    )
    log_audit(
        conn,
        action="garmin_push_exercise_sets",
        target=f"activity:{activity_id}",
        before_obj={"changes_from": [c["before"] for c in changes]},
        after_obj={"changes_to": [c["after"] for c in changes]},
        garmin_response=resp if isinstance(resp, dict) else {"raw": str(resp)},
    )
    conn.execute(
        """
        UPDATE exercise_sets
        SET user_corrected = 0,
            orig_category = category,
            orig_exercise_name = exercise_name,
            orig_reps = reps,
            orig_weight_kg = weight_kg
        WHERE activity_id = ? AND user_corrected = 1
        """,
        (activity_id,),
    )
    sync_exercise_sets_for_activity(client, conn, activity_id, scope="write_refresh", preserve_user_edits=False)
    return {
        "ok": True,
        "preview": False,
        "activity_id": activity_id,
        "changes_pushed": len(changes),
    }


def _compute_hr_zone_proposal(current: Dict[str, Any], body: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build current vs proposed Garmin heartRateZones entry with validated BPM boundaries."""
    before = dict(current)
    after = dict(current)

    method_raw = body.get("training_method")
    if method_raw:
        m = str(method_raw).strip().upper()
        if m not in {"LACTATE_THRESHOLD", "HR_MAX", "HR_RESERVE"}:
            raise ValueError("training_method must be LACTATE_THRESHOLD, HR_MAX, or HR_RESERVE")
        after["trainingMethod"] = m

    rhr = body.get("resting_hr", after.get("restingHeartRateUsed"))
    max_hr = body.get("max_hr", after.get("maxHeartRateUsed"))
    lthr = body.get("lactate_threshold_hr", after.get("lactateThresholdHeartRateUsed"))

    if rhr is not None:
        rhr = int(rhr)
        if not 25 <= rhr <= 140:
            raise ValueError("resting_hr must be 25..140 bpm")
        after["restingHeartRateUsed"] = rhr
        after["restingHrAutoUpdateUsed"] = False
    if max_hr is not None:
        max_hr = int(max_hr)
        if not 100 <= max_hr <= 240:
            raise ValueError("max_hr must be 100..240 bpm")
        after["maxHeartRateUsed"] = max_hr
    if lthr is not None:
        lthr = int(lthr)
        if not 80 <= lthr <= 220:
            raise ValueError("lactate_threshold_hr must be 80..220 bpm")
        after["lactateThresholdHeartRateUsed"] = lthr

    eff_max = int(after.get("maxHeartRateUsed") or 197)
    eff_rhr = int(after.get("restingHeartRateUsed") or 56)
    eff_lthr = int(after.get("lactateThresholdHeartRateUsed") or 186)
    if eff_rhr >= eff_max:
        raise ValueError("resting_hr must be strictly lower than max_hr")
    if eff_lthr > eff_max:
        raise ValueError("lactate_threshold_hr cannot exceed max_hr")

    custom_floors = body.get("floors")
    if custom_floors is not None:
        if not isinstance(custom_floors, list) or len(custom_floors) != 5:
            raise ValueError("floors must be a list of 5 integer BPM boundaries")
        floors = [int(x) for x in custom_floors]
    else:
        eff_method = after.get("trainingMethod") or "HR_MAX"
        if eff_method == "LACTATE_THRESHOLD":
            # Standard Garmin %LTHR thresholds anchored to LTHR (Z5 starts at LTHR)
            floors = [
                round(eff_lthr * 0.65),
                round(eff_lthr * 0.80),
                round(eff_lthr * 0.89),
                round(eff_lthr * 0.95),
                min(eff_max - 1, eff_lthr),
            ]
        elif eff_method == "HR_RESERVE" or eff_method == "HR_MAX":
            # Karvonen HRR floors if RHR is available, else %MaxHR
            if eff_method == "HR_RESERVE":
                hrr = eff_max - eff_rhr
                floors = [eff_rhr + round(hrr * pct) for pct in (0.50, 0.60, 0.70, 0.80, 0.90)]
            else:
                floors = [round(eff_max * pct) for pct in (0.50, 0.60, 0.70, 0.80, 0.90)]
        else:
            floors = [int(after.get(f"zone{i}Floor") or (90 + i * 20)) for i in range(1, 6)]

    if any(floors[i] >= floors[i + 1] for i in range(4)):
        raise ValueError(f"Zone boundaries must strictly increase: {floors}")
    if floors[-1] > eff_max:
        raise ValueError(f"Zone 5 floor ({floors[-1]}) cannot exceed max_hr ({eff_max})")

    for idx, floor in enumerate(floors, start=1):
        after[f"zone{idx}Floor"] = floor
    after["changeState"] = "CHANGED"
    return before, after


def build_api_routes(db_path: Optional[Path] = None) -> List[Any]:
    """Construct all Starlette routes bound to `db_path` (or active account's DB when None)."""

    def _db() -> Path:
        return db_path if db_path is not None else get_active_account().db_path

    async def api_accounts(request: Request) -> Response:
        return JSONResponse({
            "activeAccount": get_active_account().id,
            "accounts": list_accounts(),
        })

    async def api_accounts_select(request: Request) -> Response:
        body = await _read_json(request)
        account_id = str(body.get("accountId") or "").strip()
        acc = set_active_account(account_id)
        with get_conn(acc.db_path):
            pass
        return JSONResponse({
            "activeAccount": acc.id,
            "accounts": list_accounts(),
        })

    async def api_accounts_login(request: Request) -> Response:
        body = await _read_json(request)
        acc = get_active_account()
        email = str(body.get("email") or acc.email or "").strip()
        password = str(body.get("password") or "")
        if not email or not password:
            return _err(400, "Both Garmin email and password are required to sign in.")

        def _login():
            from garminconnect import Garmin
            from dashboard.api.garmin_sync import _CLIENTS
            acc.token_dir.mkdir(parents=True, exist_ok=True)
            client = Garmin(email, password)
            client.login()
            if hasattr(client, "garth"):
                client.garth.dump(str(acc.token_dir))
            else:
                client.client.dump(str(acc.token_dir))
            save_account_meta(acc.token_dir, email)
            _CLIENTS.pop(str(acc.token_dir), None)
            with get_conn(acc.db_path):
                pass

        try:
            await asyncio.to_thread(_login)
            return JSONResponse({"ok": True, "accounts": list_accounts()})
        except Exception as exc:
            return _err(401, f"Garmin login failed for {email}: {exc}")

    async def api_accounts_logout(request: Request) -> Response:
        from dashboard.api.garmin_sync import _CLIENTS
        acc = get_active_account()
        if acc.token_dir.exists():
            for p in acc.token_dir.glob("*.json"):
                try:
                    p.unlink()
                except OSError:
                    pass
        _CLIENTS.pop(str(acc.token_dir), None)
        return JSONResponse({"ok": True, "accounts": list_accounts()})

    async def api_today(request: Request) -> Response:
        def _work():
            cur_db = _db()
            with get_conn(cur_db) as conn:
                return build_today_payload(conn, db_path=cur_db)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_strength(request: Request) -> Response:
        week_d = _date_param(request, "week")

        def _work():
            with get_conn(_db()) as conn:
                return analyze_strength(conn, get_settings(conn), week_start=week_d)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_strength_patch_local(request: Request) -> Response:
        try:
            activity_id = int(request.path_params["activity_id"])
        except ValueError:
            return _err(400, "Invalid activity_id")
        body = await _read_json(request)
        edits = body.get("edits")
        if not isinstance(edits, list) or not edits:
            # Support single-set payload too
            if any(k in body for k in ("set_index", "id")):
                edits = [body]
            else:
                return _err(400, "edits list or single set payload required")

        def _work():
            with get_conn(_db()) as conn:
                before_list = []
                after_list = []
                for item in edits:
                    if not isinstance(item, dict):
                        continue
                    set_idx = item.get("set_index")
                    row_id = item.get("id")
                    if row_id is not None:
                        row = conn.execute(
                            "SELECT * FROM exercise_sets WHERE id = ? AND activity_id = ?",
                            (int(row_id), activity_id),
                        ).fetchone()
                    elif set_idx is not None:
                        row = conn.execute(
                            "SELECT * FROM exercise_sets WHERE activity_id = ? AND set_index = ?",
                            (activity_id, int(set_idx)),
                        ).fetchone()
                    else:
                        continue
                    if not row:
                        continue

                    new_cat = str(item.get("category") or row["category"]).strip().upper()
                    new_name = (
                        str(item["exercise_name"]).strip().upper()
                        if item.get("exercise_name") not in (None, "")
                        else row["exercise_name"]
                    )
                    if "exercise_name" in item and item["exercise_name"] == "":
                        new_name = None

                    new_reps = row["reps"]
                    if "reps" in item and item["reps"] is not None:
                        r_val = int(item["reps"])
                        if not 0 <= r_val <= 200:
                            raise ValueError("reps must be between 0 and 200")
                        new_reps = r_val

                    new_w = row["weight_kg"]
                    if "weight_kg" in item and item["weight_kg"] is not None:
                        w_val = float(item["weight_kg"])
                        if not 0 <= w_val <= 1000:
                            raise ValueError("weight_kg must be between 0 and 1000")
                        new_w = round(w_val, 2)

                    before_list.append(
                        {
                            "set_index": row["set_index"],
                            "category": row["category"],
                            "exercise_name": row["exercise_name"],
                            "reps": row["reps"],
                            "weight_kg": row["weight_kg"],
                        }
                    )
                    after_list.append(
                        {
                            "set_index": row["set_index"],
                            "category": new_cat,
                            "exercise_name": new_name,
                            "reps": new_reps,
                            "weight_kg": new_w,
                        }
                    )
                    conn.execute(
                        """
                        UPDATE exercise_sets
                        SET category = ?, exercise_name = ?, reps = ?, weight_kg = ?, user_corrected = 1
                        WHERE id = ?
                        """,
                        (new_cat, new_name, new_reps, new_w, row["id"]),
                    )

                if not after_list:
                    raise ValueError("No matching exercise sets found to update")
                log_audit(conn, "local_edit_exercise_sets", f"activity:{activity_id}", before_list, after_list)
                return {
                    "ok": True,
                    "activity_id": activity_id,
                    "updated": len(after_list),
                    "strength": analyze_strength(conn, get_settings(conn)),
                }

        try:
            return JSONResponse(await asyncio.to_thread(_work))
        except ValueError as exc:
            return _err(400, str(exc))

    async def api_strength_push_garmin(request: Request) -> Response:
        try:
            activity_id = int(request.path_params["activity_id"])
        except ValueError:
            return _err(400, "Invalid activity_id")
        body = await _read_json(request)
        confirm = bool(body.get("confirm", False))

        def _work():
            client = get_garmin_client() if confirm else None
            with get_conn(_db()) as conn:
                res = _sync_active_workout_sets_to_garmin(client, conn, activity_id, confirm)
                if confirm and not res.get("preview"):
                    res["strength"] = analyze_strength(conn, get_settings(conn))
                return res

        try:
            return JSONResponse(await asyncio.to_thread(_work))
        except ValueError as exc:
            return _err(400, str(exc))
        except Exception as exc:
            return _err(502, f"Garmin push failed: {exc}")

    async def api_engine(request: Request) -> Response:
        days = _int_param(request, "days", 30, 7, 365)

        def _work():
            with get_conn(_db()) as conn:
                return analyze_engine(conn, get_settings(conn), days=days)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_tips(request: Request) -> Response:
        refresh = request.query_params.get("refresh") == "1"
        today_str = date.today().isoformat()

        def _work():
            try:
                reports = fetch_garmin_reports_cached(_db(), today_str, force_refresh=refresh)
            except Exception:
                reports = {}
            with get_conn(_db()) as conn:
                return analyze_tips(conn, get_settings(conn), reports)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_recovery(request: Request) -> Response:
        days = _int_param(request, "days", 14, 7, 90)

        def _work():
            with get_conn(_db()) as conn:
                return analyze_recovery(conn, get_settings(conn), days=days)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_intraday(request: Request) -> Response:
        ds_param = _date_param(request, "date")
        ds = (ds_param or datetime.now().date()).isoformat()
        refresh = request.query_params.get("refresh") in ("1", "true", "yes")
        try:
            data = await asyncio.to_thread(fetch_intraday_cached, ds, refresh, _db())
            return JSONResponse(data)
        except Exception as exc:
            return _err(502, f"Intraday telemetry unavailable: {exc}")

    async def api_body(request: Request) -> Response:
        def _work():
            with get_conn(_db()) as conn:
                return analyze_body(conn, get_settings(conn))

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_body_weigh_in(request: Request) -> Response:
        body = await _read_json(request)
        if "weight_kg" not in body or body["weight_kg"] is None:
            return _err(400, "weight_kg is required")
        try:
            weight_kg = float(body["weight_kg"])
        except (TypeError, ValueError):
            return _err(400, "weight_kg must be numeric")
        if not 20.0 <= weight_kg <= 300.0:
            return _err(400, "weight_kg must be between 20 and 300")

        bf_pct = body.get("body_fat_pct")
        if bf_pct not in (None, ""):
            try:
                bf_pct = float(bf_pct)
            except (TypeError, ValueError):
                return _err(400, "body_fat_pct must be numeric")
            if not 3.0 <= bf_pct <= 60.0:
                return _err(400, "body_fat_pct must be between 3 and 60")
        else:
            bf_pct = None

        cdate_str = str(body.get("date") or datetime.now().date().isoformat())
        try:
            date.fromisoformat(cdate_str)
        except ValueError:
            return _err(400, "date must be YYYY-MM-DD")

        notes = str(body.get("notes") or "").strip() or None
        sync_garmin = bool(body.get("sync_to_garmin", True))
        now_local = datetime.now()
        now_utc = datetime.now(timezone.utc)
        rec_ts = f"{cdate_str}T{now_local.strftime('%H:%M:%S')}"
        gmt_ts = f"{cdate_str}T{now_utc.strftime('%H:%M:%S')}"

        def _work():
            synced = 0
            garmin_err = None
            if sync_garmin:
                try:
                    client = get_garmin_client()
                    if bf_pct is not None:
                        client.add_body_composition(
                            timestamp=rec_ts,
                            weight=round(weight_kg, 2),
                            percent_fat=round(bf_pct, 1),
                        )
                    else:
                        client.add_weigh_in_with_timestamps(
                            weight=round(weight_kg, 2),
                            unitKey="kg",
                            dateTimestamp=rec_ts,
                            gmtTimestamp=gmt_ts,
                        )
                    synced = 1
                except Exception as exc:
                    garmin_err = str(exc)

            with get_conn(_db()) as conn:
                conn.execute(
                    """
                    INSERT INTO body_measurements (
                        calendar_date, recorded_at, weight_kg, body_fat_pct,
                        body_fat_source, notes, source, synced_to_garmin
                    ) VALUES (?, ?, ?, ?, ?, ?, 'manual', ?)
                    """,
                    (
                        cdate_str,
                        utcnow_iso(),
                        round(weight_kg, 2),
                        round(bf_pct, 1) if bf_pct is not None else None,
                        "manual" if bf_pct is not None else None,
                        notes,
                        synced,
                    ),
                )
                log_audit(
                    conn,
                    "log_weigh_in",
                    cdate_str,
                    None,
                    {"weight_kg": round(weight_kg, 2), "body_fat_pct": bf_pct, "synced_to_garmin": synced},
                    {"error": garmin_err} if garmin_err else {"synced": True},
                )
                payload = analyze_body(conn, get_settings(conn))
                payload["garmin_synced"] = bool(synced)
                payload["garmin_error"] = garmin_err
                return payload

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_body_tape(request: Request) -> Response:
        body = await _read_json(request)
        cdate_str = str(body.get("date") or datetime.now().date().isoformat())
        try:
            date.fromisoformat(cdate_str)
        except ValueError:
            return _err(400, "date must be YYYY-MM-DD")

        tape_fields = ("waist_cm", "chest_cm", "arm_cm", "thigh_cm", "shoulder_cm", "neck_cm")
        vals: Dict[str, Optional[float]] = {}
        any_val = False
        for field in tape_fields:
            raw = body.get(field)
            if raw not in (None, ""):
                try:
                    num = round(float(raw), 1)
                except (TypeError, ValueError):
                    return _err(400, f"{field} must be numeric")
                if not 10.0 <= num <= 250.0:
                    return _err(400, f"{field} must be between 10 and 250 cm")
                vals[field] = num
                any_val = True
            else:
                vals[field] = None
        if not any_val:
            return _err(400, "Provide at least one tape measurement in cm")

        notes = str(body.get("notes") or "").strip() or None

        def _work():
            with get_conn(_db()) as conn:
                conn.execute(
                    """
                    INSERT INTO body_measurements (
                        calendar_date, recorded_at, waist_cm, chest_cm, arm_cm,
                        thigh_cm, shoulder_cm, neck_cm, notes, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'tape')
                    """,
                    (
                        cdate_str,
                        utcnow_iso(),
                        vals["waist_cm"],
                        vals["chest_cm"],
                        vals["arm_cm"],
                        vals["thigh_cm"],
                        vals["shoulder_cm"],
                        vals["neck_cm"],
                        notes,
                    ),
                )
                log_audit(conn, "log_tape", cdate_str, None, vals)
                return analyze_body(conn, get_settings(conn))

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_body_photo_upload(request: Request) -> Response:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            return _err(400, "Multipart form field 'file' is required")
        filename_orig = getattr(upload, "filename", "") or "photo.jpg"
        ext = Path(filename_orig).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTS:
            return _err(400, f"Unsupported image format '{ext}'. Allowed: .jpg, .jpeg, .png, .webp")
        data = await upload.read()
        if not data or len(data) > MAX_PHOTO_BYTES:
            return _err(400, "Photo must be non-empty and <= 10 MB")

        pose = str(form.get("pose") or "front").strip().lower()
        if pose not in {"front", "side", "back"}:
            pose = "front"
        cdate_str = str(form.get("date") or datetime.now().date().isoformat())
        try:
            date.fromisoformat(cdate_str)
        except ValueError:
            return _err(400, "date must be YYYY-MM-DD")
        notes = str(form.get("notes") or "").strip() or None

        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        stored_name = f"{cdate_str}_{pose}_{uuid.uuid4().hex[:10]}{ext}"
        dest = PHOTOS_DIR / stored_name
        await asyncio.to_thread(dest.write_bytes, data)

        def _work():
            with get_conn(_db()) as conn:
                conn.execute(
                    """
                    INSERT INTO progress_photos (calendar_date, pose, filename, notes, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cdate_str, pose, stored_name, notes, utcnow_iso()),
                )
                return analyze_body(conn, get_settings(conn))

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_body_photo_get(request: Request) -> Response:
        try:
            photo_id = int(request.path_params["photo_id"])
        except ValueError:
            return _err(400, "Invalid photo_id")

        def _lookup():
            with get_conn(_db()) as conn:
                row = conn.execute("SELECT filename FROM progress_photos WHERE id = ?", (photo_id,)).fetchone()
                return row["filename"] if row else None

        fname = await asyncio.to_thread(_lookup)
        if not fname:
            return _err(404, "Photo not found")
        target = (PHOTOS_DIR / fname).resolve()
        if target.parent != PHOTOS_DIR.resolve() or not target.exists():
            return _err(404, "Photo file missing")
        return FileResponse(str(target))

    async def api_body_photo_delete(request: Request) -> Response:
        try:
            photo_id = int(request.path_params["photo_id"])
        except ValueError:
            return _err(400, "Invalid photo_id")

        def _work():
            with get_conn(_db()) as conn:
                row = conn.execute("SELECT filename FROM progress_photos WHERE id = ?", (photo_id,)).fetchone()
                if not row:
                    return None
                conn.execute("DELETE FROM progress_photos WHERE id = ?", (photo_id,))
                target = (PHOTOS_DIR / row["filename"]).resolve()
                if target.parent == PHOTOS_DIR.resolve() and target.exists():
                    target.unlink()
                return analyze_body(conn, get_settings(conn))

        res = await asyncio.to_thread(_work)
        if res is None:
            return _err(404, "Photo not found")
        return JSONResponse(res)

    async def api_fuel(request: Request) -> Response:
        days = _int_param(request, "days", 14, 7, 90)

        def _work():
            with get_conn(_db()) as conn:
                return analyze_fuel(conn, get_settings(conn), days=days)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_fuel_log(request: Request) -> Response:
        body = await _read_json(request)
        try:
            calories = float(body.get("calories", 0))
            protein_g = float(body.get("protein_g", 0))
            carbs_g = float(body.get("carbs_g") or 0)
            fat_g = float(body.get("fat_g") or 0)
        except (TypeError, ValueError):
            return _err(400, "Nutrition macros must be numeric")
        if not 0 <= calories <= 15000 or not 0 <= protein_g <= 1000:
            return _err(400, "Out-of-range calories or protein_g")
        if calories == 0 and protein_g == 0 and carbs_g == 0 and fat_g == 0:
            return _err(400, "Provide calories or at least one macro")

        cdate_str = str(body.get("date") or datetime.now().date().isoformat())
        try:
            date.fromisoformat(cdate_str)
        except ValueError:
            return _err(400, "date must be YYYY-MM-DD")
        label = str(body.get("label") or "").strip() or None

        def _work():
            with get_conn(_db()) as conn:
                conn.execute(
                    """
                    INSERT INTO nutrition_logs (
                        calendar_date, recorded_at, calories, protein_g, carbs_g, fat_g, label, source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'quick_log')
                    """,
                    (
                        cdate_str,
                        utcnow_iso(),
                        round(calories, 1),
                        round(protein_g, 1),
                        round(carbs_g, 1),
                        round(fat_g, 1),
                        label,
                    ),
                )
                return analyze_fuel(conn, get_settings(conn), days=14)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_fuel_delete(request: Request) -> Response:
        try:
            entry_id = int(request.path_params["entry_id"])
        except ValueError:
            return _err(400, "Invalid entry_id")

        def _work():
            with get_conn(_db()) as conn:
                conn.execute("DELETE FROM nutrition_logs WHERE id = ?", (entry_id,))
                return analyze_fuel(conn, get_settings(conn), days=14)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_hydration(request: Request) -> Response:
        body = await _read_json(request)
        try:
            value_ml = float(body.get("value_ml", 250))
        except (TypeError, ValueError):
            return _err(400, "value_ml must be numeric")
        if not -10000 <= value_ml <= 10000 or value_ml == 0:
            return _err(400, "value_ml must be non-zero between -10000 and 10000")

        ds = str(body.get("date") or datetime.now().date().isoformat())
        try:
            date.fromisoformat(ds)
        except ValueError:
            return _err(400, "date must be YYYY-MM-DD")
        sync_garmin = bool(body.get("sync_to_garmin", True))

        def _work():
            garmin_synced = False
            garmin_error = None
            latest_garmin_ml = None
            if sync_garmin:
                try:
                    client = get_garmin_client()
                    now_time = datetime.now().strftime("%H:%M:%S")
                    resp = client.add_hydration_data(
                        value_in_ml=value_ml,
                        cdate=ds,
                        timestamp=f"{ds}T{now_time}.0",
                    )
                    garmin_synced = True
                    if isinstance(resp, dict) and resp.get("valueInML") is not None:
                        latest_garmin_ml = float(resp["valueInML"])
                except Exception as exc:
                    garmin_error = str(exc)

            with get_conn(_db()) as conn:
                row = conn.execute(
                    "SELECT hydration_intake_ml, hydration_goal_ml FROM daily_wellness WHERE calendar_date = ?",
                    (ds,),
                ).fetchone()
                cur_ml = float(row["hydration_intake_ml"] or 0) if row else 0.0
                goal_ml = float(row["hydration_goal_ml"] or 3500) if row else 3500.0
                new_ml = latest_garmin_ml if latest_garmin_ml is not None else max(0.0, cur_ml + value_ml)
                conn.execute(
                    """
                    INSERT INTO daily_wellness (calendar_date, hydration_intake_ml, hydration_goal_ml, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(calendar_date) DO UPDATE SET
                        hydration_intake_ml = excluded.hydration_intake_ml,
                        updated_at = excluded.updated_at
                    """,
                    (ds, round(new_ml), round(goal_ml), utcnow_iso()),
                )
                return {
                    "ok": True,
                    "date": ds,
                    "delta_ml": value_ml,
                    "intake_ml": round(new_ml),
                    "goal_ml": round(goal_ml),
                    "garmin_synced": garmin_synced,
                    "garmin_error": garmin_error,
                }

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_progress(request: Request) -> Response:
        def _work():
            with get_conn(_db()) as conn:
                return build_progress_payload(conn)

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_progress_export(request: Request) -> Response:
        fmt = (request.query_params.get("format") or "markdown").lower()

        def _work():
            with get_conn(_db()) as conn:
                return build_progress_payload(conn)

        payload = await asyncio.to_thread(_work)
        if fmt == "json":
            return Response(
                json.dumps(payload, indent=2),
                media_type="application/json",
                headers={"Content-Disposition": 'attachment; filename="forge-weekly-review.json"'},
            )
        score = payload.get("forge_score") or {}
        wr = payload.get("weekly_review") or {}
        ms = payload.get("monthly_summary") or {}
        lines = [
            f"# FORGE Weekly Performance Review ({wr.get('week_start', '--')} to {wr.get('week_end', '--')})",
            "",
            f"- **Weekly Forge Score:** {score.get('overall', '--')}/100 (Train: {score.get('train_pct', '--')}% | Fuel: {score.get('fuel_pct') if score.get('fuel_pct') is not None else 'Excluded'} | Recover: {score.get('recover_pct', '--')}%)",
            f"- **Muscles at Target:** {score.get('muscles_at_target', '--')} | **Lifts:** {score.get('lifts_this_week', '--')} | **Sleep Nights Hit:** {score.get('sleep_nights_hit', '--')}",
            "",
            "## Wins",
            *[f"- {w}" for w in (wr.get("wins") or ["No standout wins logged yet"])],
            "",
            "## Misses & Gaps",
            *[f"- {m}" for m in (wr.get("misses") or ["None"])],
            "",
            "## Next Week Focus (Top 3)",
            *[f"- {f}" for f in (wr.get("focus_items") or [])],
            "",
            "## 30-Day Snapshot",
            f"- Run distance: {ms.get('run_km_30d', 0)} km | Strength tonnage: {ms.get('strength_tonnage_30d', 0)} kg | Avg sleep: {ms.get('avg_sleep_h', '--')}h | HRV baseline: {ms.get('hrv_baseline_ms', '--')} ms | Trend weight: {ms.get('trend_weight_kg', '--')} kg",
        ]
        return PlainTextResponse(
            "\n".join(lines),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="forge-weekly-review.md"'},
        )

    async def api_activity_detail(request: Request) -> Response:
        try:
            activity_id = int(request.path_params["activity_id"])
        except ValueError:
            return _err(400, "Invalid activity_id")
        refresh = request.query_params.get("refresh") in ("1", "true", "yes")
        try:
            data = await asyncio.to_thread(fetch_activity_detail_cached, activity_id, refresh, _db())
            if not data:
                return _err(404, "Activity not found")
            return JSONResponse(data)
        except Exception as exc:
            return _err(502, f"Failed to load activity {activity_id}: {exc}")

    async def api_activity_effort(request: Request) -> Response:
        try:
            activity_id = int(request.path_params["activity_id"])
        except ValueError:
            return _err(400, "Invalid activity_id")
        body = await _read_json(request)
        summary_updates: Dict[str, Any] = {}
        rpe_store = None
        feel_store = None

        if "rpe" in body and body["rpe"] is not None:
            try:
                rpe_val = float(body["rpe"])
            except (TypeError, ValueError):
                return _err(400, "rpe must be numeric")
            if not 0.0 <= rpe_val <= 10.0:
                return _err(400, "rpe must be between 0 and 10")
            rpe_store = int(round(rpe_val * 10))
            summary_updates["directWorkoutRpe"] = rpe_store

        if "feel" in body and body["feel"] is not None:
            try:
                feel_val = int(body["feel"])
            except (TypeError, ValueError):
                return _err(400, "feel must be an integer")
            if feel_val not in (0, 25, 50, 75, 100):
                return _err(400, "feel must be one of 0, 25, 50, 75, 100")
            feel_store = feel_val
            summary_updates["directWorkoutFeel"] = feel_store

        if not summary_updates:
            return _err(400, "Provide rpe and/or feel")
        sync_garmin = bool(body.get("sync_to_garmin", True))

        def _work():
            garmin_synced = False
            garmin_err = None
            if sync_garmin:
                try:
                    client = get_garmin_client()
                    url = f"{client.garmin_connect_activity}/{activity_id}"
                    client.connectapi(
                        url,
                        method="PUT",
                        json={"activityId": activity_id, "summaryDTO": summary_updates},
                    )
                    garmin_synced = True
                except Exception as exc:
                    garmin_err = str(exc)

            with get_conn(_db()) as conn:
                if rpe_store is not None:
                    conn.execute("UPDATE activities SET rpe = ? WHERE activity_id = ?", (rpe_store, activity_id))
                if feel_store is not None:
                    conn.execute("UPDATE activities SET feel = ? WHERE activity_id = ?", (feel_store, activity_id))
                log_audit(conn, "update_activity_effort", f"activity:{activity_id}", None, summary_updates)
                return {
                    "ok": True,
                    "activity_id": activity_id,
                    "rpe_raw": rpe_store,
                    "feel_raw": feel_store,
                    "garmin_synced": garmin_synced,
                    "garmin_error": garmin_err,
                }

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_settings_get(request: Request) -> Response:
        def _work():
            with get_conn(_db()) as conn:
                map_rows = [
                    {
                        "category": r["category"],
                        "exercise_name": r["exercise_name"],
                        "primary_muscle": r["primary_muscle"],
                        "secondary_muscles": json.loads(r["secondary_muscles_json"] or "[]"),
                        "is_custom": bool(r["is_custom"]),
                    }
                    for r in conn.execute(
                        "SELECT * FROM exercise_muscle_map ORDER BY is_custom DESC, category ASC, exercise_name ASC"
                    ).fetchall()
                ]
                audit_rows = [
                    dict(r)
                    for r in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 25").fetchall()
                ]
                return {
                    "settings": get_settings(conn),
                    "defaults": DEFAULT_SETTINGS,
                    "hr_audit": audit_hr_zones(conn),
                    "muscle_groups": list(MUSCLE_GROUPS),
                    "muscle_meta": MUSCLE_META,
                    "muscle_map": map_rows,
                    "sync": get_sync_state(),
                    "audit_log": audit_rows,
                }

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_settings_patch(request: Request) -> Response:
        body = await _read_json(request)
        if not body:
            return _err(400, "No settings fields provided")

        def _work():
            with get_conn(_db()) as conn:
                before = get_settings(conn)
                after = update_settings(conn, body)
                log_audit(conn, "update_settings", "app_settings", before, after)
                return {"ok": True, "settings": after}

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_settings_hr_zones(request: Request) -> Response:
        body = await _read_json(request)
        confirm = bool(body.get("confirm", False))
        sport = str(body.get("sport") or "DEFAULT").strip().upper()

        def _work():
            with get_conn(_db()) as conn:
                prof = conn.execute("SELECT hr_zones_json FROM athlete_profile WHERE id = 1").fetchone()
                zones = json.loads(prof["hr_zones_json"] or "[]") if prof and prof["hr_zones_json"] else []
                current = next((z for z in zones if isinstance(z, dict) and z.get("sport") == sport), None) or (
                    zones[0] if zones else {"sport": sport, "trainingMethod": "HR_MAX", "maxHeartRateUsed": 197, "restingHeartRateUsed": 56}
                )
                before, after = _compute_hr_zone_proposal(current, body)

                if not confirm:
                    return {"preview": True, "sport": sport, "before": before, "after": after}

                client = get_garmin_client()
                resp = client.connectapi("/biometric-service/heartRateZones", method="PUT", json=[after])
                # Refresh saved profile HR zones
                fresh = client.connectapi("/biometric-service/heartRateZones")
                if isinstance(fresh, list):
                    conn.execute(
                        "UPDATE athlete_profile SET hr_zones_json = ?, updated_at = ? WHERE id = 1",
                        (json.dumps(fresh), utcnow_iso()),
                    )
                log_audit(
                    conn,
                    "garmin_update_hr_zones",
                    f"sport:{sport}",
                    before,
                    after,
                    resp if isinstance(resp, dict) else {"result": "updated"},
                )
                return {
                    "ok": True,
                    "preview": False,
                    "sport": sport,
                    "hr_audit": audit_hr_zones(conn),
                }

        try:
            return JSONResponse(await asyncio.to_thread(_work))
        except ValueError as exc:
            return _err(400, str(exc))
        except Exception as exc:
            return _err(502, f"HR zones update failed: {exc}")

    async def api_settings_muscle_map(request: Request) -> Response:
        body = await _read_json(request)
        cat = str(body.get("category") or "").strip().upper()
        ex_name = str(body.get("exercise_name") or "").strip().upper()
        primary = str(body.get("primary_muscle") or "").strip().lower()
        secondary = body.get("secondary_muscles") or []
        if not cat or primary not in MUSCLE_GROUPS:
            return _err(400, "Valid category and primary_muscle required")
        sec_clean = [str(m).strip().lower() for m in secondary if str(m).strip().lower() in MUSCLE_GROUPS and str(m).strip().lower() != primary]

        def _work():
            with get_conn(_db()) as conn:
                conn.execute(
                    """
                    INSERT INTO exercise_muscle_map (category, exercise_name, primary_muscle, secondary_muscles_json, is_custom)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(category, exercise_name) DO UPDATE SET
                        primary_muscle = excluded.primary_muscle,
                        secondary_muscles_json = excluded.secondary_muscles_json,
                        is_custom = 1
                    """,
                    (cat, ex_name, primary, json.dumps(sec_clean)),
                )
                log_audit(conn, "upsert_muscle_map", f"{cat}:{ex_name}", None, {"primary": primary, "secondary": sec_clean})
                return {"ok": True, "category": cat, "exercise_name": ex_name, "primary_muscle": primary, "secondary_muscles": sec_clean}

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_export(request: Request) -> Response:
        def _work():
            with get_conn(_db()) as conn:
                return {
                    "exported_at": utcnow_iso(),
                    "settings": get_settings(conn),
                    "athlete_profile": dict(conn.execute("SELECT * FROM athlete_profile WHERE id = 1").fetchone() or {}),
                    "body_measurements": [dict(r) for r in conn.execute("SELECT * FROM body_measurements ORDER BY calendar_date DESC").fetchall()],
                    "nutrition_logs": [dict(r) for r in conn.execute("SELECT * FROM nutrition_logs ORDER BY calendar_date DESC").fetchall()],
                    "muscle_map_custom": [dict(r) for r in conn.execute("SELECT * FROM exercise_muscle_map WHERE is_custom = 1").fetchall()],
                    "audit_log": [dict(r) for r in conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100").fetchall()],
                    "activities_count": conn.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"],
                }

        data = await asyncio.to_thread(_work)
        return Response(
            json.dumps(data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="forge-athlete-export.json"'},
        )

    async def api_sync_now(request: Request) -> Response:
        days = _int_param(request, "days", 7, 1, 90)
        wait = request.query_params.get("wait", "1") != "0"
        if not wait:
            started = trigger_background_sync(scope="incremental", days=days, activity_limit=40, db_path=_db())
            return JSONResponse({"started": started, "sync": get_sync_state()})
        try:
            res = await asyncio.to_thread(run_sync, "incremental", days, 40, _db())
            return JSONResponse({"ok": True, "result": res, "sync": get_sync_state()})
        except Exception as exc:
            return _err(502, f"Sync failed: {exc}")

    async def api_sync_backfill(request: Request) -> Response:
        days = _int_param(request, "days", 90, 7, 365)
        wait = request.query_params.get("wait", "0") == "1"
        if not wait:
            started = trigger_background_sync(scope="backfill", days=days, activity_limit=150, db_path=_db())
            return JSONResponse({"started": started, "sync": get_sync_state()})
        try:
            res = await asyncio.to_thread(run_sync, "backfill", days, 150, _db())
            return JSONResponse({"ok": True, "result": res, "sync": get_sync_state()})
        except Exception as exc:
            return _err(502, f"Backfill failed: {exc}")

    async def api_sync_status(request: Request) -> Response:
        def _work():
            with get_conn(_db()) as conn:
                runs = [
                    dict(r)
                    for r in conn.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 20").fetchall()
                ]
                act_n = conn.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"]
                days_n = conn.execute("SELECT COUNT(*) AS n FROM daily_wellness").fetchone()["n"]
                return {
                    "sync": get_sync_state(),
                    "counts": {"activities": act_n, "daily_wellness": days_n},
                    "recent_runs": runs,
                }

        return JSONResponse(await asyncio.to_thread(_work))

    async def api_overview(request: Request) -> Response:
        days = _int_param(request, "days", 7, 1, 90)

        def _work():
            with get_conn(_db()) as conn:
                return build_legacy_overview(conn, days=days)

        return JSONResponse(await asyncio.to_thread(_work))

    async def spa_index(request: Request) -> Response:
        rel_path = request.path_params.get("path", "")
        if rel_path and not rel_path.startswith("api/"):
            candidate = (FRONTEND_DIST / rel_path).resolve()
            if (
                candidate.is_file()
                and str(candidate).startswith(str(FRONTEND_DIST.resolve()))
            ):
                return FileResponse(str(candidate))
        index_file = FRONTEND_DIST / "index.html"
        if index_file.exists():
            return HTMLResponse(index_file.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<h1>FORGE Frontend Not Built</h1><p>Run <code>npm run build</code> in <code>dashboard/frontend</code>.</p>",
            status_code=503,
        )

    routes: List[Any] = [
        Route("/api/accounts", api_accounts),
        Route("/api/accounts/select", api_accounts_select, methods=["POST"]),
        Route("/api/accounts/login", api_accounts_login, methods=["POST"]),
        Route("/api/accounts/logout", api_accounts_logout, methods=["POST"]),
        Route("/api/today", api_today),
        Route("/api/strength", api_strength),
        Route("/api/strength/sets/{activity_id}/local", api_strength_patch_local, methods=["PATCH"]),
        Route("/api/strength/sets/{activity_id}/push", api_strength_push_garmin, methods=["POST"]),
        Route("/api/engine", api_engine),
        Route("/api/tips", api_tips),
        Route("/api/recovery", api_recovery),
        Route("/api/intraday", api_intraday),
        Route("/api/body", api_body),
        Route("/api/body/weigh-in", api_body_weigh_in, methods=["POST"]),
        Route("/api/body/tape", api_body_tape, methods=["POST"]),
        Route("/api/body/photo", api_body_photo_upload, methods=["POST"]),
        Route("/api/body/photo/{photo_id}", api_body_photo_get, methods=["GET"]),
        Route("/api/body/photo/{photo_id}", api_body_photo_delete, methods=["DELETE"]),
        Route("/api/fuel", api_fuel),
        Route("/api/fuel/log", api_fuel_log, methods=["POST"]),
        Route("/api/fuel/log/{entry_id}", api_fuel_delete, methods=["DELETE"]),
        Route("/api/hydration", api_hydration, methods=["POST"]),
        Route("/api/progress", api_progress),
        Route("/api/progress/export", api_progress_export),
        Route("/api/activity/{activity_id}", api_activity_detail),
        Route("/api/activity/{activity_id}/effort", api_activity_effort, methods=["PATCH"]),
        Route("/api/settings", api_settings_get, methods=["GET"]),
        Route("/api/settings", api_settings_patch, methods=["PATCH"]),
        Route("/api/settings/hr-zones", api_settings_hr_zones, methods=["POST"]),
        Route("/api/settings/muscle-map", api_settings_muscle_map, methods=["POST"]),
        Route("/api/export", api_export),
        Route("/api/sync/now", api_sync_now, methods=["POST"]),
        Route("/api/sync/backfill", api_sync_backfill, methods=["POST"]),
        Route("/api/sync/status", api_sync_status),
        Route("/api/overview", api_overview),
        Route("/", spa_index),
        Route("/strength", spa_index),
        Route("/engine", spa_index),
        Route("/recovery", spa_index),
        Route("/body", spa_index),
        Route("/fuel", spa_index),
        Route("/progress", spa_index),
        Route("/settings", spa_index),
        Route("/{path:path}", spa_index),
    ]
    return routes
