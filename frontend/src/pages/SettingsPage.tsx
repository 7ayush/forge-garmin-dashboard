import React, { useEffect, useState } from "react";
import { CheckCheck, Download, HeartPulse, RefreshCw, ShieldAlert } from "lucide-react";
import { forgeApi } from "../api/client";
import {
  ErrorBanner,
  GlassCard,
  InfoCallout,
  LoadingState,
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";

export function SettingsPage({
  refreshTick,
  onDataChanged,
}: {
  refreshTick: number;
  onDataChanged: () => void;
}) {
  const { data, loading, error, reload } = useAsyncData(() => forgeApi.getSettings(), [refreshTick]);
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [hzMethod, setHzMethod] = useState<"LACTATE_THRESHOLD" | "HR_RESERVE" | "HR_MAX">("LACTATE_THRESHOLD");
  const [hzPreview, setHzPreview] = useState<{ before?: Record<string, unknown>; after?: Record<string, unknown> } | null>(null);
  const [mapCat, setMapCat] = useState("UNKNOWN");
  const [mapName, setMapName] = useState("");
  const [mapPrimary, setMapPrimary] = useState("chest");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (data?.settings) {
      setForm(data.settings);
    }
  }, [data]);

  if (loading && !data) return <LoadingState label="Loading Calibration & Thresholds..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const { hr_audit: hz } = data;

  const saveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await forgeApi.patchSettings(form);
      await reload();
      onDataChanged();
      setNotice("Saved calibration targets & safety thresholds.");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setBusy(false);
    }
  };

  const previewHrZones = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await forgeApi.postHrZones({
        training_method: hzMethod,
        resting_hr: hz.measured_rhr_7d || hz.configured_rhr || 56,
        max_hr: hz.observed_max_hr_90d || hz.configured_max_hr || 197,
        lactate_threshold_hr: hz.configured_lthr || 186,
        confirm: false,
      });
      setHzPreview(res);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "HR Zone preview failed");
    } finally {
      setBusy(false);
    }
  };

  const confirmHrZones = async () => {
    setBusy(true);
    setNotice(null);
    try {
      await forgeApi.postHrZones({
        training_method: hzMethod,
        resting_hr: hz.measured_rhr_7d || hz.configured_rhr || 56,
        max_hr: hz.observed_max_hr_90d || hz.configured_max_hr || 197,
        lactate_threshold_hr: hz.configured_lthr || 186,
        confirm: true,
      });
      setHzPreview(null);
      await reload();
      onDataChanged();
      setNotice("Updated Garmin Connect Heart Rate Zones.");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "HR Zone update failed");
    } finally {
      setBusy(false);
    }
  };

  const saveMuscleMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await forgeApi.postMuscleMap({
        category: mapCat,
        exercise_name: mapName || undefined,
        primary_muscle: mapPrimary,
      });
      setMapName("");
      await reload();
      onDataChanged();
      setNotice(`Mapped ${mapCat}${mapName ? `/${mapName}` : ""} -> ${mapPrimary}.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Mapping failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {notice && <InfoCallout tone="emerald">{notice}</InfoCallout>}

      {/* HR Zones Calibrator */}
      <GlassCard className={hz.is_stale ? "border-amber-400/40" : ""}>
        <SectionHeader
          eyebrow="Biometric Calibration"
          title="Garmin Heart Rate Zones Auditor"
          subtitle={hz.recommendation}
          right={
            <StatusBadge tone={hz.is_stale ? "amber" : "emerald"}>
              {hz.is_stale ? "Zones Out of Date" : "Zones Synchronized"}
            </StatusBadge>
          }
        />

        <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-slate-400">Configured RHR vs 7D</div>
            <div className="font-mono-num mt-1 text-base font-bold text-slate-100">
              {hz.configured_rhr ?? "--"} vs <span className="text-emerald-300">{hz.measured_rhr_7d ?? "--"}</span> bpm
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-slate-400">Configured Max vs 90D</div>
            <div className="font-mono-num mt-1 text-base font-bold text-slate-100">
              {hz.configured_max_hr ?? "--"} vs <span className="text-rose-300">{hz.observed_max_hr_90d ?? "--"}</span> bpm
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-slate-400">Lactate Threshold</div>
            <div className="font-mono-num mt-1 text-base font-bold text-cyan-300">{hz.configured_lthr ?? "--"} bpm</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
            <div className="text-slate-400">Method / Floors</div>
            <div className="font-mono-num mt-1 text-xs font-semibold text-slate-200">
              {hz.training_method || "--"} · [{hz.floors.join(", ")}]
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <select
            value={hzMethod}
            onChange={(e) => setHzMethod(e.target.value as "LACTATE_THRESHOLD" | "HR_RESERVE" | "HR_MAX")}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-slate-100"
          >
            <option value="LACTATE_THRESHOLD">%LTHR (Recommended for Running)</option>
            <option value="HR_RESERVE">%HRR Karvonen (Uses 7D RHR)</option>
            <option value="HR_MAX">%Max HR</option>
          </select>
          <button
            type="button"
            disabled={busy}
            onClick={() => void previewHrZones()}
            className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/40 bg-cyan-500/15 px-3.5 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25"
          >
            <HeartPulse className="h-3.5 w-3.5" /> Preview Zone Recalibration
          </button>
        </div>

        {hzPreview?.after && (
          <div className="mt-3 rounded-xl border border-amber-400/40 bg-amber-950/20 p-3 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold text-amber-200">
                Proposed Garmin HR Zones ({String(hzPreview.after.trainingMethod)}): Z1-Z5 floors [
                {[1, 2, 3, 4, 5].map((i) => String(hzPreview.after?.[`zone${i}Floor`])).join(", ")}] bpm
              </span>
              <div className="flex gap-2">
                <button type="button" onClick={() => setHzPreview(null)} className="rounded-lg border border-slate-700 px-3 py-1 text-slate-300">
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void confirmHrZones()}
                  className="inline-flex items-center gap-1 rounded-lg bg-amber-400 px-3 py-1 font-bold text-slate-950 hover:bg-amber-300"
                >
                  <CheckCheck className="h-3.5 w-3.5" /> Confirm Write to Garmin
                </button>
              </div>
            </div>
          </div>
        )}
      </GlassCard>

      {/* Athlete Thresholds + Muscle Map Override */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-7">
          <SectionHeader eyebrow="Coaching Guardrails" title="Training & Nutrition Targets" />
          <form onSubmit={saveSettings} className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
            {[
              { key: "muscle_set_min", label: "Weekly Set Min (MEV)" },
              { key: "muscle_set_max", label: "Weekly Set Max (MRV)" },
              { key: "lifting_freq_target", label: "Lifting Days / Wk" },
              { key: "z2_target_pct", label: "Z2 Target %" },
              { key: "protein_g_per_kg", label: "Protein Min (g/kg)" },
              { key: "sleep_target_h", label: "Sleep Target (h)" },
              { key: "calorie_target", label: "Calorie Target (kcal)" },
              { key: "acwr_danger", label: "ACWR Danger Cap" },
              { key: "interference_window_hours", label: "Interference Window (h)" },
            ].map((field) => (
              <label key={field.key}>
                <span className="text-slate-400">{field.label}</span>
                <input
                  type="number"
                  step="0.1"
                  value={String(form[field.key] ?? "")}
                  onChange={(e) => setForm((f) => ({ ...f, [field.key]: Number(e.target.value) }))}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
            ))}

            <label className="col-span-2 flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950/60 px-3 py-2 sm:col-span-3">
              <input
                type="checkbox"
                checked={Boolean(form.illness_mode)}
                onChange={(e) => setForm((f) => ({ ...f, illness_mode: e.target.checked }))}
                className="accent-rose-500"
              />
              <ShieldAlert className="h-4 w-4 text-rose-400" />
              <span className="font-semibold text-rose-200">
                Illness / Travel Mode (Triggers Rule R0 Full Rest &amp; suppresses overload prompts)
              </span>
            </label>

            <button
              type="submit"
              disabled={busy}
              className="col-span-2 rounded-xl bg-emerald-500 py-2 font-bold text-slate-950 hover:bg-emerald-400 sm:col-span-3"
            >
              Save Targets
            </button>
          </form>
        </GlassCard>

        <div className="space-y-5 lg:col-span-5">
          <GlassCard>
            <SectionHeader eyebrow="Exercise Taxonomy" title="Custom Muscle Mapping Override" />
            <form onSubmit={saveMuscleMapping} className="space-y-2.5 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={mapCat}
                  onChange={(e) => setMapCat(e.target.value)}
                  placeholder="Category (e.g. FLYE)"
                  className="font-mono-num rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-slate-100"
                />
                <input
                  value={mapName}
                  onChange={(e) => setMapName(e.target.value)}
                  placeholder="Exercise (optional)"
                  className="font-mono-num rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-slate-100"
                />
              </div>
              <select
                value={mapPrimary}
                onChange={(e) => setMapPrimary(e.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-slate-100"
              >
                {data.muscle_groups
                  .filter((g) => g.id !== "cardio")
                  .map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.label} ({g.pattern})
                    </option>
                  ))}
              </select>
              <button
                type="submit"
                disabled={busy}
                className="w-full rounded-xl border border-emerald-400/40 bg-emerald-500/15 py-2 font-semibold text-emerald-200 hover:bg-emerald-500/25"
              >
                Save Muscle Mapping
              </button>
            </form>
          </GlassCard>

          <GlassCard>
            <SectionHeader eyebrow="Sync & Portability" title="Backfill & Data Export" />
            <div className="flex flex-wrap gap-2 text-xs">
              <button
                type="button"
                onClick={() => void forgeApi.syncBackfill(90).then(() => setNotice("Started 90D Garmin Connect backfill in background."))}
                className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-400/35 bg-cyan-500/12 px-3 py-2 font-semibold text-cyan-200 hover:bg-cyan-500/22"
              >
                <RefreshCw className="h-3.5 w-3.5" /> Run 90D Backfill
              </button>
              <a
                href="/api/export"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 font-medium text-slate-200 hover:border-slate-500"
              >
                <Download className="h-3.5 w-3.5" /> Export Full JSON
              </a>
            </div>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
