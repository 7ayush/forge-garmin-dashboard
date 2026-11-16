import React, { useEffect, useState } from "react";
import { AlertTriangle, Award, Flame, MapPin } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
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
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";
import { RouteMap } from "../components/maps/RouteMap";
import type { ActivityDetailPayload } from "../types/forge";

export function EnginePage({
  refreshTick,
  onSelectActivity,
}: {
  refreshTick: number;
  onSelectActivity: (activityId: number) => void;
}) {
  const [days, setDays] = useState(30);
  const { data, loading, error, reload } = useAsyncData(
    () => forgeApi.getEngine(days),
    [refreshTick, days]
  );
  const [latestRouteDetail, setLatestRouteDetail] = useState<ActivityDetailPayload | null>(null);

  const latestGpsActivity = data?.activities.find((a) => a.hasPolyline) ?? null;

  useEffect(() => {
    if (!latestGpsActivity) {
      setLatestRouteDetail(null);
      return;
    }
    let cancelled = false;
    forgeApi
      .getActivityDetail(latestGpsActivity.activityId)
      .then((res) => {
        if (!cancelled) setLatestRouteDetail(res);
      })
      .catch(() => {
        if (!cancelled) setLatestRouteDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [latestGpsActivity?.activityId]);

  if (loading && !data) return <LoadingState label="Computing Cardio Engine & Workload..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const zw = data.zones_window;
  const totalMin = Math.round(zw.total_zone_min || 0);
  const zoneMeta = [
    { zone: "Z1 Recovery", color: "bg-slate-500" },
    { zone: "Z2 Aerobic Base", color: "bg-emerald-400" },
    { zone: "Z3 Tempo", color: "bg-cyan-400" },
    { zone: "Z4 Threshold", color: "bg-amber-400" },
    { zone: "Z5 VO2 Max", color: "bg-rose-500" },
  ];
  const zoneBars = zoneMeta.map((meta, idx) => ({
    ...meta,
    min: Math.round((zw.zones_sec?.[idx] ?? 0) / 60),
    pct: Math.round(zw.zones_pct?.[idx] ?? 0),
  }));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="emerald">
            Status: {data.training_status.status || "Pending"}
          </StatusBadge>
          <StatusBadge tone={(data.training_status.acwr ?? 0) > 1.5 ? "amber" : "cyan"}>
            ACWR: {data.training_status.acwr ?? "--"} ({data.training_status.acwr_status || "N/A"})
          </StatusBadge>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/80 p-1">
          {[7, 14, 30, 90].map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`font-mono-num rounded-lg px-2.5 py-1 text-xs font-semibold transition ${
                days === d ? "bg-emerald-500/20 text-emerald-200" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {d}D
            </button>
          ))}
        </div>
      </div>

      {/* Warnings & Interference Alerts */}
      {data.interference_warnings.length > 0 && (
        <div className="space-y-2">
          {data.interference_warnings.map((w, i) => (
            <InfoCallout key={i} tone="amber">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                <span>{w}</span>
              </div>
            </InfoCallout>
          ))}
        </div>
      )}

      {/* KPI Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile
          label={`Z2 Discipline (${days}D)`}
          value={zw.z2_discipline_pct !== null ? `${zw.z2_discipline_pct}%` : "--"}
          subtext={`Target >= ${data.z2_target_pct}% (${totalMin} min total)`}
          tone={(zw.z2_discipline_pct ?? 0) >= data.z2_target_pct ? "emerald" : "amber"}
        />
        <KpiTile
          label="VO2 Max"
          value={data.vo2_trend.length ? data.vo2_trend[data.vo2_trend.length - 1].vo2_max : "--"}
          unit="mL/kg/min"
          tone="cyan"
        />
        <KpiTile
          label="Lactate Threshold"
          value={data.lactate.lthr ?? "--"}
          unit="bpm"
          subtext={data.lactate.pace ? `Pace ${data.lactate.pace} · ${data.lactate.power_watts ?? "--"}W` : ""}
          tone="lime"
        />
        <KpiTile
          label="Endurance Score"
          value={data.endurance.overall ?? "--"}
          subtext={`30d max: ${data.endurance.max ?? "--"}`}
          tone="emerald"
        />
        <KpiTile
          label="Hill Score"
          value={data.hill.overall ?? "--"}
          subtext={`Str ${data.hill.strength ?? "--"} · End ${data.hill.endurance ?? "--"}`}
        />
        <KpiTile
          label="Interference"
          value={data.interference_events.length}
          unit="events"
          subtext="Runs within +-6h of legs"
          tone={data.interference_events.length > 0 ? "amber" : "emerald"}
        />
      </div>

      {/* Zones & Load Trend */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-5">
          <SectionHeader
            eyebrow={`Heart Rate Zones (${days}D)`}
            title="Polarized Aerobic Distribution"
            subtitle="Target: >=75% of cardio time in Z1-Z2"
          />
          <div className="space-y-3">
            {zoneBars.map((zb) => (
              <div key={zb.zone}>
                <div className="mb-1 flex justify-between text-xs">
                  <span className="text-slate-300">{zb.zone}</span>
                  <span className="font-mono-num text-slate-200">
                    {zb.min} min ({zb.pct}%)
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div className={`h-full rounded-full ${zb.color}`} style={{ width: `${zb.pct}%` }} />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3 text-xs">
            <div className="flex justify-between text-slate-300">
              <span>Load Focus Feedback</span>
              <span className="font-mono-num text-amber-300">
                {data.training_status.load_balance_feedback || "Pending"}
              </span>
            </div>
            <div className="font-mono-num mt-1 text-[11px] text-slate-400">
              Low: {data.training_status.load_aerobic_low ?? "--"} · High:{" "}
              {data.training_status.load_aerobic_high ?? "--"} · Ana:{" "}
              {data.training_status.load_anaerobic ?? "--"}
            </div>
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-7">
          <SectionHeader eyebrow="Acute vs Chronic" title="Workload & ACWR Trajectory" />
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.load_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Area type="monotone" dataKey="acute_load" name="Acute Load" stroke="#10b981" fill="#10b981" fillOpacity={0.18} />
                <Line type="monotone" dataKey="chronic_load" name="Chronic Load" stroke="#22d3ee" dot={false} strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </div>

      {/* Aerobic Efficiency Factor + Race Predictions & PRs */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-7">
          <SectionHeader
            eyebrow="Running Economy"
            title="Aerobic Efficiency Factor (Speed / Avg HR)"
            subtitle="Rising trend at submaximal effort signals stronger aerobic adaptation"
          />
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.efficiency_series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} domain={["auto", "auto"]} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="efficiency_index" name="Efficiency Index" stroke="#a3e635" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-5">
          <SectionHeader eyebrow="Garmin Predictor & PRs" title="Race Projections" />
          <div className="grid grid-cols-2 gap-2.5">
            {Object.entries(data.race_predictions).map(([dist, info]) => (
              <div key={dist} className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
                <div className="text-[11px] text-slate-400">{dist}</div>
                <div className="font-mono-num text-base font-bold text-emerald-300">{info.formatted}</div>
                <div className="font-mono-num text-[10px] text-slate-400">{info.pace}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 border-t border-slate-800/80 pt-3">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-200">
              <Award className="h-3.5 w-3.5 text-lime-300" /> Personal Records
            </div>
            <div className="max-h-36 space-y-1.5 overflow-y-auto text-xs">
              {data.personal_records.slice(0, 8).map((pr) => (
                <div key={pr.typeId} className="flex items-center justify-between text-slate-300">
                  <span>{pr.label}</span>
                  <span className="font-mono-num font-bold text-slate-100">{pr.displayValue}</span>
                </div>
              ))}
            </div>
          </div>
        </GlassCard>
      </div>

      {/* Latest Outdoor Route */}
      {latestGpsActivity && latestRouteDetail?.route?.hasRoute && (
        <GlassCard>
          <div className="mb-3 flex items-center justify-between gap-2">
            <SectionHeader
              eyebrow="Latest Outdoor Route"
              title={latestGpsActivity.name}
            />
            <button
              type="button"
              onClick={() => onSelectActivity(latestGpsActivity.activityId)}
              className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-300 transition hover:bg-emerald-500/20"
            >
              Inspect Splits &amp; HR
            </button>
          </div>
          <RouteMap
            route={latestRouteDetail.route}
            heightClass="h-[260px]"
            title={`${latestGpsActivity.date} · ${latestGpsActivity.distanceKm} km`}
          />
        </GlassCard>
      )}

      {/* Activity Table */}
      <GlassCard>
        <SectionHeader eyebrow="Engine Log" title={`Recorded Sessions (${data.activities.length})`} />
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 text-[10px] text-slate-400 uppercase">
              <tr>
                <th className="py-2 pr-3">Date</th>
                <th className="py-2 pr-3">Session</th>
                <th className="py-2 pr-3">Dist / Time</th>
                <th className="py-2 pr-3">Pace</th>
                <th className="py-2 pr-3">Avg / Max HR</th>
                <th className="py-2 pr-3">Z1-Z2 %</th>
                <th className="py-2">Load</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {data.activities.slice(0, 25).map((a) => (
                <tr
                  key={a.activityId}
                  onClick={() => onSelectActivity(a.activityId)}
                  className="cursor-pointer transition hover:bg-slate-900/60"
                >
                  <td className="font-mono-num py-2 pr-3 text-slate-400">{a.date}</td>
                  <td className="py-2 pr-3 font-medium text-slate-100">
                    {a.name}
                    <span className="ml-2 text-[10px] text-slate-400">{a.type}</span>
                    {a.hasPolyline && (
                      <span className="ml-2 inline-flex items-center gap-0.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-300">
                        <MapPin className="h-2.5 w-2.5" />
                        GPS
                      </span>
                    )}
                  </td>
                  <td className="font-mono-num py-2 pr-3">
                    {a.distanceKm > 0 ? `${a.distanceKm} km · ` : ""}
                    {a.durationFormatted}
                  </td>
                  <td className="font-mono-num py-2 pr-3 text-emerald-300">{a.paceFormatted || "--"}</td>
                  <td className="font-mono-num py-2 pr-3">
                    {a.avgHr ?? "--"} / {a.maxHr ?? "--"}
                  </td>
                  <td className="font-mono-num py-2 pr-3">
                    {a.z1_2_pct !== null ? `${a.z1_2_pct}%` : "--"}
                  </td>
                  <td className="font-mono-num py-2 font-semibold text-cyan-300">{a.trainingLoad}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>
    </div>
  );
}
