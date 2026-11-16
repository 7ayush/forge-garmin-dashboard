"""SQLite persistence layer (WAL mode) for FORGE Garmin Performance Dashboard."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .exercise_taxonomy import DEFAULT_CATEGORY_MAP, DEFAULT_EXERCISE_OVERRIDES

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "forge.db"
PHOTOS_DIR = Path(__file__).resolve().parent.parent / "data" / "photos"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "muscle_set_min": 10,
    "muscle_set_max": 20,
    "lifting_freq_target": 4,
    "z2_target_pct": 75,
    "protein_g_per_kg": 1.6,
    "protein_max_g_per_kg": 2.2,
    "sleep_target_h": 7.0,
    "sleep_debt_target_h": 7.5,
    "gain_rate_pct_month": 0.75,
    "calorie_target": 2600,
    "illness_mode": False,
    "e1rm_formula": "epley",
    "exclude_warmups": True,
    "readiness_heavy_min": 70,
    "readiness_moderate_min": 50,
    "readiness_rest_max": 25,
    "acwr_caution": 1.3,
    "acwr_danger": 1.5,
    "interference_window_hours": 6.0,
    "target_event": "Sub-2:00 Half Marathon + 1.0x/1.5x/2.0x BW Lifts",
}

_INIT_LOCK = threading.Lock()
_INITIALIZED_PATHS: set[str] = set()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_schema(db_path)
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_schema(db_path: Path = DEFAULT_DB_PATH) -> None:
    key = str(db_path.resolve())
    if key in _INITIALIZED_PATHS:
        return
    with _INIT_LOCK:
        if key in _INITIALIZED_PATHS:
            return
        db_path.parent.mkdir(parents=True, exist_ok=True)
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS raw_payloads (
                    source_key TEXT NOT NULL,
                    entity_key TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (source_key, entity_key)
                );

                CREATE TABLE IF NOT EXISTS athlete_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    full_name TEXT,
                    device_name TEXT,
                    gender TEXT,
                    birth_date TEXT,
                    height_cm REAL,
                    weight_kg REAL,
                    vo2_max_running REAL,
                    lactate_threshold_hr INTEGER,
                    lactate_threshold_pace TEXT,
                    lactate_threshold_power INTEGER,
                    unit_system TEXT,
                    profile_json TEXT,
                    hr_zones_json TEXT,
                    race_predictions_json TEXT,
                    personal_records_json TEXT,
                    badges_json TEXT,
                    fitness_age_json TEXT,
                    endurance_json TEXT,
                    hill_json TEXT,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS activities (
                    activity_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    event_type TEXT,
                    start_time_local TEXT NOT NULL,
                    calendar_date TEXT NOT NULL,
                    duration_s REAL DEFAULT 0,
                    moving_duration_s REAL DEFAULT 0,
                    distance_m REAL DEFAULT 0,
                    calories REAL DEFAULT 0,
                    avg_hr REAL,
                    max_hr REAL,
                    te_aerobic REAL DEFAULT 0,
                    te_anaerobic REAL DEFAULT 0,
                    te_label TEXT,
                    training_load REAL DEFAULT 0,
                    avg_cadence REAL,
                    avg_power REAL,
                    norm_power REAL,
                    avg_stride_cm REAL,
                    avg_gct_ms REAL,
                    avg_vo_cm REAL,
                    elevation_gain REAL DEFAULT 0,
                    vo2_max REAL,
                    bb_impact INTEGER,
                    rpe INTEGER,
                    feel INTEGER,
                    hr_z1_s REAL DEFAULT 0,
                    hr_z2_s REAL DEFAULT 0,
                    hr_z3_s REAL DEFAULT 0,
                    hr_z4_s REAL DEFAULT 0,
                    hr_z5_s REAL DEFAULT 0,
                    has_splits INTEGER DEFAULT 0,
                    sets_fetched INTEGER DEFAULT 0,
                    raw_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(calendar_date DESC);
                CREATE INDEX IF NOT EXISTS idx_activities_type ON activities(type, calendar_date DESC);

                CREATE TABLE IF NOT EXISTS exercise_sets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    activity_id INTEGER NOT NULL,
                    set_index INTEGER NOT NULL,
                    set_type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    exercise_name TEXT,
                    probability REAL,
                    reps INTEGER,
                    weight_kg REAL,
                    duration_s REAL,
                    rest_s REAL,
                    start_time TEXT,
                    user_corrected INTEGER DEFAULT 0,
                    orig_category TEXT,
                    orig_exercise_name TEXT,
                    orig_reps INTEGER,
                    orig_weight_kg REAL,
                    FOREIGN KEY (activity_id) REFERENCES activities(activity_id) ON DELETE CASCADE,
                    UNIQUE (activity_id, set_index)
                );

                CREATE INDEX IF NOT EXISTS idx_sets_activity ON exercise_sets(activity_id);

                CREATE TABLE IF NOT EXISTS exercise_muscle_map (
                    category TEXT NOT NULL,
                    exercise_name TEXT NOT NULL DEFAULT '',
                    primary_muscle TEXT NOT NULL,
                    secondary_muscles_json TEXT NOT NULL DEFAULT '[]',
                    is_custom INTEGER DEFAULT 0,
                    PRIMARY KEY (category, exercise_name)
                );

                CREATE TABLE IF NOT EXISTS daily_wellness (
                    calendar_date TEXT PRIMARY KEY,
                    steps INTEGER DEFAULT 0,
                    step_goal INTEGER DEFAULT 10000,
                    distance_km REAL DEFAULT 0,
                    active_kcal REAL DEFAULT 0,
                    total_kcal REAL DEFAULT 0,
                    bmr_kcal REAL DEFAULT 0,
                    floors REAL DEFAULT 0,
                    im_moderate INTEGER DEFAULT 0,
                    im_vigorous INTEGER DEFAULT 0,
                    rhr INTEGER,
                    min_hr INTEGER,
                    max_hr INTEGER,
                    stress_avg INTEGER,
                    stress_max INTEGER,
                    bb_charged INTEGER,
                    bb_drained INTEGER,
                    bb_peak INTEGER,
                    bb_low INTEGER,
                    sleep_s INTEGER,
                    nap_s INTEGER DEFAULT 0,
                    sleep_score INTEGER,
                    sleep_qualifier TEXT,
                    deep_s INTEGER,
                    rem_s INTEGER,
                    light_s INTEGER,
                    awake_s INTEGER,
                    sleep_start_ms INTEGER,
                    sleep_end_ms INTEGER,
                    avg_sleep_stress REAL,
                    hrv_night INTEGER,
                    hrv_5min_high INTEGER,
                    hrv_weekly INTEGER,
                    hrv_status TEXT,
                    hydration_intake_ml REAL DEFAULT 0,
                    hydration_goal_ml REAL DEFAULT 3500,
                    hydration_sweat_ml REAL DEFAULT 0,
                    resp_sleep REAL,
                    resp_wake REAL,
                    spo2_avg REAL,
                    vo2_max REAL,
                    vo2_carried_forward INTEGER DEFAULT 0,
                    acute_load INTEGER,
                    chronic_load INTEGER,
                    acwr REAL,
                    acwr_status TEXT,
                    acwr_percent INTEGER,
                    training_status TEXT,
                    load_aerobic_low REAL,
                    load_aerobic_high REAL,
                    load_anaerobic REAL,
                    load_balance_feedback TEXT,
                    readiness_score INTEGER,
                    readiness_level TEXT,
                    readiness_context TEXT,
                    readiness_recovery_h REAL,
                    updated_at TEXT
                );

                CREATE TABLE IF NOT EXISTS readiness_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calendar_date TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    context TEXT,
                    score INTEGER,
                    level TEXT,
                    feedback TEXT,
                    recovery_time_h REAL,
                    sleep_score INTEGER,
                    hrv_weekly_avg INTEGER,
                    acute_load INTEGER,
                    factors_json TEXT,
                    UNIQUE (calendar_date, timestamp)
                );

                CREATE TABLE IF NOT EXISTS body_measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calendar_date TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    weight_kg REAL,
                    body_fat_pct REAL,
                    body_fat_source TEXT,
                    waist_cm REAL,
                    chest_cm REAL,
                    arm_cm REAL,
                    thigh_cm REAL,
                    shoulder_cm REAL,
                    neck_cm REAL,
                    notes TEXT,
                    source TEXT NOT NULL DEFAULT 'manual',
                    synced_to_garmin INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_body_date ON body_measurements(calendar_date DESC);

                CREATE TABLE IF NOT EXISTS nutrition_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calendar_date TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    calories REAL DEFAULT 0,
                    protein_g REAL DEFAULT 0,
                    carbs_g REAL DEFAULT 0,
                    fat_g REAL DEFAULT 0,
                    label TEXT,
                    source TEXT NOT NULL DEFAULT 'quick_log'
                );

                CREATE INDEX IF NOT EXISTS idx_nutrition_date ON nutrition_logs(calendar_date DESC);

                CREATE TABLE IF NOT EXISTS progress_photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calendar_date TEXT NOT NULL,
                    pose TEXT NOT NULL DEFAULT 'front',
                    filename TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_written INTEGER DEFAULT 0,
                    latency_ms INTEGER DEFAULT 0,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target TEXT NOT NULL,
                    before_json TEXT,
                    after_json TEXT,
                    garmin_response_json TEXT
                );
                """
            )

            # Seed default exercise muscle mappings if not already populated
            for cat, (primary, secondary) in DEFAULT_CATEGORY_MAP.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO exercise_muscle_map
                    (category, exercise_name, primary_muscle, secondary_muscles_json, is_custom)
                    VALUES (?, '', ?, ?, 0)
                    """,
                    (cat, primary, json.dumps(secondary)),
                )
            for (cat, name), (primary, secondary) in DEFAULT_EXERCISE_OVERRIDES.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO exercise_muscle_map
                    (category, exercise_name, primary_muscle, secondary_muscles_json, is_custom)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (cat, name, primary, json.dumps(secondary)),
                )

            now = utcnow_iso()
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO app_settings (key, value_json, updated_at) VALUES (?, ?, ?)",
                    (k, json.dumps(v), now),
                )

            conn.commit()
        finally:
            conn.close()
        _INITIALIZED_PATHS.add(key)


def get_settings(conn: sqlite3.Connection) -> Dict[str, Any]:
    rows = conn.execute("SELECT key, value_json FROM app_settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for r in rows:
        try:
            settings[r["key"]] = json.loads(r["value_json"])
        except json.JSONDecodeError:
            pass
    return settings


def update_settings(conn: sqlite3.Connection, updates: Dict[str, Any]) -> Dict[str, Any]:
    now = utcnow_iso()
    for k, v in updates.items():
        if k in DEFAULT_SETTINGS:
            conn.execute(
                """
                INSERT INTO app_settings (key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at
                """,
                (k, json.dumps(v), now),
            )
    return get_settings(conn)


def load_muscle_map(conn: sqlite3.Connection) -> Dict[Tuple[str, str], Tuple[str, List[str]]]:
    rows = conn.execute(
        "SELECT category, exercise_name, primary_muscle, secondary_muscles_json FROM exercise_muscle_map"
    ).fetchall()
    out: Dict[Tuple[str, str], Tuple[str, List[str]]] = {}
    for r in rows:
        try:
            sec = json.loads(r["secondary_muscles_json"] or "[]")
        except json.JSONDecodeError:
            sec = []
        out[(r["category"].upper(), (r["exercise_name"] or "").upper())] = (
            r["primary_muscle"],
            sec,
        )
    return out


def log_sync_run(
    conn: sqlite3.Connection,
    started_at: str,
    ended_at: str,
    scope: str,
    endpoint: str,
    status: str,
    records_written: int,
    latency_ms: int,
    error: Optional[str] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO sync_runs (started_at, ended_at, scope, endpoint, status, records_written, latency_ms, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (started_at, ended_at, scope, endpoint, status, records_written, latency_ms, error),
    )


def log_audit(
    conn: sqlite3.Connection,
    action: str,
    target: str,
    before_obj: Any,
    after_obj: Any,
    garmin_response: Any = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (created_at, action, target, before_json, after_json, garmin_response_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            utcnow_iso(),
            action,
            target,
            json.dumps(before_obj, default=str) if before_obj is not None else None,
            json.dumps(after_obj, default=str) if after_obj is not None else None,
            json.dumps(garmin_response, default=str) if garmin_response is not None else None,
        ),
    )
