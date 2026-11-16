import React, { useState } from "react";
import { Droplets, Flame, Scale, X } from "lucide-react";
import { forgeApi } from "../../api/client";

type QuickTab = "weight" | "nutrition" | "hydration";

export function QuickLogModal({
  open,
  defaultWeight,
  onClose,
  onSaved,
}: {
  open: boolean;
  defaultWeight?: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [tab, setTab] = useState<QuickTab>("weight");
  const [weightKg, setWeightKg] = useState(defaultWeight ? String(defaultWeight) : "73.2");
  const [bodyFat, setBodyFat] = useState("");
  const [syncGarmin, setSyncGarmin] = useState(true);
  const [proteinG, setProteinG] = useState("45");
  const [calories, setCalories] = useState("550");
  const [label, setLabel] = useState("Chicken & Rice");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const handleSaveWeight = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      const res = await forgeApi.postWeighIn({
        weight_kg: Number(weightKg),
        body_fat_pct: bodyFat ? Number(bodyFat) : null,
        sync_to_garmin: syncGarmin,
      });
      setFeedback(
        res.garmin_synced
          ? `Saved ${res.latest_weight_kg} kg & synced to Garmin Connect.`
          : `Saved ${res.latest_weight_kg} kg locally.`
      );
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save weight");
    } finally {
      setBusy(false);
    }
  };

  const handleSaveNutrition = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      await forgeApi.postFuelLog({
        protein_g: Number(proteinG),
        calories: Number(calories),
        label: label || "Quick Meal",
      });
      setFeedback(`Logged +${proteinG}g protein (${calories} kcal).`);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save nutrition");
    } finally {
      setBusy(false);
    }
  };

  const handleWater = async (ml: number) => {
    setBusy(true);
    setError(null);
    setFeedback(null);
    try {
      const res = await forgeApi.postHydration({ value_ml: ml, sync_to_garmin: true });
      setFeedback(
        `Added +${ml} ml -> ${res.intake_ml} / ${res.goal_ml} ml${res.garmin_synced ? " (Garmin synced)" : ""}`
      );
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to log hydration");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="telemetry-card w-full max-w-md rounded-2xl p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="font-mono-num text-[10px] tracking-widest text-emerald-400 uppercase">
              3-Tap Capture
            </div>
            <h3 className="font-display text-lg font-bold text-slate-100">Quick Log</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            aria-label="Close Quick Log"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mb-4 grid grid-cols-3 gap-1.5 rounded-xl bg-slate-950/75 p-1">
          {[
            { id: "weight" as QuickTab, label: "Weight", icon: Scale },
            { id: "nutrition" as QuickTab, label: "Protein", icon: Flame },
            { id: "hydration" as QuickTab, label: "Water", icon: Droplets },
          ].map((item) => {
            const Icon = item.icon;
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  setTab(item.id);
                  setError(null);
                  setFeedback(null);
                }}
                className={`flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-semibold transition ${
                  active ? "bg-emerald-500/20 text-emerald-200 border border-emerald-500/35" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {item.label}
              </button>
            );
          })}
        </div>

        {tab === "weight" && (
          <form onSubmit={handleSaveWeight} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs">
                <span className="text-slate-400">Weight (kg)</span>
                <input
                  type="number"
                  step="0.1"
                  required
                  value={weightKg}
                  onChange={(e) => setWeightKg(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-400"
                />
              </label>
              <label className="block text-xs">
                <span className="text-slate-400">Body Fat % (opt)</span>
                <input
                  type="number"
                  step="0.1"
                  placeholder="e.g. 15.5"
                  value={bodyFat}
                  onChange={(e) => setBodyFat(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-400"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={syncGarmin}
                onChange={(e) => setSyncGarmin(e.target.checked)}
                className="accent-emerald-400"
              />
              Write weigh-in directly to Garmin Connect
            </label>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-emerald-500 px-4 py-2.5 text-xs font-bold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
            >
              {busy ? "Saving..." : "Log Morning Weigh-In"}
            </button>
          </form>
        )}

        {tab === "nutrition" && (
          <form onSubmit={handleSaveNutrition} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="block text-xs">
                <span className="text-slate-400">Protein (g)</span>
                <input
                  type="number"
                  step="1"
                  required
                  value={proteinG}
                  onChange={(e) => setProteinG(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-400"
                />
              </label>
              <label className="block text-xs">
                <span className="text-slate-400">Calories (kcal)</span>
                <input
                  type="number"
                  step="10"
                  required
                  value={calories}
                  onChange={(e) => setCalories(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-400"
                />
              </label>
            </div>
            <label className="block text-xs">
              <span className="text-slate-400">Meal Label</span>
              <input
                type="text"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                className="mt-1 w-full rounded-xl border border-slate-700/80 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-400"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-emerald-500 px-4 py-2.5 text-xs font-bold text-slate-950 transition hover:bg-emerald-400 disabled:opacity-50"
            >
              {busy ? "Logging..." : "Log Meal / Shake"}
            </button>
          </form>
        )}

        {tab === "hydration" && (
          <div className="space-y-3">
            <p className="text-xs text-slate-400">One-tap sync directly to Garmin Connect Hydration.</p>
            <div className="grid grid-cols-3 gap-2">
              {[250, 500, 750].map((ml) => (
                <button
                  key={ml}
                  type="button"
                  disabled={busy}
                  onClick={() => handleWater(ml)}
                  className="font-mono-num rounded-xl border border-cyan-400/35 bg-cyan-500/12 py-3 text-sm font-bold text-cyan-200 transition hover:bg-cyan-500/25 disabled:opacity-50"
                >
                  +{ml} ml
                </button>
              ))}
            </div>
          </div>
        )}

        {feedback && (
          <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
            {feedback}
          </div>
        )}
        {error && (
          <div className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
