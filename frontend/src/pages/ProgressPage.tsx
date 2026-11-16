import React from "react";
import { Award, CheckCircle2, Download, Flame, Target, XCircle } from "lucide-react";
import { forgeApi } from "../api/client";
import {
  ErrorBanner,
  GlassCard,
  KpiTile,
  LoadingState,
  ProgressBar,
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";

export function ProgressPage({ refreshTick }: { refreshTick: number }) {
  const { data, loading, error, reload } = useAsyncData(() => forgeApi.getProgress(), [refreshTick]);

  if (loading && !data) return <LoadingState label="Compiling Athlete Roadmap & Reviews..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const wr = data.weekly_review;
  const ms = data.monthly_summary;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <StatusBadge tone="lime">
            Weekly Window: {wr.week_start} -&gt; {wr.week_end}
          </StatusBadge>
        </div>
        <div className="flex gap-2">
          <a
            href="/api/progress/export?format=markdown"
            className="inline-flex items-center gap-1.5 rounded-xl border border-emerald-400/40 bg-emerald-500/15 px-3 py-1.5 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/25"
          >
            <Download className="h-3.5 w-3.5" /> Export Weekly Review (.md)
          </a>
          <a
            href="/api/progress/export?format=json"
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 hover:border-slate-500"
          >
            Export JSON
          </a>
        </div>
      </div>

      {/* Streaks + 30D Summary */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile label="FORGE Score" value={data.forge_score.overall} unit="/100" tone="lime" />
        <KpiTile label="30D Running" value={ms.run_km_30d} unit="km" tone="cyan" />
        <KpiTile
          label="30D Tonnage"
          value={`${Math.round(ms.strength_tonnage_30d / 1000 * 10) / 10}t`}
          subtext={`${ms.strength_tonnage_30d.toLocaleString()} kg`}
          tone="emerald"
        />
        <KpiTile label="7H+ Sleep Streak" value={data.streaks.sleep_7h_streak} unit="nights" tone="cyan" />
        <KpiTile label="Lifts This Week" value={data.streaks.lifts_this_week} tone="emerald" />
        <KpiTile label="VO2 Max Latest" value={ms.vo2_latest ?? "--"} unit="mL/kg" tone="lime" />
      </div>

      {/* Weekly Review Cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <GlassCard>
          <SectionHeader eyebrow="What Worked" title="Wins" />
          <ul className="space-y-2 text-xs text-slate-200">
            {wr.wins.map((w, i) => (
              <li key={i} className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        </GlassCard>

        <GlassCard>
          <SectionHeader eyebrow="Bottlenecks" title="Misses & Leaks" />
          <ul className="space-y-2 text-xs text-slate-300">
            {(wr.misses.length ? wr.misses : ["No critical misses detected."]).map((m, i) => (
              <li key={i} className="flex items-start gap-2">
                <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
                <span>{m}</span>
              </li>
            ))}
          </ul>
        </GlassCard>

        <GlassCard>
          <SectionHeader eyebrow="Next 7 Days" title="Top-3 Focus" />
          <ul className="space-y-2 text-xs text-slate-200">
            {wr.focus_items.map((f, i) => (
              <li key={i} className="flex items-start gap-2">
                <Target className="mt-0.5 h-4 w-4 shrink-0 text-lime-300" />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </GlassCard>
      </div>

      {/* 2-Year Roadmap Phases */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {data.roadmap.map((phase, idx) => (
          <GlassCard key={phase.phase}>
            <div className="flex items-center justify-between">
              <StatusBadge tone={idx === 0 ? "emerald" : idx === 1 ? "cyan" : "lime"}>
                PHASE {idx + 1}
              </StatusBadge>
              <span className="font-mono-num text-[11px] text-slate-400">{phase.window}</span>
            </div>
            <h3 className="font-display mt-2.5 text-base font-bold text-slate-100">{phase.phase}</h3>
            <div className="mt-4 space-y-3 text-xs">
              {phase.targets.map((t) => (
                <div key={t.label}>
                  <div className="mb-1 flex justify-between gap-2 text-slate-300">
                    <span className="truncate">{t.label}</span>
                    <span className="font-mono-num shrink-0 font-semibold text-emerald-300">{t.current}</span>
                  </div>
                  <ProgressBar value={t.pct} tone={idx === 0 ? "emerald" : idx === 1 ? "cyan" : "lime"} heightClass="h-1.5" />
                </div>
              ))}
            </div>
          </GlassCard>
        ))}
      </div>

      {/* Garmin Badges */}
      {data.garmin_badges.length > 0 && (
        <GlassCard>
          <SectionHeader eyebrow="Garmin Connect Achievements" title="Earned Badges" />
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
            {data.garmin_badges.map((b, i) => (
              <div key={i} className="flex items-center gap-3 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
                <Award className="h-5 w-5 shrink-0 text-amber-300" />
                <div className="min-w-0">
                  <div className="truncate text-xs font-semibold text-slate-100">{b.name}</div>
                  <div className="font-mono-num text-[10px] text-slate-400">
                    {b.date} · {b.points ?? 0} pts
                  </div>
                </div>
              </div>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
