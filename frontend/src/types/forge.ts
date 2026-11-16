export type PageRoute =
  | "today"
  | "strength"
  | "engine"
  | "recovery"
  | "body"
  | "fuel"
  | "progress"
  | "tips"
  | "settings";

export type SeverityTone = "emerald" | "lime" | "cyan" | "amber" | "crimson" | "neutral";

export interface SyncState {
  running: boolean;
  scope: string | null;
  progress: number;
  total: number;
  current_step: string;
  last_sync_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  circuit_open: boolean;
}

export interface AthleteProfileSummary {
  name: string;
  device: string;
  weight_kg: number;
  height_cm: number;
  vo2_max: number | null;
  lthr: number | null;
  lt_pace: string | null;
}

export interface SessionRecommendation {
  rule_id: string;
  severity: SeverityTone;
  verdict: string;
  sub_verdict: string;
  target_muscle: string;
  reasons: string[];
  confidence: "HIGH" | "MEDIUM" | "LOW";
  missing_inputs: string[];
}

export interface ForgeScoreSummary {
  overall: number;
  train_pct: number;
  fuel_pct: number | null;
  recover_pct: number;
  excluded_pillars: string[];
  muscles_at_target: string;
  lifts_this_week: string;
  sleep_nights_hit: string;
  protein_days_hit: string;
}

export interface MuscleVolumeEntry {
  muscle: string;
  label: string;
  region: string;
  pattern: string;
  direct_sets: number;
  fractional_sets: number;
  all_time_direct: number;
  target_min: number;
  target_max: number;
  last_trained: string | null;
  days_since: number | null;
  status: "below_target" | "optimal" | "above_target" | "untrained" | string;
}

export interface ActivitySummaryItem {
  activityId: number;
  name: string;
  type: string;
  startTimeLocal: string;
  date: string;
  distanceKm: number;
  durationSec: number;
  durationFormatted: string;
  paceFormatted: string | null;
  calories: number;
  avgHr: number | null;
  maxHr: number | null;
  aerobicTe: number;
  anaerobicTe: number;
  trainingLoad: number;
  avgPower: number | null;
  normPower: number | null;
  avgCadence: number | null;
  rpe: number | null;
  feel: number | null;
  z1_2_pct: number | null;
  hasPolyline?: boolean;
  locationName?: string | null;
}

export interface TodayAlert {
  id: string;
  severity: SeverityTone;
  title: string;
  cta: string;
  route: PageRoute;
}

export interface TodayPayload {
  date: string;
  athlete: AthleteProfileSummary;
  sync: SyncState;
  recommendation: SessionRecommendation;
  forge_score: ForgeScoreSummary;
  bio_health_index: {
    overall: number;
    pillars: {
      sleep: number;
      recovery: number;
      activity: number;
      autonomic: number;
    };
  };
  vitals: {
    readiness: number | null;
    readiness_level: string | null;
    readiness_context: string | null;
    recovery_time_h: number | null;
    sleep_h: number | null;
    sleep_score: number | null;
    sleep_debt_7d_h: number;
    hrv_night: number | null;
    hrv_weekly: number | null;
    hrv_status: string | null;
    rhr: number | null;
    rhr_baseline_28d: number | null;
    bb_peak: number | null;
    bb_low: number | null;
    bb_charged: number | null;
    bb_drained: number | null;
    stress_avg: number | null;
    acwr: number | null;
    acwr_status: string | null;
    acute_load: number | null;
    steps_today: number | null;
    step_goal: number;
  };
  sparklines: {
    readiness: (number | null)[];
    hrv: (number | null)[];
    rhr: (number | null)[];
    sleep: (number | null)[];
    stress?: (number | null)[];
    steps?: (number | null)[];
  };
  muscle_recency: MuscleVolumeEntry[];
  alerts: TodayAlert[];
  readiness_timeline: Array<{
    calendar_date: string;
    timestamp: string;
    context: string | null;
    score: number | null;
    level: string | null;
    recovery_time_h: number | null;
  }>;
  recent_activities: ActivitySummaryItem[];
}

export interface BalanceRatioBlock {
  push_sets: number;
  pull_sets: number;
  push_pull_ratio: number | null;
  upper_sets: number;
  lower_sets: number;
  upper_lower_ratio: number | null;
  quads_sets: number;
  hamstrings_sets: number;
  quad_ham_ratio: number | null;
}

export interface TriageItem {
  id: number;
  activity_id: number;
  activity_name: string;
  calendar_date: string;
  set_index: number;
  category: string;
  exercise_name: string | null;
  probability: number | null;
  reps: number | null;
  weight_kg: number | null;
  duration_s: number | null;
  issues: string[];
}

export interface ExerciseProgressItem {
  exercise: string;
  total_sets: number;
  non_qualifying_sets: number;
  best_e1rm: number | null;
  rolling_28d_e1rm: number | null;
  latest_weight: number;
  latest_reps: number;
  overload_status: "pr" | "stalled" | "building_baseline" | string;
  series: Array<{
    date: string;
    best_e1rm: number;
    best_weight: number;
    best_reps: number;
    best_volume_set: number;
  }>;
  note: string | null;
}

export interface StrengthPayload {
  week_start: string;
  week_end: string;
  available_weeks: string[];
  e1rm_formula: string;
  exclude_warmups: boolean;
  summary: {
    total_sessions: number;
    sessions_this_week: number;
    total_active_sets: number;
    verified_sets: number;
    verified_pct: number;
    unclassified_count: number;
    total_triage_count: number;
    total_tonnage_kg: number;
    avg_rest_sec: number | null;
  };
  muscle_volume: MuscleVolumeEntry[];
  balance_week: BalanceRatioBlock;
  balance_all_time: BalanceRatioBlock;
  triage_queue: TriageItem[];
  triage_presets: Array<{ label: string; category: string; exercise_name: string }>;
  exercises_progress: ExerciseProgressItem[];
  weekly_tonnage: Array<{ week_start: string; tonnage_kg: number }>;
  session_summaries: Array<{
    activity_id: number;
    name: string;
    calendar_date: string;
    start_time_local: string;
    duration_min: number;
    working_sets: number;
    tonnage_kg: number;
    density_kg_per_min: number;
    issue_count: number;
    muscles: Record<string, number>;
    avg_hr: number | null;
  }>;
  session_comparisons: Array<{
    template: string;
    current: { calendar_date: string; tonnage_kg: number; working_sets: number };
    previous: { calendar_date: string; tonnage_kg: number; working_sets: number };
    tonnage_delta_kg: number;
    sets_delta: number;
  }>;
  relative_strength: Array<{
    lift: string;
    e1rm: number | null;
    novice: number;
    inter: number;
    adv: number;
    bw_ratio: number | null;
  }>;
  missing_volume_plan: Array<{ muscle: string; label: string; done: number; needed: number }>;
  bodyweight_kg: number;
}

export interface ZoneSummaryBlock {
  zones_sec: number[];
  zones_pct: number[];
  total_zone_min: number;
  z2_discipline_pct: number | null;
  z4_z5_min: number;
}

export interface EnginePayload {
  days: number;
  z2_target_pct: number;
  zones_window: ZoneSummaryBlock;
  zones_week: ZoneSummaryBlock;
  training_status: {
    status: string | null;
    acute_load: number | null;
    chronic_load: number | null;
    acwr: number | null;
    acwr_status: string | null;
    acwr_percent: number | null;
    load_aerobic_low: number | null;
    load_aerobic_high: number | null;
    load_anaerobic: number | null;
    load_balance_feedback: string | null;
  };
  vo2_trend: Array<{ date: string; vo2_max: number; carried_forward?: boolean }>;
  load_trend: Array<{
    date: string;
    acute_load: number | null;
    chronic_load: number | null;
    acwr: number | null;
    training_status?: string | null;
  }>;
  efficiency_series: Array<{
    date: string;
    name: string;
    distance_km: number;
    pace: string | null;
    avg_hr: number;
    efficiency_index: number;
    power_hr: number | null;
    cadence: number | null;
    gct_ms: number | null;
    vo_cm: number | null;
    stride_cm: number | null;
  }>;
  interference_events: Array<{
    cardio_date: string;
    cardio_name: string;
    strength_date: string;
    strength_name: string;
    gap_hours: number;
    te_aerobic: number | null;
  }>;
  interference_warnings: string[];
  endurance: { overall: number | null; avg: number | null; max: number | null };
  hill: { overall: number | null; strength: number | null; endurance: number | null };
  lactate: { lthr: number | null; pace: string | null; power_watts: number | null };
  race_predictions: Record<string, { seconds: number; formatted: string; pace: string }>;
  personal_records: Array<{
    typeId: number;
    label: string;
    displayValue: string;
    activityName: string;
    date: string;
  }>;
  activities: ActivitySummaryItem[];
}

export interface RecoveryPayload {
  days: number;
  sleep_target_h: number;
  summary: {
    avg_sleep_h: number | null;
    nights_tracked_7d: number;
    nights_under_5h_win: number;
    sleep_debt_7d_h: number;
    bedtime_sd_min: number | null;
    avg_sleep_score: number | null;
    rhr_latest: number | null;
    rhr_baseline_28d: number | null;
    rhr_spike_alert: boolean;
    hrv_latest: number | null;
    hrv_weekly: number | null;
    hrv_status: string | null;
    hrv_baseline_28d: number | null;
    spo2_available: boolean;
    spo2_hint: string | null;
  };
  daily: Array<{
    date: string;
    sleepHours: number | null;
    sleepScore: number | null;
    deepHours: number;
    remHours: number;
    lightHours: number;
    awakeHours: number;
    hrvNight: number | null;
    hrvWeekly: number | null;
    hrv5MinHigh: number | null;
    hrvStatus: string | null;
    rhr: number | null;
    stressAvg: number | null;
    stressMax: number | null;
    bbCharged: number | null;
    bbDrained: number | null;
    bbPeak: number | null;
    bbLow: number | null;
    respSleep: number | null;
    respWake: number | null;
    vigorousMin: number;
  }>;
}

export interface IntradayPayload {
  date: string;
  summary: {
    restingHr: number | null;
    minHr: number | null;
    maxHr: number | null;
    avgStress: number | null;
    maxStress: number | null;
    bbCharged: number | null;
    bbDrained: number | null;
    respWakingAvg: number | null;
    respSleepAvg: number | null;
    sleepScore: number | null;
    sleepHours: number | null;
    readinessScore: number | null;
  };
  heartRate: Array<{ t: string; ts: number; v: number }>;
  stress: Array<{ t: string; ts: number; v: number }>;
  bodyBattery: Array<{ t: string; ts: number; v: number }>;
  respiration: Array<{ t: string; ts: number; v: number }>;
  bodyBatteryEvents: Array<{
    eventType: string | null;
    impact: number | null;
    durationMin: number;
    shortFeedback: string | null;
  }>;
  readinessTimeline: Array<{
    timestamp: string | null;
    timeLabel: string;
    context: string | null;
    score: number | null;
    level: string | null;
    recoveryTimeH: number;
  }>;
}

export interface BodyPayload {
  height_cm: number;
  latest_weight_kg: number;
  trend_weight_kg: number;
  weigh_ins_14d: number;
  rate_kg_week: number | null;
  rate_pct_month: number | null;
  target_gain_pct_month: number;
  body_fat_pct: number | null;
  body_fat_source: string | null;
  navy_bf_pct?: number | null;
  ffm_kg: number | null;
  ffmi: number | null;
  nffmi: number | null;
  latest_tape: Record<string, number | string | null>;
  tape_history?: Array<Record<string, number | string | null>>;
  waist_arm_ratio: number | null;
  waist_chest_ratio: number | null;
  weight_series: Array<{
    date: string;
    weight_kg: number;
    trend_kg: number;
    body_fat_pct: number | null;
    source: string | null;
  }>;
  photos: Array<{
    id: number;
    calendar_date: string;
    pose: string;
    notes: string | null;
    url: string;
  }>;
  garmin_synced?: boolean;
  garmin_error?: string | null;
}

export interface FuelPayload {
  days: number;
  bodyweight_kg: number;
  protein_target_min_g: number;
  protein_target_max_g: number;
  calorie_target: number;
  protein_days_week: number;
  logged_days_window: number;
  tdee_coverage_pct: number;
  adaptive_tdee_kcal: number | null;
  adaptive_tdee_ready: boolean;
  containers: Array<{ name?: string; volume?: number; unit?: string }>;
  daily: Array<{
    date: string;
    shortLabel?: string;
    calories: number | null;
    protein_g: number | null;
    carbs_g: number;
    fat_g: number;
    hit_protein: boolean;
    burn_kcal: number | null;
    active_kcal: number | null;
    hydration_ml: number;
    hydration_goal_ml: number;
    sweat_loss_ml: number;
  }>;
  recent_logs: Array<{
    id: number;
    calendar_date: string;
    recorded_at: string;
    calories: number;
    protein_g: number;
    carbs_g: number;
    fat_g: number;
    label: string | null;
    source: string;
  }>;
}

export interface ProgressPayload {
  forge_score: ForgeScoreSummary;
  weekly_review: {
    week_start: string;
    week_end: string;
    wins: string[];
    misses: string[];
    focus_items: string[];
  };
  monthly_summary: {
    run_km_30d: number;
    strength_tonnage_30d: number;
    avg_sleep_h: number | null;
    hrv_baseline_ms: number | null;
    vo2_latest: number | null;
    trend_weight_kg: number;
  };
  roadmap: Array<{
    phase: string;
    window: string;
    targets: Array<{ label: string; current: string; pct: number }>;
  }>;
  streaks: {
    sleep_7h_streak: number;
    protein_days_this_week: number;
    lifts_this_week: number;
  };
  garmin_badges: Array<{
    name: string | null;
    date: string;
    points: number | null;
    earned_count: number | null;
  }>;
}

export interface MuscleMetaItem {
  id: string;
  label: string;
  region: string;
  pattern: string;
}

export interface SettingsPayload {
  settings: {
    muscle_set_min: number;
    muscle_set_max: number;
    lifting_freq_target: number;
    z2_target_pct: number;
    protein_g_per_kg: number;
    protein_max_g_per_kg: number;
    sleep_target_h: number;
    sleep_debt_target_h: number;
    gain_rate_pct_month: number;
    calorie_target: number;
    illness_mode: boolean;
    e1rm_formula: string;
    exclude_warmups: boolean;
    readiness_heavy_min: number;
    readiness_moderate_min: number;
    readiness_rest_max: number;
    acwr_caution: number;
    acwr_danger: number;
    interference_window_hours: number;
    target_event: string;
  };
  hr_audit: {
    sport: string;
    training_method: string | null;
    configured_rhr: number | null;
    measured_rhr_7d: number | null;
    rhr_auto_update: boolean | null;
    configured_max_hr: number | null;
    observed_max_hr_90d: number | null;
    configured_lthr: number | null;
    floors: (number | null)[];
    is_stale: boolean;
    rhr_stale: boolean;
    max_stale: boolean;
    recommendation: string;
  };
  muscle_groups: MuscleMetaItem[];
  muscle_meta: Record<string, MuscleMetaItem>;
  muscle_map: Array<{
    category: string;
    exercise_name: string;
    primary_muscle: string;
    secondary_muscles: string[];
    is_custom: boolean;
  }>;
  sync: SyncState;
  audit_log: Array<{
    id: number;
    created_at: string;
    action: string;
    target: string;
    before_json: string | null;
    after_json: string | null;
  }>;
}

export interface AccountInfo {
  id: string;
  label: string;
  email: string;
  authenticated: boolean;
  active: boolean;
}

export interface AccountsPayload {
  activeAccount: string;
  accounts: AccountInfo[];
}

export interface TipsPayload {
  date: string;
  tips: Array<{
    id: string;
    category: string;
    tone: "emerald" | "amber" | "rose" | "cyan";
    title: string;
    summary: string;
    action: string;
  }>;
  fitnessAge: {
    chronologicalAge: number | null;
    fitnessAge: number | null;
    achievableFitnessAge: number | null;
    previousFitnessAge: number | null;
  };
  racePredictions: Array<{
    distance: string;
    time: string | null;
    pace: string | null;
  }>;
  enduranceScore: {
    overall: number | null;
    classification: number | null;
  };
  hillScore: {
    overall: number | null;
    strength: number | null;
    endurance: number | null;
  };
  lactateThreshold: {
    heartRate: number | null;
    speed: number | null;
    date: string;
  };
  personalRecords: Array<{
    activityId: number | null;
    activityName: string;
    activityType: string;
    typeId: number | null;
    value: number | null;
    date: string;
  }>;
  badges: Array<{
    name: string;
    category: string;
    earnedDate: string;
  }>;
  sleepSummary?: {
    score: number | null;
    qualifier: string | null;
    durationHours: number | null;
    sleepNeedHours: number | null;
    feedback: string | null;
    overnightHrv: number | null;
  };
  healthSummary?: {
    steps: number | null;
    stepGoal: number | null;
    restingHr: number | null;
    stressAvg: number | null;
    bodyBatteryHigh: number | null;
    bodyBatteryLow: number | null;
    moderateMin: number | null;
    vigorousMin: number | null;
  };
}

export interface ActivityRoute {
  hasRoute: boolean;
  locationName?: string | null;
  totalRawPoints?: number;
  points: Array<[number, number, number | null]>;
  startPoint?: [number, number];
  endPoint?: [number, number];
  bounds?: [number | null, number | null, number | null, number | null];
}

export interface ActivityDetailPayload {
  activityId: number;
  route?: ActivityRoute;
  hrZones: Array<{
    zoneNumber: number;
    lowBoundary: number;
    secsInZone: number;
    durationFormatted: string;
    percent: number;
  }>;
  laps: Array<{
    lap: number;
    distanceKm: number;
    durationSec: number;
    durationFormatted: string;
    paceFormatted: string;
    paceSecPerKm: number | null;
    avgHr: number | null;
    maxHr: number | null;
    cadence: number | null;
    power: number | null;
    elevationGain: number;
    calories: number;
  }>;
  weather: {
    tempC: number;
    humidity: number | null;
    windSpeedKmh: number | null;
    desc: string | null;
  } | null;
  activity: {
    activity_id: number;
    name: string;
    type: string;
    start_time_local: string;
    calendar_date: string;
    duration_s: number;
    distance_m: number;
    calories: number;
    avg_hr: number | null;
    max_hr: number | null;
    te_aerobic: number;
    te_anaerobic: number;
    training_load: number;
    avg_power: number | null;
    norm_power: number | null;
    avg_cadence: number | null;
    avg_stride_cm: number | null;
    avg_gct_ms: number | null;
    avg_vo_cm: number | null;
    rpe: number | null;
    feel: number | null;
  } | null;
  exerciseSets: Array<{
    id: number;
    set_index: number;
    set_type: string;
    category: string;
    exercise_name: string | null;
    probability: number | null;
    reps: number | null;
    weight_kg: number | null;
    duration_s: number | null;
    rest_s: number | null;
    user_corrected: number;
  }>;
}
