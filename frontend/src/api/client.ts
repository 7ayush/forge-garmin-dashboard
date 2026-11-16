import type {
  ActivityDetailPayload,
  BodyPayload,
  AccountsPayload,
  EnginePayload,
  TipsPayload,
  FuelPayload,
  IntradayPayload,
  ProgressPayload,
  RecoveryPayload,
  SettingsPayload,
  StrengthPayload,
  TodayPayload,
} from "../types/forge";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  const text = await res.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  if (!res.ok) {
    const errMsg =
      parsed && typeof parsed === "object" && "error" in parsed
        ? String((parsed as { error: unknown }).error)
        : `HTTP ${res.status}`;
    throw new Error(errMsg);
  }
  return parsed as T;
}

export const forgeApi = {
  getToday: () => requestJson<TodayPayload>("/api/today"),
  getStrength: (week?: string) =>
    requestJson<StrengthPayload>(week ? `/api/strength?week=${encodeURIComponent(week)}` : "/api/strength"),
  patchStrengthSetsLocal: (
    activityId: number,
    edits: Array<{
      id?: number;
      set_index?: number;
      category?: string;
      exercise_name?: string;
      reps?: number;
      weight_kg?: number;
    }>
  ) =>
    requestJson<{ ok: boolean; updated: number; strength: StrengthPayload }>(
      `/api/strength/sets/${activityId}/local`,
      { method: "PATCH", body: JSON.stringify({ edits }) }
    ),
  pushStrengthSetsGarmin: (activityId: number, confirm: boolean) =>
    requestJson<{
      preview?: boolean;
      ok?: boolean;
      activity_id: number;
      changes_count?: number;
      changes_pushed?: number;
      changes?: Array<{
        set_index: number;
        before: Record<string, unknown>;
        after: Record<string, unknown>;
      }>;
      strength?: StrengthPayload;
    }>(`/api/strength/sets/${activityId}/push`, {
      method: "POST",
      body: JSON.stringify({ confirm }),
    }),

  getAccounts: () => requestJson<AccountsPayload>("/api/accounts"),
  selectAccount: (accountId: string) =>
    requestJson<AccountsPayload>("/api/accounts/select", {
      method: "POST",
      body: JSON.stringify({ accountId }),
    }),
  loginAccount: (accountId: string, password: string) =>
    requestJson<{ ok: boolean; accounts: AccountsPayload["accounts"] }>("/api/accounts/login", {
      method: "POST",
      body: JSON.stringify({ accountId, password }),
    }),
  getEngine: (days = 30) => requestJson<EnginePayload>(`/api/engine?days=${days}`),
  getTips: (refresh = false) => requestJson<TipsPayload>(`/api/tips${refresh ? "?refresh=1" : ""}`),
  getRecovery: (days = 14) => requestJson<RecoveryPayload>(`/api/recovery?days=${days}`),
  getIntraday: (dateStr: string, refresh = false) =>
    requestJson<IntradayPayload>(`/api/intraday?date=${encodeURIComponent(dateStr)}&refresh=${refresh ? "1" : "0"}`),

  getBody: () => requestJson<BodyPayload>("/api/body"),
  postWeighIn: (payload: {
    weight_kg: number;
    body_fat_pct?: number | null;
    date?: string;
    notes?: string;
    sync_to_garmin?: boolean;
  }) => requestJson<BodyPayload>("/api/body/weigh-in", { method: "POST", body: JSON.stringify(payload) }),
  postTape: (payload: Record<string, string | number | undefined>) =>
    requestJson<BodyPayload>("/api/body/tape", { method: "POST", body: JSON.stringify(payload) }),
  uploadPhoto: (form: FormData) =>
    requestJson<BodyPayload>("/api/body/photo", { method: "POST", body: form }),
  deletePhoto: (photoId: number) =>
    requestJson<BodyPayload>(`/api/body/photo/${photoId}`, { method: "DELETE" }),

  getFuel: (days = 14) => requestJson<FuelPayload>(`/api/fuel?days=${days}`),
  postFuelLog: (payload: {
    calories: number;
    protein_g: number;
    carbs_g?: number;
    fat_g?: number;
    label?: string;
    date?: string;
  }) => requestJson<FuelPayload>("/api/fuel/log", { method: "POST", body: JSON.stringify(payload) }),
  deleteFuelLog: (entryId: number) =>
    requestJson<FuelPayload>(`/api/fuel/log/${entryId}`, { method: "DELETE" }),
  postHydration: (payload: { value_ml: number; date?: string; sync_to_garmin?: boolean }) =>
    requestJson<{
      ok: boolean;
      intake_ml: number;
      goal_ml: number;
      garmin_synced: boolean;
      garmin_error: string | null;
    }>("/api/hydration", { method: "POST", body: JSON.stringify(payload) }),

  getProgress: () => requestJson<ProgressPayload>("/api/progress"),
  getActivityDetail: (activityId: number, refresh = false) =>
    requestJson<ActivityDetailPayload>(`/api/activity/${activityId}?refresh=${refresh ? "1" : "0"}`),
  patchActivityEffort: (
    activityId: number,
    payload: { rpe?: number; feel?: number; sync_to_garmin?: boolean }
  ) =>
    requestJson<{ ok: boolean; garmin_synced: boolean; garmin_error: string | null }>(
      `/api/activity/${activityId}/effort`,
      { method: "PATCH", body: JSON.stringify(payload) }
    ),

  getSettings: () => requestJson<SettingsPayload>("/api/settings"),
  patchSettings: (updates: Record<string, unknown>) =>
    requestJson<{ ok: boolean; settings: SettingsPayload["settings"] }>("/api/settings", {
      method: "PATCH",
      body: JSON.stringify(updates),
    }),
  postHrZones: (payload: {
    training_method: "LACTATE_THRESHOLD" | "HR_MAX" | "HR_RESERVE";
    resting_hr: number;
    max_hr: number;
    lactate_threshold_hr: number;
    floors?: number[];
    confirm: boolean;
  }) =>
    requestJson<{
      preview?: boolean;
      ok?: boolean;
      before?: Record<string, unknown>;
      after?: Record<string, unknown>;
      hr_audit?: SettingsPayload["hr_audit"];
    }>("/api/settings/hr-zones", { method: "POST", body: JSON.stringify(payload) }),
  postMuscleMap: (payload: {
    category: string;
    exercise_name?: string;
    primary_muscle: string;
    secondary_muscles?: string[];
  }) =>
    requestJson<{ ok: boolean }>("/api/settings/muscle-map", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  syncNow: (days = 7) =>
    requestJson<{ ok: boolean; sync: SettingsPayload["sync"] }>(`/api/sync/now?days=${days}&wait=1`, {
      method: "POST",
    }),
  syncBackfill: (days = 90) =>
    requestJson<{ started: boolean; sync: SettingsPayload["sync"] }>(`/api/sync/backfill?days=${days}&wait=0`, {
      method: "POST",
    }),
  getSyncStatus: () =>
    requestJson<{ sync: SettingsPayload["sync"]; counts: { activities: number; daily_wellness: number } }>(
      "/api/sync/status"
    ),
};
