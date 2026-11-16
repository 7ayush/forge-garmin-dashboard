import React, { useState } from "react";
import { Droplets, Trash2 } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { forgeApi } from "../api/client";
import {
  CHART_TOOLTIP_STYLE,
  ErrorBanner,
  GlassCard,
  InfoCallout,
  KpiTile,
  LoadingState,
  ProgressBar,
  SectionHeader,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";

export function FuelPage({
  refreshTick,
  onDataChanged,
}: {
  refreshTick: number;
  onDataChanged: () => void;
}) {
  const { data, setData, loading, error, reload } = useAsyncData(() => forgeApi.getFuel(14), [refreshTick]);
  const [calories, setCalories] = useState("650");
  const [proteinG, setProteinG] = useState("45");
  const [carbsG, setCarbsG] = useState("65");
  const [fatG, setFatG] = useState("18");
  const [label, setLabel] = useState("Whey + Oats + Eggs");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  if (loading && !data) return <LoadingState label="Loading Fuel & Hydration Telemetry..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const todayFuel = data.daily[data.daily.length - 1];

  const handleLogMeal = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const res = await forgeApi.postFuelLog({
        calories: Number(calories),
        protein_g: Number(proteinG),
        carbs_g: Number(carbsG || 0),
        fat_g: Number(fatG || 0),
        label,
      });
      setData(res);
      onDataChanged();
      setNotice(`Logged ${label || "meal"} (+${proteinG}g protein, +${calories} kcal).`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to log nutrition");
    } finally {
      setBusy(false);
    }
  };

  const handleHydration = async (ml: number) => {
    setBusy(true);
    setNotice(null);
    try {
      const res = await forgeApi.postHydration({ value_ml: ml, sync_to_garmin: true });
      await reload();
      onDataChanged();
      setNotice(`Added +${ml} ml -> ${res.intake_ml} / ${res.goal_ml} ml`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Hydration log failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <KpiTile
          label="Today Protein"
          value={todayFuel?.protein_g ?? 0}
          unit={`/ ${data.protein_target_min_g}g`}
          subtext={`Ceiling ${data.protein_target_max_g}g (${data.bodyweight_kg} kg BW)`}
          tone={(todayFuel?.protein_g ?? 0) >= data.protein_target_min_g ? "emerald" : "amber"}
        />
        <KpiTile
          label="Today Intake"
          value={todayFuel?.calories ?? 0}
          unit={`/ ${data.calorie_target} kcal`}
          subtext={`Burn: ${todayFuel?.burn_kcal ?? "--"} kcal`}
          tone="cyan"
        />
        <KpiTile
          label="Hydration Today"
          value={todayFuel?.hydration_ml ?? 0}
          unit={`/ ${todayFuel?.hydration_goal_ml ?? 3500} ml`}
          subtext={`Est sweat loss: ${todayFuel?.sweat_loss_ml ?? 0} ml`}
          tone="cyan"
        />
        <KpiTile
          label="Adaptive TDEE"
          value={data.adaptive_tdee_kcal ?? "--"}
          unit={data.adaptive_tdee_ready ? "kcal" : ""}
          subtext={
            data.adaptive_tdee_ready
              ? "Solved from intake + EWMA delta"
              : `Coverage ${data.tdee_coverage_pct}% (needs >=80% / 14d)`
          }
          tone={data.adaptive_tdee_ready ? "lime" : "neutral"}
        />
        <KpiTile
          label="7D Protein Hits"
          value={`${data.protein_days_week}/7`}
          subtext={`${data.logged_days_window}d logged in ${data.days}d`}
          tone="emerald"
        />
      </div>

      {notice && <InfoCallout tone="emerald">{notice}</InfoCallout>}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        {/* Intake vs Burn Chart */}
        <GlassCard className="lg:col-span-7">
          <SectionHeader
            eyebrow="14-Day Energy Balance"
            title="Calories Logged vs Garmin Total Burn"
            subtitle="Target slight surplus (+200-300 kcal above TDEE) on lifting blocks"
          />
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Bar dataKey="calories" name="Logged Intake (kcal)" fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="burn_kcal" name="Garmin Burn (kcal)" fill="#22d3ee" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        {/* Quick Meal + Hydration Controls */}
        <div className="space-y-5 lg:col-span-5">
          <GlassCard>
            <SectionHeader eyebrow="Zero-Friction Capture" title="Quick Meal / Macro Logger" />
            <form onSubmit={handleLogMeal} className="grid grid-cols-2 gap-2.5 text-xs">
              <label>
                <span className="text-slate-400">Protein (g)</span>
                <input
                  type="number"
                  required
                  value={proteinG}
                  onChange={(e) => setProteinG(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
              <label>
                <span className="text-slate-400">Calories (kcal)</span>
                <input
                  type="number"
                  required
                  value={calories}
                  onChange={(e) => setCalories(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
              <label>
                <span className="text-slate-400">Carbs (g)</span>
                <input
                  type="number"
                  value={carbsG}
                  onChange={(e) => setCarbsG(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
              <label>
                <span className="text-slate-400">Fat (g)</span>
                <input
                  type="number"
                  value={fatG}
                  onChange={(e) => setFatG(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
              <label className="col-span-2">
                <span className="text-slate-400">Meal Label</span>
                <input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
              <button
                type="submit"
                disabled={busy}
                className="col-span-2 mt-1 rounded-xl bg-emerald-500 py-2 font-bold text-slate-950 hover:bg-emerald-400"
              >
                Log Meal
              </button>
            </form>
          </GlassCard>

          <GlassCard>
            <SectionHeader
              eyebrow="Garmin Sync"
              title="Hydration vs Sweat Loss"
              right={
                <span className="font-mono-num text-xs text-cyan-300">
                  {todayFuel?.hydration_ml ?? 0} / {todayFuel?.hydration_goal_ml ?? 3500} ml
                </span>
              }
            />
            <ProgressBar
              value={todayFuel?.hydration_ml ?? 0}
              max={todayFuel?.hydration_goal_ml ?? 3500}
              tone="cyan"
            />
            <div className="mt-3 grid grid-cols-3 gap-2">
              {data.containers.slice(0, 3).map((c, idx) => {
                const vol = Math.round(Number(c.volume || (idx + 1) * 250));
                return (
                  <button
                    key={idx}
                    type="button"
                    disabled={busy}
                    onClick={() => void handleHydration(vol)}
                    className="font-mono-num inline-flex items-center justify-center gap-1 rounded-xl border border-cyan-500/35 bg-cyan-500/12 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/25"
                  >
                    <Droplets className="h-3.5 w-3.5" />+{vol} ml
                  </button>
                );
              })}
            </div>
          </GlassCard>
        </div>
      </div>

      {/* Recent Logs */}
      <GlassCard>
        <SectionHeader eyebrow="Food Diary" title="Recent Nutrition Entries" />
        {data.recent_logs.length === 0 ? (
          <div className="py-4 text-xs text-slate-400">No meals logged yet. Use Quick Meal above to unlock Fuel scoring.</div>
        ) : (
          <div className="divide-y divide-slate-800/60 text-xs">
            {data.recent_logs.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between py-2">
                <div>
                  <span className="font-semibold text-slate-200">{entry.label || "Meal"}</span>
                  <span className="font-mono-num ml-2 text-slate-400">{entry.calendar_date}</span>
                </div>
                <div className="font-mono-num flex items-center gap-4">
                  <span className="text-emerald-300">{entry.protein_g}g P</span>
                  <span className="text-slate-300">{entry.calories} kcal</span>
                  <button
                    type="button"
                    onClick={() => void forgeApi.deleteFuelLog(entry.id).then(setData)}
                    className="text-slate-500 hover:text-rose-400"
                    aria-label="Delete nutrition log"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
