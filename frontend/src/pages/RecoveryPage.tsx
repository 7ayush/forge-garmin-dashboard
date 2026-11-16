import React, { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
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
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";
import type { IntradayPayload } from "../types/forge";

export function RecoveryPage({ refreshTick }: { refreshTick: number }) {
  const [days, setDays] = useState(14);
  const { data, loading, error, reload } = useAsyncData(
    () => forgeApi.getRecovery(days),
    [refreshTick, days]
  );

  const [selectedDate, setSelectedDate] = useState<string>("");
  const [intraday, setIntraday] = useState<IntradayPayload | null>(null);
  const [intradayLoading, setIntradayLoading] = useState(false);

  useEffect(() => {
    if (data?.daily.length && !selectedDate) {
      setSelectedDate(data.daily[data.daily.length - 1].date);
    }
  }, [data, selectedDate]);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setIntradayLoading(true);
    forgeApi
      .getIntraday(selectedDate)
      .then((res) => {
        if (!cancelled) setIntraday(res);
      })
      .catch(() => {
        if (!cancelled) setIntraday(null);
      })
      .finally(() => {
        if (!cancelled) setIntradayLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedDate]);

  if (loading && !data) return <LoadingState label="Analyzing Sleep & Autonomic Recovery..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const s = data.summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <StatusBadge tone={s.rhr_spike_alert ? "crimson" : "emerald"}>
            {s.rhr_spike_alert ? "RHR SPIKE ALERT" : "Autonomic Baseline Normal"}
          </StatusBadge>
          <StatusBadge tone={s.hrv_status === "BALANCED" ? "emerald" : "amber"}>
            HRV Status: {s.hrv_status || "Pending"}
          </StatusBadge>
        </div>

        <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-950/80 p-1">
          {[7, 14, 28].map((d) => (
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

      {!s.spo2_available && s.spo2_hint && (
        <InfoCallout tone="cyan">{s.spo2_hint}</InfoCallout>
      )}

      {/* KPI Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile
          label="7D Avg Sleep"
          value={s.avg_sleep_h ?? "--"}
          unit="hrs"
          subtext={`Score avg ${s.avg_sleep_score ?? "--"} · ${s.nights_tracked_7d}/7 nights`}
          tone={(s.avg_sleep_h ?? 0) >= 7 ? "emerald" : "amber"}
        />
        <KpiTile
          label="7D Sleep Debt"
          value={s.sleep_debt_7d_h}
          unit="hrs"
          subtext={`vs ${data.sleep_target_h}h target`}
          tone={s.sleep_debt_7d_h > 4 ? "amber" : "emerald"}
        />
        <KpiTile
          label="Bedtime SD"
          value={s.bedtime_sd_min ?? "--"}
          unit="min"
          subtext="Lower = steadier circadian rhythm"
          tone={(s.bedtime_sd_min ?? 0) <= 45 ? "emerald" : "amber"}
        />
        <KpiTile
          label="RHR vs 28D"
          value={s.rhr_latest ?? "--"}
          unit="bpm"
          subtext={`Baseline ${s.rhr_baseline_28d ?? "--"} bpm`}
          tone={s.rhr_spike_alert ? "crimson" : "cyan"}
        />
        <KpiTile
          label="Overnight HRV"
          value={s.hrv_latest ?? "--"}
          unit="ms"
          subtext={`28d avg ${s.hrv_baseline_28d ?? "--"} ms`}
          tone="emerald"
        />
        <KpiTile
          label="Nights < 5h"
          value={s.nights_under_5h_win}
          subtext={`in trailing ${days}d window`}
          tone={s.nights_under_5h_win > 0 ? "crimson" : "emerald"}
        />
      </div>

      {/* Sleep Architecture + HRV vs RHR */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-6">
          <SectionHeader eyebrow="Sleep Architecture" title="Nightly Stages (Deep / REM / Light)" />
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <ReferenceLine y={data.sleep_target_h} stroke="#a3e635" strokeDasharray="3 3" />
                <Bar dataKey="deepHours" name="Deep (h)" stackId="s" fill="#10b981" />
                <Bar dataKey="remHours" name="REM (h)" stackId="s" fill="#22d3ee" />
                <Bar dataKey="lightHours" name="Light (h)" stackId="s" fill="#334155" />
                <Bar dataKey="awakeHours" name="Awake (h)" stackId="s" fill="#f59e0b" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-6">
          <SectionHeader eyebrow="Autonomic Stress Watch" title="Overnight HRV & Resting HR" />
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                <YAxis yAxisId="left" stroke="#10b981" fontSize={10} />
                <YAxis yAxisId="right" orientation="right" stroke="#ef4444" fontSize={10} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Line yAxisId="left" type="monotone" dataKey="hrvNight" name="HRV (ms)" stroke="#10b981" strokeWidth={2} />
                <Line yAxisId="right" type="monotone" dataKey="rhr" name="RHR (bpm)" stroke="#ef4444" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>
      </div>

      {/* Intraday Inspector */}
      <GlassCard>
        <SectionHeader
          eyebrow="Minute-by-Minute Biometrics"
          title="Intraday Heart Rate, Body Battery & Stress Curve"
          right={
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="font-mono-num rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-slate-100"
              />
              <button
                type="button"
                onClick={() => {
                  if (!selectedDate) return;
                  setIntradayLoading(true);
                  forgeApi
                    .getIntraday(selectedDate, true)
                    .then(setIntraday)
                    .finally(() => setIntradayLoading(false));
                }}
                className="rounded-xl border border-slate-700 p-1.5 text-slate-300 hover:border-emerald-400"
                title="Refresh intraday telemetry from Garmin"
              >
                <RefreshCw className={`h-4 w-4 ${intradayLoading ? "animate-spin text-emerald-400" : ""}`} />
              </button>
            </div>
          }
        />

        {intraday ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
                <span className="text-slate-400">HR Range</span>
                <div className="font-mono-num text-sm font-bold text-slate-100">
                  {intraday.summary.minHr ?? "--"} - {intraday.summary.maxHr ?? "--"} bpm (RHR{" "}
                  {intraday.summary.restingHr ?? "--"})
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
                <span className="text-slate-400">Body Battery +/-</span>
                <div className="font-mono-num text-sm font-bold text-emerald-300">
                  +{intraday.summary.bbCharged ?? 0} / -{intraday.summary.bbDrained ?? 0}
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
                <span className="text-slate-400">Avg / Max Stress</span>
                <div className="font-mono-num text-sm font-bold text-amber-300">
                  {intraday.summary.avgStress ?? "--"} / {intraday.summary.maxStress ?? "--"}
                </div>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs">
                <span className="text-slate-400">Respiration (Sleep/Wake)</span>
                <div className="font-mono-num text-sm font-bold text-cyan-300">
                  {intraday.summary.respSleepAvg ?? "--"} / {intraday.summary.respWakingAvg ?? "--"} brpm
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="h-52 w-full rounded-xl border border-slate-800/70 bg-slate-950/50 p-3">
                <div className="mb-1 text-[11px] font-semibold text-slate-300">Intraday Heart Rate (bpm)</div>
                <ResponsiveContainer width="100%" height="90%">
                  <AreaChart data={intraday.heartRate}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
                    <XAxis dataKey="t" stroke="#64748b" fontSize={10} minTickGap={30} />
                    <YAxis stroke="#64748b" fontSize={10} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                    <Area type="monotone" dataKey="v" name="HR (bpm)" stroke="#ef4444" fill="#ef4444" fillOpacity={0.18} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div className="h-52 w-full rounded-xl border border-slate-800/70 bg-slate-950/50 p-3">
                <div className="mb-1 text-[11px] font-semibold text-slate-300">Body Battery Curve</div>
                <ResponsiveContainer width="100%" height="90%">
                  <AreaChart data={intraday.bodyBattery}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.08)" />
                    <XAxis dataKey="t" stroke="#64748b" fontSize={10} minTickGap={30} />
                    <YAxis stroke="#64748b" fontSize={10} domain={[0, 100]} />
                    <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                    <Area type="monotone" dataKey="v" name="Body Battery" stroke="#10b981" fill="#10b981" fillOpacity={0.2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-8 text-center text-xs text-slate-400">
            Select a date to view Garmin intraday curve.
          </div>
        )}
      </GlassCard>
    </div>
  );
}
