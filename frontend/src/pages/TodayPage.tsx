import React from "react";
import { AlertCircle, ArrowRight, MapPin, ShieldCheck, Zap } from "lucide-react";
import { forgeApi } from "../api/client";
import {
  GlassCard,
  InfoCallout,
  KpiTile,
  LoadingState,
  ErrorBanner,
  ProgressBar,
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";
import type { PageRoute } from "../types/forge";

export function TodayPage({
  refreshTick,
  onNavigate,
  onSelectActivity,
  onOpenQuickLog,
}: {
  refreshTick: number;
  onNavigate: (route: PageRoute) => void;
  onSelectActivity: (activityId: number) => void;
  onOpenQuickLog: () => void;
}) {
  const { data, loading, error, reload } = useAsyncData(() => forgeApi.getToday(), [refreshTick]);

  if (loading && !data) return <LoadingState label="Synthesizing Today Cockpit..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const { recommendation: rec, vitals, forge_score: score, bio_health_index: bio } = data;
  const heroBorder =
    rec.severity === "crimson"
      ? "border-rose-500/40 bg-rose-950/15"
      : rec.severity === "amber"
      ? "border-amber-500/40 bg-amber-950/15"
      : "border-emerald-500/40 bg-emerald-950/15";

  return (
    <div className="space-y-6">
      {/* Row 1: Today's Session Recommendation + Forge Score + Bio Health */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <GlassCard className={`lg:col-span-7 ${heroBorder}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <StatusBadge tone={rec.severity}>RULE {rec.rule_id}</StatusBadge>
              <StatusBadge tone={rec.confidence === "HIGH" ? "emerald" : "amber"}>
                {rec.confidence} CONFIDENCE
              </StatusBadge>
            </div>
            <span className="font-mono-num text-xs text-slate-400">Latest snapshot: {data.date}</span>
          </div>

          <h2 className="font-display mt-3 text-xl font-extrabold tracking-tight text-slate-50 sm:text-2xl">
            {rec.verdict}
          </h2>
          <p className="mt-1.5 text-sm leading-relaxed text-slate-300">{rec.sub_verdict}</p>

          <ul className="mt-4 space-y-1.5 border-t border-slate-800/80 pt-3 text-xs text-slate-300">
            {rec.reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                <Zap className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                <span>{r}</span>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onNavigate("strength")}
              className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
            >
              Open Strength Lab <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={onOpenQuickLog}
              className="rounded-xl border border-slate-700 bg-slate-900/75 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-slate-500"
            >
              Log Morning Metrics
            </button>
          </div>
        </GlassCard>

        <GlassCard className="flex flex-col justify-between lg:col-span-5">
          <div>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-mono-num text-[10px] tracking-widest text-emerald-400 uppercase">
                  Weekly Execution
                </div>
                <h3 className="font-display text-base font-bold text-slate-100">FORGE Score</h3>
              </div>
              <div className="text-right">
                <span className="font-mono-num text-3xl font-extrabold text-lime-300">{score.overall}</span>
                <span className="font-mono-num text-xs text-slate-400">/100</span>
              </div>
            </div>

            <div className="mt-4 space-y-3 text-xs">
              <div>
                <div className="mb-1 flex justify-between text-slate-300">
                  <span>Train (Muscles {score.muscles_at_target} · Lifts {score.lifts_this_week})</span>
                  <span className="font-mono-num font-bold text-emerald-300">{score.train_pct}%</span>
                </div>
                <ProgressBar value={score.train_pct} tone="emerald" />
              </div>

              <div>
                <div className="mb-1 flex justify-between text-slate-300">
                  <span>
                    Recover (Sleep {score.sleep_nights_hit} · HRV {vitals.hrv_status || "N/A"})
                  </span>
                  <span className="font-mono-num font-bold text-cyan-300">{score.recover_pct}%</span>
                </div>
                <ProgressBar value={score.recover_pct} tone="cyan" />
              </div>

              <div>
                <div className="mb-1 flex justify-between text-slate-300">
                  <span>
                    Fuel ({score.fuel_pct !== null ? `Protein ${score.protein_days_hit}` : "Excluded — 0 logs this week"})
                  </span>
                  <span className="font-mono-num font-bold text-amber-300">
                    {score.fuel_pct !== null ? `${score.fuel_pct}%` : "Re-weighted"}
                  </span>
                </div>
                <ProgressBar value={score.fuel_pct ?? 0} tone="amber" />
              </div>
            </div>
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-slate-800/80 pt-3 text-xs">
            <div className="flex items-center gap-2 text-slate-300">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <span>Bio Health Index</span>
            </div>
            <span className="font-mono-num font-bold text-slate-100">{bio.overall}/100</span>
          </div>
        </GlassCard>
      </div>

      {/* Row 2: 5 Vitals Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <KpiTile
          label="Readiness"
          value={vitals.readiness ?? "--"}
          unit="/100"
          tone={(vitals.readiness ?? 0) >= 70 ? "emerald" : (vitals.readiness ?? 0) >= 50 ? "amber" : "crimson"}
          subtext={`${vitals.readiness_level || "Pending"} · ${vitals.recovery_time_h ?? 0}h rec left`}
          sparkline={data.sparklines.readiness}
          onClick={() => onNavigate("recovery")}
        />
        <KpiTile
          label="Last Night Sleep"
          value={vitals.sleep_h ?? "--"}
          unit="hrs"
          tone={(vitals.sleep_h ?? 0) >= 7 ? "emerald" : "amber"}
          subtext={`Score ${vitals.sleep_score ?? "--"} · 7d debt ${vitals.sleep_debt_7d_h}h`}
          sparkline={data.sparklines.sleep}
          onClick={() => onNavigate("recovery")}
        />
        <KpiTile
          label="Overnight HRV"
          value={vitals.hrv_night ?? "--"}
          unit="ms"
          tone={vitals.hrv_status === "BALANCED" ? "emerald" : "amber"}
          subtext={`7d avg ${vitals.hrv_weekly ?? "--"} ms · ${vitals.hrv_status || "Pending"}`}
          sparkline={data.sparklines.hrv}
          onClick={() => onNavigate("recovery")}
        />
        <KpiTile
          label="Resting HR"
          value={vitals.rhr ?? "--"}
          unit="bpm"
          tone="cyan"
          subtext={`28d baseline: ${vitals.rhr_baseline_28d ?? "--"} bpm · Steps ${(vitals.steps_today ?? 0).toLocaleString()}`}
          sparkline={data.sparklines.rhr}
          onClick={() => onNavigate("recovery")}
        />
        <KpiTile
          label="Workload ACWR"
          value={vitals.acwr ?? "--"}
          unit={vitals.acwr_status || ""}
          tone={(vitals.acwr ?? 0) > 1.5 ? "amber" : "lime"}
          subtext={`Acute load ${vitals.acute_load ?? "--"} · BB ${vitals.bb_peak ?? "--"} peak`}
          onClick={() => onNavigate("engine")}
        />
      </div>

      {/* Row 3: Alerts & Action Queue */}
      {data.alerts.length > 0 && (
        <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
          {data.alerts.map((alert) => (
            <InfoCallout key={alert.id} tone={alert.severity === "amber" || alert.severity === "crimson" ? "amber" : "cyan"}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>{alert.title}</span>
                <button
                  type="button"
                  onClick={() => onNavigate(alert.route)}
                  className="font-semibold underline decoration-dotted underline-offset-4 hover:text-white"
                >
                  {alert.cta}
                </button>
              </div>
            </InfoCallout>
          ))}
        </div>
      )}

      {/* Row 4: Muscle Recency Strip + Recent Workouts */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-6">
          <SectionHeader
            eyebrow="Weekly Hypertrophy Progress"
            title="Muscle Volume & Recovery Recency"
            subtitle="Fractional sets this week vs MEV (10-20 sets)"
            right={
              <button
                type="button"
                onClick={() => onNavigate("strength")}
                className="text-xs font-semibold text-emerald-300 hover:underline"
              >
                Full Muscle Map
              </button>
            }
          />
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            {data.muscle_recency
              .filter((m) => m.muscle !== "cardio")
              .slice(0, 12)
              .map((m) => {
                const tone =
                  m.status === "optimal"
                    ? "emerald"
                    : m.status === "above_target"
                    ? "amber"
                    : m.fractional_sets > 0
                    ? "cyan"
                    : "neutral";
                return (
                  <button
                    key={m.muscle}
                    type="button"
                    onClick={() => onNavigate("strength")}
                    className="rounded-xl border border-slate-800/90 bg-slate-950/60 p-2.5 text-left transition hover:border-emerald-500/40"
                  >
                    <div className="flex items-center justify-between text-[11px] font-medium text-slate-200">
                      <span className="truncate">{m.label}</span>
                      <span className="font-mono-num text-[10px] text-slate-400">
                        {m.days_since !== null ? `${m.days_since}d` : "--"}
                      </span>
                    </div>
                    <div className="mt-1.5 flex items-baseline justify-between">
                      <span className="font-mono-num text-sm font-bold text-slate-100">
                        {m.fractional_sets}
                        <span className="text-[10px] font-normal text-slate-500">/{m.target_min}</span>
                      </span>
                      <span className="text-[10px] text-slate-400">all {m.all_time_direct}</span>
                    </div>
                    <div className="mt-1.5">
                      <ProgressBar value={m.fractional_sets} max={m.target_min} tone={tone} heightClass="h-1.5" />
                    </div>
                  </button>
                );
              })}
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-6">
          <SectionHeader
            eyebrow="Telemetry Stream"
            title="Recent Workouts"
            subtitle="Click any session to open HR zones, splits, sets & RPE editor"
          />
          {data.recent_activities.length === 0 ? (
            <div className="flex items-center gap-2 py-8 text-xs text-slate-400">
              <AlertCircle className="h-4 w-4" /> Syncing Garmin activity history...
            </div>
          ) : (
            <div className="space-y-2">
              {data.recent_activities.map((act) => (
                <button
                  key={act.activityId}
                  type="button"
                  onClick={() => onSelectActivity(act.activityId)}
                  className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-800/80 bg-slate-950/60 px-3.5 py-2.5 text-left transition hover:border-emerald-500/40"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-xs font-semibold text-slate-100">{act.name}</span>
                      <StatusBadge tone={act.type.includes("strength") ? "lime" : "cyan"}>
                        {act.type.replace("_", " ")}
                      </StatusBadge>
                      {act.hasPolyline && (
                        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
                          <MapPin className="h-2.5 w-2.5" />
                          GPS
                        </span>
                      )}
                    </div>
                    <div className="font-mono-num mt-0.5 text-[11px] text-slate-400">
                      {act.date} · {act.durationFormatted}
                      {act.distanceKm > 0 ? ` · ${act.distanceKm} km` : ""}
                      {act.paceFormatted ? ` (${act.paceFormatted})` : ""}
                    </div>
                  </div>
                  <div className="font-mono-num shrink-0 text-right">
                    <div className="text-xs font-bold text-slate-200">
                      {act.avgHr ? `${act.avgHr} bpm` : "--"}
                    </div>
                    <div className="text-[10px] text-emerald-300">Load {act.trainingLoad}</div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
