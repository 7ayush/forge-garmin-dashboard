import React, { useMemo, useState } from "react";
import { Check, CheckCheck, Sparkles, UploadCloud } from "lucide-react";
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
import { AnatomicalMuscleMap } from "../components/strength/AnatomicalMuscleMap";
import {
  CHART_TOOLTIP_STYLE,
  ErrorBanner,
  GlassCard,
  InfoCallout,
  KpiTile,
  LoadingState,
  ProgressBar,
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";
import type { TriageItem } from "../types/forge";

export function StrengthPage({
  refreshTick,
  onSelectActivity,
  onDataChanged,
}: {
  refreshTick: number;
  onSelectActivity: (activityId: number) => void;
  onDataChanged: () => void;
}) {
  const [selectedWeek, setSelectedWeek] = useState<string>("");
  const { data, setData, loading, error, reload } = useAsyncData(
    () => forgeApi.getStrength(selectedWeek || undefined),
    [refreshTick, selectedWeek]
  );

  const [selectedMuscle, setSelectedMuscle] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editCat, setEditCat] = useState("");
  const [editName, setEditName] = useState("");
  const [editReps, setEditReps] = useState("10");
  const [editWeight, setEditWeight] = useState("0");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [pushPreview, setPushPreview] = useState<{
    activityId: number;
    changesCount: number;
    changes: Array<{ set_index: number; before: Record<string, unknown>; after: Record<string, unknown> }>;
  } | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  const modifiedActivities = useMemo(() => {
    if (!data) return [];
    const seen = new Map<number, string>();
    for (const s of data.session_summaries) {
      seen.set(s.activity_id, `${s.calendar_date} · ${s.name}`);
    }
    return Array.from(seen.entries());
  }, [data]);

  if (loading && !data) return <LoadingState label="Analyzing Strength & Hypertrophy Volume..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const startEdit = (item: TriageItem) => {
    setEditingId(item.id);
    setEditCat(item.category);
    setEditName(item.exercise_name || "");
    setEditReps(String(item.reps ?? 10));
    setEditWeight(String(item.weight_kg ?? 0));
  };

  const applyPreset = async (
    item: TriageItem,
    preset: { category: string; exercise_name: string }
  ) => {
    setBusyId(item.id);
    setBanner(null);
    try {
      const res = await forgeApi.patchStrengthSetsLocal(item.activity_id, [
        {
          id: item.id,
          category: preset.category,
          exercise_name: preset.exercise_name,
        },
      ]);
      setData(res.strength);
      onDataChanged();
      setBanner(`Updated set #${item.set_index + 1} locally -> ${preset.exercise_name}.`);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Failed update");
    } finally {
      setBusyId(null);
    }
  };

  const saveInlineEdit = async (item: TriageItem) => {
    setBusyId(item.id);
    setBanner(null);
    try {
      const res = await forgeApi.patchStrengthSetsLocal(item.activity_id, [
        {
          id: item.id,
          category: editCat,
          exercise_name: editName,
          reps: Number(editReps),
          weight_kg: Number(editWeight),
        },
      ]);
      setEditingId(null);
      setData(res.strength);
      onDataChanged();
      setBanner(`Saved local fix on ${item.activity_name} set #${item.set_index + 1}.`);
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusyId(null);
    }
  };

  const handlePreviewPush = async (activityId: number) => {
    setBanner(null);
    try {
      const res = await forgeApi.pushStrengthSetsGarmin(activityId, false);
      if (!res.changes_count) {
        setBanner("No pending local edits on this session to push to Garmin.");
        return;
      }
      setPushPreview({
        activityId,
        changesCount: res.changes_count,
        changes: res.changes || [],
      });
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Preview failed");
    }
  };

  const confirmPushToGarmin = async () => {
    if (!pushPreview) return;
    try {
      const res = await forgeApi.pushStrengthSetsGarmin(pushPreview.activityId, true);
      if (res.strength) setData(res.strength);
      setBanner(`Pushed ${res.changes_pushed ?? 0} set correction(s) to Garmin Connect.`);
      setPushPreview(null);
      onDataChanged();
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Garmin push failed");
    }
  };

  const coreMuscles = data.muscle_volume.filter((m) => m.muscle !== "cardio");
  const selectedMuscleInfo = selectedMuscle
    ? coreMuscles.find((m) => m.muscle === selectedMuscle)
    : null;

  return (
    <div className="space-y-6">
      {/* Header Controls & KPI Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="emerald">e1RM: {data.e1rm_formula.toUpperCase()} (1-10 reps)</StatusBadge>
          <StatusBadge tone={data.exclude_warmups ? "cyan" : "neutral"}>
            {data.exclude_warmups ? "Warmups Excluded (<50% top)" : "Warmups Included"}
          </StatusBadge>
        </div>

        <label className="flex items-center gap-2 text-xs text-slate-300">
          <span>Target Week:</span>
          <select
            value={selectedWeek || data.week_start}
            onChange={(e) => setSelectedWeek(e.target.value)}
            className="font-mono-num rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100 outline-none focus:border-emerald-400"
          >
            {data.available_weeks.map((wk) => (
              <option key={wk} value={wk}>
                Week of {wk}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile label="Sessions" value={data.summary.total_sessions} subtext={`${data.summary.sessions_this_week} this week`} tone="emerald" />
        <KpiTile label="Active Sets" value={data.summary.total_active_sets} subtext={`${data.summary.verified_pct}% verified`} tone="cyan" />
        <KpiTile
          label="Triage Needed"
          value={data.summary.total_triage_count}
          subtext={`${data.summary.unclassified_count} UNKNOWN watch sets`}
          tone={data.summary.total_triage_count > 0 ? "amber" : "emerald"}
        />
        <KpiTile
          label="All-Time Tonnage"
          value={`${Math.round(data.summary.total_tonnage_kg / 1000 * 10) / 10}t`}
          unit={`(${data.summary.total_tonnage_kg.toLocaleString()} kg)`}
          tone="lime"
        />
        <KpiTile
          label="Push : Pull (All)"
          value={data.balance_all_time.push_pull_ratio ? `${data.balance_all_time.push_pull_ratio}:1` : "--"}
          subtext={`${data.balance_all_time.push_sets} push vs ${data.balance_all_time.pull_sets} pull`}
          tone="cyan"
        />
        <KpiTile
          label="Avg Rest"
          value={data.summary.avg_rest_sec ?? "--"}
          unit="sec"
          subtext={`BW ref: ${data.bodyweight_kg} kg`}
        />
      </div>

      {banner && <InfoCallout tone="emerald">{banner}</InfoCallout>}

      {/* Anatomical Muscle Map + Weekly Fractional Sets Bars */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-5">
          <SectionHeader
            eyebrow="Body Map"
            title="Weekly Muscle Activation"
            subtitle={`Week ${data.week_start} -> ${data.week_end}`}
          />
          <AnatomicalMuscleMap
            muscles={coreMuscles}
            selectedMuscle={selectedMuscle}
            onSelectMuscle={setSelectedMuscle}
          />
          {selectedMuscleInfo && (
            <div className="mt-3 rounded-xl border border-emerald-500/30 bg-slate-950/75 p-3 text-xs">
              <div className="flex items-center justify-between font-semibold text-slate-100">
                <span>{selectedMuscleInfo.label}</span>
                <span className="font-mono-num text-emerald-300">
                  {selectedMuscleInfo.fractional_sets} frac sets ({selectedMuscleInfo.direct_sets} direct)
                </span>
              </div>
              <div className="mt-1 text-slate-400">
                All-time direct sets: {selectedMuscleInfo.all_time_direct} · Last trained:{" "}
                {selectedMuscleInfo.last_trained || "Not yet"}
              </div>
            </div>
          )}
        </GlassCard>

        <GlassCard className="lg:col-span-7">
          <SectionHeader
            eyebrow="MEV -> MRV Targets (10 - 20 sets)"
            title="Fractional Sets & Gap Planner"
            subtitle="Direct sets (1.0x) + Secondary synergists (0.5x)"
          />
          <div className="space-y-2.5">
            {coreMuscles.map((m) => {
              const isSelected = selectedMuscle === m.muscle;
              const tone =
                m.status === "optimal"
                  ? "emerald"
                  : m.status === "above_target"
                  ? "amber"
                  : m.fractional_sets > 0
                  ? "cyan"
                  : "neutral";
              return (
                <div
                  key={m.muscle}
                  onClick={() => setSelectedMuscle(m.muscle)}
                  className={`cursor-pointer rounded-xl px-2.5 py-1.5 transition ${
                    isSelected ? "bg-emerald-500/10 ring-1 ring-emerald-500/40" : "hover:bg-slate-900/50"
                  }`}
                >
                  <div className="mb-1 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-200">{m.label}</span>
                    <div className="font-mono-num flex items-center gap-3 text-[11px]">
                      <span className="text-slate-400">all-time: {m.all_time_direct}</span>
                      <span className="font-bold text-slate-100">
                        {m.fractional_sets} / {m.target_min}
                      </span>
                    </div>
                  </div>
                  <ProgressBar value={m.fractional_sets} max={m.target_max} tone={tone} heightClass="h-2" />
                </div>
              );
            })}
          </div>
        </GlassCard>
      </div>

      {/* Data Quality Triage Queue */}
      <GlassCard>
        <SectionHeader
          eyebrow="Watch Cleanup & Verification"
          title={`Set Triage Queue (${data.triage_queue.length} flagged sets)`}
          subtitle="Fixes save locally immediately. Push edited sessions back to Garmin only after explicit diff confirmation."
          right={
            modifiedActivities.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                {modifiedActivities.slice(0, 3).map(([aid, label]) => (
                  <button
                    key={aid}
                    type="button"
                    onClick={() => void handlePreviewPush(aid)}
                    className="inline-flex items-center gap-1.5 rounded-xl border border-amber-400/35 bg-amber-500/12 px-3 py-1.5 text-[11px] font-semibold text-amber-200 hover:bg-amber-500/22"
                  >
                    <UploadCloud className="h-3.5 w-3.5" />
                    Preview Push ({label.slice(13, 28)})
                  </button>
                ))}
              </div>
            )
          }
        />

        {pushPreview && (
          <div className="mb-4 rounded-xl border border-amber-400/50 bg-amber-950/25 p-4 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="font-semibold text-amber-200">
                Confirm Garmin Connect Write-Back ({pushPreview.changesCount} modified sets on Activity #
                {pushPreview.activityId})
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setPushPreview(null)}
                  className="rounded-lg border border-slate-700 px-3 py-1 text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void confirmPushToGarmin()}
                  className="inline-flex items-center gap-1 rounded-lg bg-amber-400 px-3 py-1 font-bold text-slate-950 hover:bg-amber-300"
                >
                  <CheckCheck className="h-3.5 w-3.5" /> Confirm PUT to Garmin
                </button>
              </div>
            </div>
            <div className="font-mono-num mt-2 max-h-40 space-y-1 overflow-y-auto text-[11px] text-slate-300">
              {pushPreview.changes.map((c) => (
                <div key={c.set_index}>
                  Set #{c.set_index + 1}: {String(c.before.category)}/{String(c.before.exercise_name ?? "--")} (
                  {String(c.before.reps)}x{String(c.before.weight_kg)}kg) -&gt;{" "}
                  <span className="text-emerald-300">
                    {String(c.after.category)}/{String(c.after.exercise_name ?? "--")} ({String(c.after.reps)}x
                    {String(c.after.weight_kg)}kg)
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {data.triage_queue.length === 0 ? (
          <div className="flex items-center gap-2 py-4 text-xs text-emerald-300">
            <Check className="h-4 w-4" /> All recorded strength sets are verified!
          </div>
        ) : (
          <div className="max-h-[420px] space-y-2.5 overflow-y-auto pr-1">
            {data.triage_queue.slice(0, 35).map((item) => {
              const isEditing = editingId === item.id;
              return (
                <div
                  key={item.id}
                  className="rounded-xl border border-slate-800/80 bg-slate-950/65 p-3 text-xs"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-mono-num text-[11px] text-slate-400">
                        {item.calendar_date} · Set #{item.set_index + 1} · {item.activity_name}
                      </span>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2">
                        <span className="font-mono-num font-bold text-slate-100">
                          {item.category}
                          {item.exercise_name ? ` / ${item.exercise_name}` : ""}
                        </span>
                        <span className="font-mono-num text-emerald-300">
                          {item.reps ?? "--"} reps × {item.weight_kg ?? 0} kg
                        </span>
                        {item.issues.map((iss) => (
                          <StatusBadge key={iss} tone={iss.includes("unclassified") ? "crimson" : "amber"}>
                            {iss.replace(/_/g, " ")}
                          </StatusBadge>
                        ))}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      {!isEditing && (
                        <>
                          {data.triage_presets.slice(0, 3).map((preset) => (
                            <button
                              key={preset.label}
                              type="button"
                              disabled={busyId === item.id}
                              onClick={() => void applyPreset(item, preset)}
                              className="rounded-lg border border-slate-700/80 bg-slate-900 px-2 py-1 text-[10px] font-medium text-slate-300 hover:border-emerald-400/50 hover:text-emerald-200"
                            >
                              <Sparkles className="mr-1 inline h-2.5 w-2.5 text-emerald-400" />
                              {preset.label}
                            </button>
                          ))}
                          <button
                            type="button"
                            onClick={() => startEdit(item)}
                            className="rounded-lg border border-cyan-500/35 bg-cyan-500/12 px-2.5 py-1 text-[11px] font-semibold text-cyan-200 hover:bg-cyan-500/22"
                          >
                            Edit
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {isEditing && (
                    <div className="mt-3 grid grid-cols-2 gap-2 border-t border-slate-800 pt-3 sm:grid-cols-5">
                      <input
                        value={editCat}
                        onChange={(e) => setEditCat(e.target.value)}
                        placeholder="Category (e.g. CURL)"
                        className="font-mono-num rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-100"
                      />
                      <input
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        placeholder="Exercise name"
                        className="font-mono-num rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-slate-100 sm:col-span-2"
                      />
                      <div className="flex gap-1.5">
                        <input
                          type="number"
                          value={editReps}
                          onChange={(e) => setEditReps(e.target.value)}
                          placeholder="Reps"
                          className="font-mono-num w-1/2 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                        />
                        <input
                          type="number"
                          step="0.5"
                          value={editWeight}
                          onChange={(e) => setEditWeight(e.target.value)}
                          placeholder="kg"
                          className="font-mono-num w-1/2 rounded-lg border border-slate-700 bg-slate-900 px-2 py-1.5 text-xs text-slate-100"
                        />
                      </div>
                      <div className="flex gap-1.5">
                        <button
                          type="button"
                          onClick={() => void saveInlineEdit(item)}
                          disabled={busyId === item.id}
                          className="flex-1 rounded-lg bg-emerald-500 px-2 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="rounded-lg border border-slate-700 px-2 py-1.5 text-xs text-slate-300"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </GlassCard>

      {/* Progressive Overload + Weekly Tonnage Chart + Relative Strength */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-7">
          <SectionHeader
            eyebrow="Progressive Overload"
            title="Exercise e1RM & Overload Status"
            subtitle="Sets >10 reps use volume-set tracking (no inflated e1RM extrapolation)"
          />
          <div className="max-h-80 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 text-[10px] text-slate-400 uppercase">
                <tr>
                  <th className="py-2 pr-3">Exercise</th>
                  <th className="py-2 pr-3">Sets</th>
                  <th className="py-2 pr-3">Best e1RM</th>
                  <th className="py-2 pr-3">Latest</th>
                  <th className="py-2">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {data.exercises_progress.slice(0, 15).map((ex) => (
                  <tr key={ex.exercise}>
                    <td className="py-2 pr-3 font-medium text-slate-200">
                      <div>{ex.exercise.replace(/_/g, " ")}</div>
                      {ex.note && <div className="text-[10px] text-slate-400">{ex.note}</div>}
                    </td>
                    <td className="font-mono-num py-2 pr-3">{ex.total_sets}</td>
                    <td className="font-mono-num py-2 pr-3 font-bold text-emerald-300">
                      {ex.best_e1rm ? `${ex.best_e1rm} kg` : "--"}
                    </td>
                    <td className="font-mono-num py-2 pr-3 text-slate-300">
                      {ex.latest_weight}kg × {ex.latest_reps}
                    </td>
                    <td className="py-2">
                      <StatusBadge
                        tone={
                          ex.overload_status === "pr"
                            ? "lime"
                            : ex.overload_status === "stalled"
                            ? "amber"
                            : "neutral"
                        }
                      >
                        {ex.overload_status.replace(/_/g, " ")}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>

        <div className="space-y-5 lg:col-span-5">
          <GlassCard>
            <SectionHeader eyebrow="Tonnage Trend" title="Weekly Working Tonnage (kg)" />
            <div className="h-44 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.weekly_tonnage}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                  <XAxis dataKey="week_start" stroke="#64748b" fontSize={10} />
                  <YAxis stroke="#64748b" fontSize={10} />
                  <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                  <Bar dataKey="tonnage_kg" name="Tonnage (kg)" fill="#10b981" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </GlassCard>

          <GlassCard>
            <SectionHeader
              eyebrow="Relative Strength Standards"
              title={`Bodyweight Multipliers (${data.bodyweight_kg} kg)`}
            />
            <div className="space-y-2 text-xs">
              {data.relative_strength.map((row) => {
                const tier =
                  row.e1rm == null
                    ? "Unranked"
                    : row.e1rm >= row.adv
                    ? "Advanced"
                    : row.e1rm >= row.inter
                    ? "Intermediate"
                    : row.e1rm >= row.novice
                    ? "Novice"
                    : "Foundation";
                return (
                  <div
                    key={row.lift}
                    className="flex items-center justify-between rounded-xl border border-slate-800/70 bg-slate-950/60 px-3 py-2"
                  >
                    <div>
                      <div className="font-medium text-slate-200">{row.lift}</div>
                      <div className="font-mono-num text-[10px] text-slate-500">
                        Nov {row.novice}kg · Int {row.inter}kg · Adv {row.adv}kg
                      </div>
                    </div>
                    <div className="font-mono-num flex items-center gap-3">
                      <span className="text-slate-300">
                        {row.e1rm ? `${row.e1rm} kg (${row.bw_ratio}x)` : "Log <=10 reps"}
                      </span>
                      <StatusBadge tone={tier === "Unranked" ? "neutral" : "cyan"}>{tier}</StatusBadge>
                    </div>
                  </div>
                );
              })}
            </div>
          </GlassCard>
        </div>
      </div>

      {/* Session List */}
      <GlassCard>
        <SectionHeader eyebrow="Workouts" title="Strength Sessions" subtitle="Click any session to inspect sets & edit RPE" />
        <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {data.session_summaries.map((s) => (
            <button
              key={s.activity_id}
              type="button"
              onClick={() => onSelectActivity(s.activity_id)}
              className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3 text-left transition hover:border-emerald-400/45"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-100">{s.name}</span>
                {s.issue_count > 0 && <StatusBadge tone="amber">{s.issue_count} triage</StatusBadge>}
              </div>
              <div className="font-mono-num mt-1 text-[11px] text-slate-400">
                {s.calendar_date} · {s.duration_min} min · {s.working_sets} sets
              </div>
              <div className="font-mono-num mt-1 text-xs font-semibold text-emerald-300">
                {s.tonnage_kg.toLocaleString()} kg tonnage
              </div>
            </button>
          ))}
        </div>
      </GlassCard>
    </div>
  );
}
