"""Garmin exercise taxonomy -> hypertrophy muscle-group mapping and balance classification."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

# Canonical muscle groups tracked in FORGE's Hypertrophy Lab
MUSCLE_GROUPS: List[Dict[str, str]] = [
    {"id": "chest", "label": "Chest", "region": "upper", "pattern": "push"},
    {"id": "back", "label": "Back (Lats / Mid)", "region": "upper", "pattern": "pull"},
    {"id": "shoulders", "label": "Shoulders (Side/Front)", "region": "upper", "pattern": "push"},
    {"id": "rear_delts", "label": "Rear Delts", "region": "upper", "pattern": "pull"},
    {"id": "biceps", "label": "Biceps", "region": "upper", "pattern": "pull"},
    {"id": "triceps", "label": "Triceps", "region": "upper", "pattern": "push"},
    {"id": "quads", "label": "Quads", "region": "lower", "pattern": "quad"},
    {"id": "hamstrings", "label": "Hamstrings", "region": "lower", "pattern": "hinge"},
    {"id": "glutes", "label": "Glutes", "region": "lower", "pattern": "hinge"},
    {"id": "calves", "label": "Calves", "region": "lower", "pattern": "lower"},
    {"id": "lower_back", "label": "Lower Back", "region": "core", "pattern": "hinge"},
    {"id": "traps", "label": "Traps", "region": "upper", "pattern": "pull"},
    {"id": "core", "label": "Core / Abs", "region": "core", "pattern": "core"},
]

MUSCLE_META: Dict[str, Dict[str, str]] = {m["id"]: m for m in MUSCLE_GROUPS}

# Default category -> (primary_muscle, secondary_muscles)
DEFAULT_CATEGORY_MAP: Dict[str, Tuple[str, List[str]]] = {
    "BENCH_PRESS": ("chest", ["triceps", "shoulders"]),
    "CHEST_PRESS": ("chest", ["triceps", "shoulders"]),
    "FLYE": ("chest", ["shoulders"]),
    "PUSH_UP": ("chest", ["triceps", "shoulders"]),
    "DIP": ("chest", ["triceps", "shoulders"]),
    "PULL_UP": ("back", ["biceps", "rear_delts"]),
    "ROW": ("back", ["biceps", "rear_delts", "traps"]),
    "LAT_PULLDOWN": ("back", ["biceps", "rear_delts"]),
    "SHOULDER_PRESS": ("shoulders", ["triceps"]),
    "LATERAL_RAISE": ("shoulders", ["traps"]),
    "SHRUG": ("traps", ["back"]),
    "CURL": ("biceps", []),
    "TRICEPS_EXTENSION": ("triceps", []),
    "SQUAT": ("quads", ["glutes", "lower_back"]),
    "LUNGE": ("quads", ["glutes"]),
    "LEG_PRESS": ("quads", ["glutes"]),
    "LEG_CURL": ("hamstrings", []),
    "DEADLIFT": ("hamstrings", ["glutes", "lower_back", "traps"]),
    "HIP_RAISE": ("glutes", ["hamstrings"]),
    "HIP_STABILITY": ("glutes", ["core"]),
    "HYPEREXTENSION": ("lower_back", ["glutes", "hamstrings"]),
    "CALF_RAISE": ("calves", []),
    "CRUNCH": ("core", []),
    "PLANK": ("core", []),
    "CORE": ("core", []),
    "SIT_UP": ("core", []),
    "LEG_RAISE": ("core", []),
    "CARRY": ("traps", ["core", "glutes"]),
    "CARDIO": ("cardio", []),
    "TOTAL_BODY": ("quads", ["chest", "back", "shoulders"]),
    "OLYMPIC_LIFT": ("quads", ["glutes", "traps", "shoulders"]),
}

# Exercise-name overrides where Garmin's category is misleading for muscle attribution
DEFAULT_EXERCISE_OVERRIDES: Dict[Tuple[str, str], Tuple[str, List[str]]] = {
    ("FLYE", "INCLINE_REVERSE_FLYE"): ("rear_delts", ["back"]),
    ("FLYE", "REVERSE_FLYE"): ("rear_delts", ["back"]),
    ("FLYE", "DUMBBELL_REVERSE_FLYE"): ("rear_delts", ["back"]),
    ("FLYE", "CABLE_REVERSE_FLYE"): ("rear_delts", ["back"]),
    ("ROW", "FACE_PULL"): ("rear_delts", ["traps", "back"]),
    ("DEADLIFT", "ROMANIAN_DEADLIFT"): ("hamstrings", ["glutes", "lower_back"]),
    ("DEADLIFT", "DUMBBELL_ROMANIAN_DEADLIFT"): ("hamstrings", ["glutes", "lower_back"]),
    ("DEADLIFT", "SINGLE_LEG_ROMANIAN_DEADLIFT"): ("hamstrings", ["glutes"]),
    ("DEADLIFT", "STIFF_LEG_DEADLIFT"): ("hamstrings", ["glutes", "lower_back"]),
    ("TRICEPS_EXTENSION", "LYING_DUMBBELL_PULLOVER_TO_EXTENSION"): ("triceps", ["chest", "back"]),
    ("SQUAT", "GOBLET_SQUAT"): ("quads", ["glutes", "core"]),
    ("SQUAT", "BARBELL_BACK_SQUAT"): ("quads", ["glutes", "lower_back"]),
    ("SQUAT", "LEG_PRESS"): ("quads", ["glutes"]),
    ("BENCH_PRESS", "CLOSE_GRIP_BARBELL_BENCH_PRESS"): ("triceps", ["chest"]),
}

# Curated common Garmin Connect exercise presets for the inline triage dropdown
TRIAGE_PRESETS: List[Dict[str, str]] = [
    {"category": "BENCH_PRESS", "exercise_name": "BARBELL_BENCH_PRESS", "label": "Barbell Bench Press"},
    {"category": "BENCH_PRESS", "exercise_name": "DUMBBELL_BENCH_PRESS", "label": "Dumbbell Bench Press"},
    {"category": "BENCH_PRESS", "exercise_name": "INCLINE_DUMBBELL_BENCH_PRESS", "label": "Incline Dumbbell Bench Press"},
    {"category": "BENCH_PRESS", "exercise_name": "DECLINE_DUMBBELL_BENCH_PRESS", "label": "Decline Dumbbell Bench Press"},
    {"category": "FLYE", "exercise_name": "INCLINE_DUMBBELL_FLYE", "label": "Incline Dumbbell Flye"},
    {"category": "FLYE", "exercise_name": "INCLINE_REVERSE_FLYE", "label": "Incline Reverse Flye (Rear Delts)"},
    {"category": "PUSH_UP", "exercise_name": "", "label": "Push-Up"},
    {"category": "PULL_UP", "exercise_name": "PULL_UP", "label": "Pull-Up"},
    {"category": "PULL_UP", "exercise_name": "BAND_ASSISTED_PULL_UP", "label": "Band-Assisted Pull-Up"},
    {"category": "PULL_UP", "exercise_name": "LAT_PULLDOWN", "label": "Lat Pulldown"},
    {"category": "PULL_UP", "exercise_name": "_30_DEGREE_LAT_PULLDOWN", "label": "30-Degree Lat Pulldown"},
    {"category": "ROW", "exercise_name": "SEATED_CABLE_ROW", "label": "Seated Cable Row"},
    {"category": "ROW", "exercise_name": "WIDE_GRIP_SEATED_CABLE_ROW", "label": "Wide-Grip Seated Cable Row"},
    {"category": "ROW", "exercise_name": "BENT_OVER_ROW", "label": "Barbell Bent-Over Row"},
    {"category": "ROW", "exercise_name": "ONE_ARM_DUMBBELL_ROW", "label": "One-Arm Dumbbell Row"},
    {"category": "ROW", "exercise_name": "FACE_PULL", "label": "Face Pull (Rear Delts)"},
    {"category": "SHOULDER_PRESS", "exercise_name": "DUMBBELL_SHOULDER_PRESS", "label": "Dumbbell Shoulder Press"},
    {"category": "SHOULDER_PRESS", "exercise_name": "OVERHEAD_BARBELL_PRESS", "label": "Overhead Barbell Press"},
    {"category": "LATERAL_RAISE", "exercise_name": "DUMBBELL_LATERAL_RAISE", "label": "Dumbbell Lateral Raise"},
    {"category": "CURL", "exercise_name": "DUMBBELL_BICEPS_CURL", "label": "Dumbbell Biceps Curl"},
    {"category": "CURL", "exercise_name": "HAMMER_CURL", "label": "Hammer Curl"},
    {"category": "TRICEPS_EXTENSION", "exercise_name": "CABLE_OVERHEAD_TRICEPS_EXTENSION", "label": "Cable Triceps Extension"},
    {"category": "TRICEPS_EXTENSION", "exercise_name": "TRICEPS_PUSHDOWN", "label": "Triceps Pushdown"},
    {"category": "SQUAT", "exercise_name": "BARBELL_BACK_SQUAT", "label": "Barbell Back Squat"},
    {"category": "SQUAT", "exercise_name": "GOBLET_SQUAT", "label": "Goblet Squat"},
    {"category": "SQUAT", "exercise_name": "LEG_PRESS", "label": "Leg Press"},
    {"category": "LUNGE", "exercise_name": "WALKING_LUNGE", "label": "Walking Lunge"},
    {"category": "LUNGE", "exercise_name": "BULGARIAN_SPLIT_SQUAT", "label": "Bulgarian Split Squat"},
    {"category": "DEADLIFT", "exercise_name": "BARBELL_DEADLIFT", "label": "Barbell Deadlift"},
    {"category": "DEADLIFT", "exercise_name": "ROMANIAN_DEADLIFT", "label": "Romanian Deadlift"},
    {"category": "LEG_CURL", "exercise_name": "LYING_LEG_CURL", "label": "Lying Leg Curl"},
    {"category": "HIP_RAISE", "exercise_name": "BARBELL_HIP_THRUST", "label": "Barbell Hip Thrust"},
    {"category": "CALF_RAISE", "exercise_name": "STANDING_CALF_RAISE", "label": "Standing Calf Raise"},
    {"category": "HYPEREXTENSION", "exercise_name": "STATIC_BACK_EXTENSION", "label": "Back Extension"},
    {"category": "SHRUG", "exercise_name": "DUMBBELL_SHRUG", "label": "Dumbbell Shrug"},
    {"category": "CRUNCH", "exercise_name": "CRUNCH", "label": "Crunch / Cable Crunch"},
    {"category": "PLANK", "exercise_name": "PLANK", "label": "Plank"},
]


def resolve_muscle_mapping(
    category: Optional[str],
    exercise_name: Optional[str],
    custom_map: Optional[Dict[Tuple[str, str], Tuple[str, List[str]]]] = None,
) -> Tuple[str, List[str]]:
    """Resolve (primary_muscle, secondary_muscles) for a Garmin category & exercise_name."""
    cat = (category or "UNKNOWN").strip().upper()
    name = (exercise_name or "").strip().upper()

    if custom_map:
        if (cat, name) in custom_map:
            return custom_map[(cat, name)]
        if (cat, "") in custom_map:
            return custom_map[(cat, "")]

    if (cat, name) in DEFAULT_EXERCISE_OVERRIDES:
        return DEFAULT_EXERCISE_OVERRIDES[(cat, name)]
    if cat in DEFAULT_CATEGORY_MAP:
        return DEFAULT_CATEGORY_MAP[cat]
    return ("unknown", [])
