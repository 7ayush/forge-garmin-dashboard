import React, { useEffect, useState } from "react";
import { CloudSun, Gauge, RefreshCw, X } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { forgeApi } from "../../api/client";
import type { ActivityDetailPayload } from "../../types/forge";
import { RouteMap } from "../maps/RouteMap";
import { CHART_TOOLTIP_STYLE, LoadingState, StatusBadge } from "../ui/Primitives";

const ZONE_COLORS = ["#64748b", "#10b981", "#22d3ee", "#f59e0b", "#ef4444"];
const FEEL_OPTIONS = [
  { val: 0, label: "Very Poor" },
  { val: 25, label: "Tired" },
  { val: 50, label: "Normal" },
  { val: 75, label: "Good" },
  { val: 100, label: "Strong" },
];

export function ActivityDetailModal({
  activityId,
  onClose,
  onEffortUpdated,
}: {
  activityId: number | null;
  onClose: () => void;
  onEffortUpdated?: () => void;
}) {
  const [detail, setDetail] = useState<ActivityDetailPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rpe, setRpe] = useState(7);
  const [feel, setFeel] = useState(75);
  const [savingEffort, setSavingEffort] = useState(false);
  const [effortNotice, setEffortNotice] = useState<string | null>(null);

  const load = async (id: number, refresh = false) => {
    setLoading(true);
    setError(null);
    setEffortNotice(null);
    try {
      const res = await forgeApi.getActivityDetail(id, refresh);
      setDetail(res);
      if (res.activity?.rpe != null) setRpe(Math.round(res.activity.rpe / 10));
      if (res.activity?.feel != null) setFeel(res.activity.feel);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load activity");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activityId !== null) {
      void load(activityId);
    } else {
      setDetail(null);
    }
  }, [activityId]);

  if (activityId === null) return null;

  const act = detail?.activity;

  const saveEffort = async () => {
    if (!activityId) return;
    setSavingEffort(true);
    setEffortNotice(null);
    try {
      const res = await forgeApi.patchActivityEffort(activityId, { rpe, feel, sync_to_garmin: true });
      setEffortNotice(res.garmin_synced ? "Updated RPE & Feel in Garmin Connect." : "Saved locally.");
      onEffortUpdated?.();
    } catch (err) {
      setEffortNotice(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSavingEffort(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 backdrop-blur-sm sm:p-5">
      <div className="telemetry-card flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-slate-800/80 px-5 py-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone="emerald">{act?.type || "activity"}</StatusBadge>
              <span className="font-mono-num text-xs text-slate-400">
                {act?.start_time_local || `Activity #${activityId}`}
              </span>
              {detail?.weather && (
                <span className="inline-flex items-center gap-1 font-mono-num text-xs text-cyan-300">
                  <CloudSun className="h-3.5 w-3.5" />
                  {detail.weather.tempC} °C · {detail.weather.humidity ?? "--"}% RH
                </span>
              )}
            </div>
            <h3 className="font-display mt-1 text-lg font-bold text-slate-100">
              {act?.name || `Activity ${activityId}`}
            </h3>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => void load(activityId, true)}
              className="rounded-lg border border-slate-700/80 p-1.5 text-slate-400 hover:text-emerald-300"
              title="Refresh from Garmin"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700/80 p-1.5 text-slate-400 hover:text-slate-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {loading && !detail && <LoadingState label="Pulling activity telemetry..." />}
          {error && <div className="text-xs text-rose-300">{error}</div>}

          {detail && (
            <>
              {/* Key KPIs */}
              {act && (
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-5">
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                    <div className="text-[10px] text-slate-400 uppercase">Duration</div>
                    <div className="font-mono-num mt-0.5 text-base font-bold text-slate-100">
                      {Math.round(act.duration_s / 60)} min
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                    <div className="text-[10px] text-slate-400 uppercase">Distance</div>
                    <div className="font-mono-num mt-0.5 text-base font-bold text-slate-100">
                      {(act.distance_m / 1000).toFixed(2)} km
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                    <div className="text-[10px] text-slate-400 uppercase">Avg / Max HR</div>
                    <div className="font-mono-num mt-0.5 text-base font-bold text-rose-300">
                      {act.avg_hr ? Math.round(act.avg_hr) : "--"} / {act.max_hr ? Math.round(act.max_hr) : "--"}
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                    <div className="text-[10px] text-slate-400 uppercase">TE (Aer / Ana)</div>
                    <div className="font-mono-num mt-0.5 text-base font-bold text-emerald-300">
                      {act.te_aerobic.toFixed(1)} / {act.te_anaerobic.toFixed(1)}
                    </div>
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
                    <div className="text-[10px] text-slate-400 uppercase">Power / GCT</div>
                    <div className="font-mono-num mt-0.5 text-base font-bold text-cyan-300">
                      {act.avg_power ? `${Math.round(act.avg_power)}W` : "--"}{" "}
                      {act.avg_gct_ms ? `· ${Math.round(act.avg_gct_ms)}ms` : ""}
                    </div>
                  </div>
                </div>
              )}

              {/* GPS Route Map */}
              {detail.route?.hasRoute && (
                <RouteMap route={detail.route} heightClass="h-[240px]" />
              )}

              {/* 5-Zone HR Breakdown */}
              {detail.hrZones.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="mb-2 flex items-center justify-between text-xs font-semibold text-slate-200">
                    <span>Heart Rate Time in Zones</span>
                    <span className="font-mono-num text-[11px] text-slate-400">
                      Z1-Z2 aerobic share:{" "}
                      {detail.hrZones
                        .filter((z) => z.zoneNumber <= 2)
                        .reduce((acc, z) => acc + z.percent, 0)
                        .toFixed(1)}
                      %
                    </span>
                  </div>
                  <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-900">
                    {detail.hrZones.map((z, idx) => (
                      <div
                        key={z.zoneNumber}
                        style={{
                          width: `${z.percent}%`,
                          backgroundColor: ZONE_COLORS[idx] ?? "#64748b",
                        }}
                        title={`Z${z.zoneNumber}: ${z.durationFormatted} (${z.percent}%)`}
                      />
                    ))}
                  </div>
                  <div className="mt-2.5 grid grid-cols-5 gap-2 text-center">
                    {detail.hrZones.map((z, idx) => (
                      <div key={z.zoneNumber} className="rounded-lg bg-slate-900/70 px-2 py-1.5">
                        <div className="flex items-center justify-center gap-1 text-[10px] font-semibold text-slate-300">
                          <span
                            className="h-2 w-2 rounded-full"
                            style={{ backgroundColor: ZONE_COLORS[idx] ?? "#64748b" }}
                          />
                          Z{z.zoneNumber} ({z.lowBoundary}+)
                        </div>
                        <div className="font-mono-num text-xs font-bold text-slate-100">{z.percent}%</div>
                        <div className="font-mono-num text-[10px] text-slate-400">{z.durationFormatted}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Lap Splits Chart + Table */}
              {detail.laps.length > 0 && (
                <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="text-xs font-semibold text-slate-200">Lap Splits &amp; HR Drift</div>
                  <div className="h-44 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={detail.laps}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                        <XAxis dataKey="lap" stroke="#64748b" fontSize={11} />
                        <YAxis stroke="#64748b" fontSize={11} domain={["auto", "auto"]} />
                        <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                        <Bar dataKey="avgHr" name="Avg HR (bpm)" fill="#ef4444" radius={[4, 4, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-slate-800 text-[10px] text-slate-400 uppercase">
                        <tr>
                          <th className="py-2 pr-3">Lap</th>
                          <th className="py-2 pr-3">Dist</th>
                          <th className="py-2 pr-3">Time</th>
                          <th className="py-2 pr-3">Pace</th>
                          <th className="py-2 pr-3">Avg HR</th>
                          <th className="py-2 pr-3">Cadence</th>
                          <th className="py-2">Power</th>
                        </tr>
                      </thead>
                      <tbody className="font-mono-num divide-y divide-slate-800/60">
                        {detail.laps.map((lap) => (
                          <tr key={lap.lap}>
                            <td className="py-1.5 pr-3 text-slate-300">#{lap.lap}</td>
                            <td className="py-1.5 pr-3">{lap.distanceKm.toFixed(2)} km</td>
                            <td className="py-1.5 pr-3">{lap.durationFormatted}</td>
                            <td className="py-1.5 pr-3 text-emerald-300">{lap.paceFormatted}</td>
                            <td className="py-1.5 pr-3">{lap.avgHr ?? "--"} bpm</td>
                            <td className="py-1.5 pr-3">{lap.cadence ?? "--"} spm</td>
                            <td className="py-1.5">{lap.power ? `${lap.power} W` : "--"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Strength Sets Table */}
              {detail.exerciseSets.length > 0 && (
                <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4">
                  <div className="mb-2 text-xs font-semibold text-slate-200">
                    Recorded Strength Sets ({detail.exerciseSets.filter((s) => s.set_type === "ACTIVE").length} active)
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-slate-800 text-[10px] text-slate-400 uppercase">
                        <tr>
                          <th className="py-1.5 pr-3">#</th>
                          <th className="py-1.5 pr-3">Category</th>
                          <th className="py-1.5 pr-3">Exercise</th>
                          <th className="py-1.5 pr-3">Reps</th>
                          <th className="py-1.5 pr-3">Load</th>
                          <th className="py-1.5">Rest</th>
                        </tr>
                      </thead>
                      <tbody className="font-mono-num divide-y divide-slate-800/50">
                        {detail.exerciseSets
                          .filter((s) => s.set_type === "ACTIVE")
                          .map((s) => (
                            <tr key={s.id}>
                              <td className="py-1.5 pr-3 text-slate-400">{s.set_index + 1}</td>
                              <td className="py-1.5 pr-3 text-cyan-300">{s.category}</td>
                              <td className="py-1.5 pr-3">{s.exercise_name || "--"}</td>
                              <td className="py-1.5 pr-3">{s.reps ?? "--"}</td>
                              <td className="py-1.5 pr-3">{s.weight_kg ?? 0} kg</td>
                              <td className="py-1.5 text-slate-400">{s.rest_s ? `${Math.round(s.rest_s)}s` : "--"}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* RPE & Feel Logger */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="mb-3 flex items-center gap-2 text-xs font-semibold text-slate-200">
                  <Gauge className="h-4 w-4 text-emerald-400" />
                  Perceived Effort (RPE) &amp; Session Feel (syncs to Garmin)
                </div>
                <div className="flex flex-wrap items-center gap-4">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">RPE:</span>
                    <input
                      type="range"
                      min={1}
                      max={10}
                      value={rpe}
                      onChange={(e) => setRpe(Number(e.target.value))}
                      className="accent-emerald-400"
                    />
                    <span className="font-mono-num w-8 text-xs font-bold text-emerald-300">{rpe}/10</span>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {FEEL_OPTIONS.map((opt) => (
                      <button
                        key={opt.val}
                        type="button"
                        onClick={() => setFeel(opt.val)}
                        className={`rounded-lg border px-2.5 py-1 text-[11px] font-medium transition ${
                          feel === opt.val
                            ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-200"
                            : "border-slate-700/70 bg-slate-900/60 text-slate-400"
                        }`}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={saveEffort}
                    disabled={savingEffort}
                    className="ml-auto rounded-xl bg-emerald-500 px-3.5 py-1.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
                  >
                    {savingEffort ? "Saving..." : "Save RPE & Feel"}
                  </button>
                </div>
                {effortNotice && <p className="mt-2 text-xs text-emerald-300">{effortNotice}</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
