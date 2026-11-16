"""Unit and integration tests for FORGE Garmin Performance Dashboard backend."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "src")):
    if p not in sys.path:
        sys.path.insert(0, p)

from dashboard.api.analytics import (
    analyze_body,
    analyze_engine,
    analyze_fuel,
    analyze_recovery,
    analyze_strength,
    audit_hr_zones,
    compute_e1rm,
    compute_weekly_forge_score,
    evaluate_session_recommendation,
    monday_of_week,
)
from dashboard.api.db import ensure_schema, get_conn, get_settings, update_settings
from dashboard.server import create_app


def _seed_sample_db(db_path: Path) -> None:
    ensure_schema(db_path)
    today = datetime.now().date()
    today_s = today.isoformat()
    week_start = monday_of_week(today)

    with get_conn(db_path) as conn:
        hr_zones = [
            {
                "sport": "DEFAULT",
                "trainingMethod": "HR_MAX",
                "restingHeartRateUsed": 63,
                "maxHeartRateUsed": 205,
                "lactateThresholdHeartRateUsed": 186,
                "restingHrAutoUpdateUsed": False,
                "zone1Floor": 103,
                "zone2Floor": 123,
                "zone3Floor": 144,
                "zone4Floor": 164,
                "zone5Floor": 185,
            }
        ]
        conn.execute(
            """
            INSERT INTO athlete_profile (
                id, full_name, device_name, gender, height_cm, weight_kg,
                vo2_max_running, lactate_threshold_hr, lactate_threshold_pace,
                lactate_threshold_power, hr_zones_json, updated_at
            ) VALUES (1, 'Ayush Kaushik', 'Forerunner 965', 'MALE', 162.6, 73.0, 48.0, 186, '5:05 /km', 310, ?, ?)
            """,
            (json.dumps(hr_zones), today_s + "T08:00:00Z"),
        )

        # 7 days of wellness
        for offset in range(7):
            d = (today - timedelta(days=offset)).isoformat()
            conn.execute(
                """
                INSERT INTO daily_wellness (
                    calendar_date, steps, step_goal, distance_km, active_kcal, total_kcal, bmr_kcal,
                    rhr, stress_avg, bb_peak, bb_low, bb_charged, bb_drained,
                    sleep_s, sleep_score, sleep_qualifier, deep_s, rem_s, light_s, awake_s,
                    hrv_night, hrv_weekly, hrv_status,
                    hydration_intake_ml, hydration_goal_ml, hydration_sweat_ml,
                    vo2_max, acute_load, chronic_load, acwr, acwr_status, training_status,
                    readiness_score, readiness_level, readiness_context, readiness_recovery_h, updated_at
                ) VALUES (?, 9500, 10000, 7.2, 620, 2520, 1900, ?, 28, 86, 22, 58, 60, ?, 82, 'GOOD', 5400, 6200, 14200, 600, 62, 60, 'BALANCED', 1500, 3500, 650, 48.0, 340, 290, 1.17, 'OPTIMAL', 'PRODUCTIVE', ?, 'HIGH', 'MORNING', 14.0, ?)
                """,
                (d, 56 if offset < 7 else 55, 27000, 78 if offset == 0 else 74, d + "T09:00:00Z"),
            )

        # Strength activity with warmup, working set, UNKNOWN, and suspicious-12 sets
        st_id = 90001
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, name, type, start_time_local, calendar_date,
                duration_s, moving_duration_s, calories, avg_hr, max_hr,
                training_load, sets_fetched
            ) VALUES (?, 'Push Day', 'strength_training', ?, ?, 3200, 3000, 310, 118, 148, 42, 1)
            """,
            (st_id, f"{week_start.isoformat()} 07:30:00", week_start.isoformat()),
        )

        raw_sets = {"activityId": st_id, "exerciseSets": []}
        sample_sets = [
            # Set 0: Warmup bench (50kg*10 vs max 100kg*5 -> warmup? 50 < 50? 40kg is < 50% of 100kg)
            ("ACTIVE", "BENCH_PRESS", "BARBELL_BENCH_PRESS", 10, 40.0, 90.0),
            # Set 1: Working heavy bench
            ("ACTIVE", "BENCH_PRESS", "BARBELL_BENCH_PRESS", 5, 100.0, 100.0),
            # Set 2: UNKNOWN watch detection
            ("ACTIVE", "UNKNOWN", None, 12, 15.0, 95.0),
            # Sets 3..7: Suspicious 5x12 default watch reps
            ("ACTIVE", "SHOULDER_PRESS", "DUMBBELL_SHOULDER_PRESS", 12, 20.0, 90.0),
            ("ACTIVE", "SHOULDER_PRESS", "DUMBBELL_SHOULDER_PRESS", 12, 20.0, 90.0),
            ("ACTIVE", "SHOULDER_PRESS", "DUMBBELL_SHOULDER_PRESS", 12, 20.0, 90.0),
            ("ACTIVE", "LATERAL_RAISE", "DUMBBELL_LATERAL_RAISE", 12, 10.0, 90.0),
            ("ACTIVE", "LATERAL_RAISE", "DUMBBELL_LATERAL_RAISE", 12, 10.0, 90.0),
        ]
        for idx, (stype, cat, name, reps, wkg, prob) in enumerate(sample_sets):
            raw_sets["exerciseSets"].append(
                {
                    "setType": stype,
                    "exercises": [{"category": cat, "name": name, "probability": prob}] if name else [{"category": cat, "probability": prob}],
                    "repetitionCount": reps,
                    "weight": wkg * 1000.0,
                    "duration": 35.0,
                    "startTime": f"{week_start.isoformat()}T07:{30+idx:02d}:00.000Z",
                }
            )
            conn.execute(
                """
                INSERT INTO exercise_sets (
                    activity_id, set_index, set_type, category, exercise_name, probability,
                    reps, weight_kg, duration_s, rest_s, start_time, user_corrected,
                    orig_category, orig_exercise_name, orig_reps, orig_weight_kg
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 35, 90, ?, 0, ?, ?, ?, ?)
                """,
                (st_id, idx, stype, cat, name, prob, reps, wkg, f"{week_start.isoformat()}T07:{30+idx:02d}:00.000Z", cat, name, reps, wkg),
            )
        conn.execute(
            "INSERT INTO raw_payloads (source_key, entity_key, payload_json, fetched_at) VALUES ('exercise_sets', ?, ?, ?)",
            (str(st_id), json.dumps(raw_sets), today_s),
        )

        # Running activity within 3h of same-day leg/lift to test interference & max HR
        run_id = 90002
        conn.execute(
            """
            INSERT INTO activities (
                activity_id, name, type, start_time_local, calendar_date,
                duration_s, moving_duration_s, distance_m, calories, avg_hr, max_hr,
                te_aerobic, te_anaerobic, training_load, avg_cadence, avg_power, norm_power,
                vo2_max, hr_z1_s, hr_z2_s, hr_z3_s, hr_z4_s, hr_z5_s
            ) VALUES (?, 'Tempo 5K', 'running', ?, ?, 1500, 1480, 5000, 420, 174, 197, 3.6, 1.1, 145, 176, 305, 315, 48.0, 60, 240, 300, 720, 180)
            """,
            (run_id, f"{week_start.isoformat()} 10:30:00", week_start.isoformat()),
        )


def test_e1rm_formulas():
    assert compute_e1rm(100.0, 5, "epley") == 116.7
    assert compute_e1rm(100.0, 1, "epley") == 100.0
    assert compute_e1rm(100.0, 12, "epley") is None  # Strictly gated 1..10 reps
    assert compute_e1rm(100.0, 5, "brzycki") == round(100.0 * 36.0 / 32.0, 1)


def test_strength_warmup_triage_and_e1rm(tmp_path: Path):
    db_path = tmp_path / "forge.db"
    _seed_sample_db(db_path)

    with get_conn(db_path) as conn:
        settings = get_settings(conn)
        res = analyze_strength(conn, settings)

    # 8 non-cardio sets total; warmup bench (40kg < 50% of 100kg) is excluded from chest direct_sets
    assert res["summary"]["total_active_sets"] == 8
    assert res["summary"]["unclassified_count"] == 1
    chest_vol = next(m for m in res["muscle_volume"] if m["muscle"] == "chest")
    assert chest_vol["direct_sets"] == 1
    # 1 UNKNOWN + 5 sets @ 12 reps -> triage items present
    assert len(res["triage_queue"]) >= 5
    # Top lift bench e1RM matches 100kg x 5 = 116.7kg
    assert res["exercises_progress"][0]["best_e1rm"] == 116.7


def test_readiness_rules_r0_to_r5(tmp_path: Path):
    db_path = tmp_path / "forge.db"
    _seed_sample_db(db_path)
    with get_conn(db_path) as conn:
        settings = get_settings(conn)
        st = analyze_strength(conn, settings)
        en = analyze_engine(conn, settings, days=14)
        rec = analyze_recovery(conn, settings, days=14)

    # R4 green path
    r4 = evaluate_session_recommendation(
        {"readiness_score": 82, "sleep_s": 7.5 * 3600, "hrv_status": "BALANCED", "rhr": 56, "acwr": 1.1},
        rec,
        st,
        en,
        settings,
    )
    assert r4["rule_id"] == "R4"
    assert r4["severity"] == "emerald"

    # R5 ACWR cap
    r5 = evaluate_session_recommendation(
        {"readiness_score": 82, "sleep_s": 7.5 * 3600, "hrv_status": "BALANCED", "rhr": 56, "acwr": 1.65},
        rec,
        st,
        en,
        settings,
    )
    assert r5["rule_id"] == "R5"
    assert r5["severity"] == "amber"

    # R0 illness override
    r0 = evaluate_session_recommendation(
        {"readiness_score": 90, "sleep_s": 8 * 3600, "hrv_status": "BALANCED", "rhr": 55, "acwr": 1.0},
        rec,
        st,
        en,
        {**settings, "illness_mode": True},
    )
    assert r0["rule_id"] == "R0"
    assert r0["severity"] == "crimson"


def test_forge_score_fuel_reweighting(tmp_path: Path):
    db_path = tmp_path / "forge.db"
    _seed_sample_db(db_path)
    with get_conn(db_path) as conn:
        settings = get_settings(conn)
        st = analyze_strength(conn, settings)
        en = analyze_engine(conn, settings, days=14)
        rec = analyze_recovery(conn, settings, days=14)
        fu_empty = analyze_fuel(conn, settings, days=14)
        score_empty = compute_weekly_forge_score(st, en, rec, fu_empty, settings)
        assert "fuel" in score_empty["excluded_pillars"]
        assert score_empty["fuel_pct"] is None

        conn.execute(
            "INSERT INTO nutrition_logs (calendar_date, recorded_at, calories, protein_g) VALUES (?, ?, 2500, 140)",
            (datetime.now().date().isoformat(), "2026-01-01T12:00:00Z"),
        )
        fu_logged = analyze_fuel(conn, settings, days=14)
        score_logged = compute_weekly_forge_score(st, en, rec, fu_logged, settings)
        assert "fuel" not in score_logged["excluded_pillars"]
        assert score_logged["fuel_pct"] is not None


def test_hr_zones_audit_and_body_ewma(tmp_path: Path):
    db_path = tmp_path / "forge.db"
    _seed_sample_db(db_path)
    today = datetime.now().date()
    with get_conn(db_path) as conn:
        audit = audit_hr_zones(conn)
        assert audit["is_stale"] is True
        assert audit["configured_rhr"] == 63
        assert audit["measured_rhr_7d"] == 56
        assert audit["observed_max_hr_90d"] == 197

        # Seed 5 weigh-ins and 1 tape measurement
        for i, w in enumerate([73.2, 73.4, 73.5, 73.7, 73.8]):
            conn.execute(
                "INSERT INTO body_measurements (calendar_date, recorded_at, weight_kg, source) VALUES (?, ?, ?, 'manual')",
                ((today - timedelta(days=4 - i)).isoformat(), f"2026-01-0{i+1}T08:00:00Z", w),
            )
        conn.execute(
            "INSERT INTO body_measurements (calendar_date, recorded_at, waist_cm, neck_cm, chest_cm, arm_cm, source) VALUES (?, ?, 79.0, 38.0, 102.0, 36.0, 'tape')",
            (today.isoformat(), "2026-01-05T08:05:00Z"),
        )
        body = analyze_body(conn, get_settings(conn))

    assert body["rate_kg_week"] is not None
    assert body["body_fat_pct"] is not None
    assert body["ffmi"] is not None
    assert body["nffmi"] is not None
    assert body["waist_arm_ratio"] == round(79.0 / 36.0, 2)


def test_http_routes_end_to_end(tmp_path: Path):
    db_path = tmp_path / "forge.db"
    _seed_sample_db(db_path)
    app = create_app(db_path=db_path, start_scheduler=False)
    client = TestClient(app)

    for path in ("/api/today", "/api/strength", "/api/engine", "/api/recovery", "/api/body", "/api/fuel", "/api/progress", "/api/settings", "/api/overview"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} failed: {r.text}"

    # Local strength triage edit + Garmin preview (confirm=false)
    edit_r = client.patch(
        "/api/strength/sets/90001/local",
        json={"edits": [{"set_index": 2, "category": "CURL", "exercise_name": "DUMBBELL_BICEPS_CURL", "reps": 10, "weight_kg": 15.0}]},
    )
    assert edit_r.status_code == 200
    assert edit_r.json()["updated"] == 1

    preview_r = client.post("/api/strength/sets/90001/push", json={"confirm": False})
    assert preview_r.status_code == 200
    assert preview_r.json()["preview"] is True
    assert preview_r.json()["changes_count"] == 1

    # Weigh-in & hydration without external Garmin network call
    w_r = client.post("/api/body/weigh-in", json={"weight_kg": 73.5, "sync_to_garmin": False})
    assert w_r.status_code == 200
    assert w_r.json()["latest_weight_kg"] == 73.5

    h_r = client.post("/api/hydration", json={"value_ml": 500, "sync_to_garmin": False})
    assert h_r.status_code == 200
    assert h_r.json()["intake_ml"] >= 500

    # Fuel log
    f_r = client.post("/api/fuel/log", json={"calories": 650, "protein_g": 45, "label": "Chicken Rice Bowl"})
    assert f_r.status_code == 200
    assert f_r.json()["daily"][-1]["protein_g"] == 45.0

    # HR zone preview (no Garmin write when confirm=false)
    hz_r = client.post("/api/settings/hr-zones", json={"training_method": "LACTATE_THRESHOLD", "lactate_threshold_hr": 186, "max_hr": 197, "resting_hr": 56, "confirm": False})
    assert hz_r.status_code == 200
    assert hz_r.json()["preview"] is True
    assert hz_r.json()["after"]["trainingMethod"] == "LACTATE_THRESHOLD"
    assert hz_r.json()["after"]["zone5Floor"] == 186

    # Export markdown
    md_r = client.get("/api/progress/export?format=markdown")
    assert md_r.status_code == 200
    assert "FORGE Weekly Performance Review" in md_r.text
