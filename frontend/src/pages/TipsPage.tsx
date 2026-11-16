import React, { useState } from "react";
import { Award, Flame, Gauge, HeartPulse, Moon, RefreshCw, Sparkles, Timer, Trophy } from "lucide-react";
import { forgeApi } from "../api/client";
import {
  ErrorBanner,
  GlassCard,
  LoadingState,
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";

export function TipsPage({
  refreshTick,
  onSelectActivity,
}: {
  refreshTick: number;
  onSelectActivity: (activityId: number) => void;
}) {
  const [forceTick, setForceTick] = useState(0);
  const { data, loading, error, reload } = useAsyncData(
    () => forgeApi.getTips(forceTick > 0),
    [refreshTick, forceTick]
  );

  if (loading && !data) return <LoadingState label="Fetching Garmin Tips, Reports & Summaries..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold tracking-wider text-emerald-400 uppercase">
            Garmin Intelligence &amp; Reports
          </div>
          <h2 className="text-xl font-bold text-slate-100">Tips, Coach Signals &amp; Benchmarks</h2>
        </div>
        <button
          type="button"
          onClick={() => setForceTick((t) => t + 1)}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:border-emerald-500/40 hover:text-emerald-300"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Garmin Reports
        </button>
      </div>

      {/* Actionable Tips */}
      <GlassCard>
        <SectionHeader eyebrow="Daily Coach Signals" title="Actionable Tips from Garmin Telemetry" />
        <div className="grid gap-3 md:grid-cols-2">
          {data.tips.map((tip) => (
            <div
              key={tip.id}
              className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"
            >
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-100">
                  <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
                  {tip.title}
                </span>
                <StatusBadge
                  tone={
                    tip.tone === "emerald"
                      ? "emerald"
                      : tip.tone === "amber"
                        ? "amber"
                        : tip.tone === "rose"
                          ? "crimson"
                          : "cyan"
                  }
                >
                  {tip.category}
                </StatusBadge>
              </div>
              <p className="text-xs text-slate-300">{tip.summary}</p>
              <p className="mt-2 text-[11px] font-medium text-emerald-300">
                Next: {tip.action}
              </p>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Fitness Age + Endurance/Hill + Lactate Threshold */}
      <div className="grid gap-4 md:grid-cols-3">
        <GlassCard>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
            <HeartPulse className="h-4 w-4 text-emerald-400" />
            Fitness Age Report
          </div>
          <div className="font-mono-num text-3xl font-bold text-emerald-300">
            {data.fitnessAge.fitnessAge ?? "--"} <span className="text-sm font-normal text-slate-400">yrs</span>
          </div>
          <div className="mt-2 space-y-1 text-xs text-slate-400">
            <div>Chronological Age: <span className="font-mono-num text-slate-200">{data.fitnessAge.chronologicalAge ?? "--"} yrs</span></div>
            <div>Achievable Target: <span className="font-mono-num text-emerald-300">{data.fitnessAge.achievableFitnessAge ?? "--"} yrs</span></div>
            {data.fitnessAge.previousFitnessAge !== null && (
              <div>Previous: <span className="font-mono-num text-slate-300">{data.fitnessAge.previousFitnessAge} yrs</span></div>
            )}
          </div>
        </GlassCard>

        <GlassCard>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
            <Gauge className="h-4 w-4 text-cyan-400" />
            Endurance &amp; Hill Scores
          </div>
          <div className="flex items-baseline gap-4">
            <div>
              <div className="text-[10px] text-slate-400 uppercase">Endurance</div>
              <div className="font-mono-num text-2xl font-bold text-cyan-300">
                {data.enduranceScore.overall ?? "--"}
              </div>
            </div>
            <div>
              <div className="text-[10px] text-slate-400 uppercase">Hill Score</div>
              <div className="font-mono-num text-2xl font-bold text-lime-300">
                {data.hillScore.overall ?? "--"}
              </div>
            </div>
          </div>
          <div className="mt-2 text-xs text-slate-400">
            Hill Strength: <span className="font-mono-num text-slate-200">{data.hillScore.strength ?? "--"}</span> ·
            Hill Endurance: <span className="font-mono-num text-slate-200">{data.hillScore.endurance ?? "--"}</span>
          </div>
        </GlassCard>

        <GlassCard>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
            <Flame className="h-4 w-4 text-amber-400" />
            Lactate Threshold
          </div>
          <div className="font-mono-num text-3xl font-bold text-amber-300">
            {data.lactateThreshold.heartRate ?? "--"} <span className="text-sm font-normal text-slate-400">bpm</span>
          </div>
          <div className="mt-2 text-xs text-slate-400">
            {data.lactateThreshold.date ? `Updated ${data.lactateThreshold.date}` : "Syncing threshold telemetry"}
          </div>
        </GlassCard>
      </div>

      {/* Health & Sleep Reports */}
      {(data.sleepSummary || data.healthSummary) && (
        <div className="grid gap-4 md:grid-cols-2">
          {data.sleepSummary && (
            <GlassCard>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
                <Moon className="h-4 w-4 text-cyan-400" />
                Sleep Coach &amp; Overnight Report
              </div>
              <div className="flex items-baseline gap-4">
                <div className="font-mono-num text-3xl font-bold text-cyan-300">
                  {data.sleepSummary.score ?? "--"} <span className="text-sm font-normal text-slate-400">/ 100</span>
                </div>
                {data.sleepSummary.qualifier && (
                  <StatusBadge tone="cyan">{data.sleepSummary.qualifier}</StatusBadge>
                )}
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-400">
                <div>Duration: <span className="font-mono-num text-slate-200">{data.sleepSummary.durationHours ?? "--"}h</span></div>
                <div>Sleep Need: <span className="font-mono-num text-slate-200">{data.sleepSummary.sleepNeedHours ?? "--"}h</span></div>
                <div>Overnight HRV: <span className="font-mono-num text-emerald-300">{data.sleepSummary.overnightHrv ?? "--"} ms</span></div>
              </div>
              {data.sleepSummary.feedback && (
                <div className="mt-2 text-[11px] text-emerald-300">
                  Coach: {data.sleepSummary.feedback.replace(/_/g, " ")}
                </div>
              )}
            </GlassCard>
          )}

          {data.healthSummary && (
            <GlassCard>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-300">
                <HeartPulse className="h-4 w-4 text-emerald-400" />
                Daily Health &amp; Vitals Summary
              </div>
              <div className="grid grid-cols-2 gap-y-2 gap-x-4 text-xs text-slate-400 sm:grid-cols-4">
                <div>
                  <div className="text-[10px] uppercase">Steps</div>
                  <div className="font-mono-num text-base font-bold text-slate-100">
                    {data.healthSummary.steps?.toLocaleString() ?? "--"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase">Resting HR</div>
                  <div className="font-mono-num text-base font-bold text-emerald-300">
                    {data.healthSummary.restingHr ?? "--"} bpm
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase">Body Battery</div>
                  <div className="font-mono-num text-base font-bold text-cyan-300">
                    {data.healthSummary.bodyBatteryHigh ?? "--"} / {data.healthSummary.bodyBatteryLow ?? "--"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] uppercase">Avg Stress</div>
                  <div className="font-mono-num text-base font-bold text-amber-300">
                    {data.healthSummary.stressAvg ?? "--"}
                  </div>
                </div>
              </div>
              <div className="mt-2 text-[11px] text-slate-400">
                Intensity Minutes: <span className="font-mono-num text-slate-200">{data.healthSummary.moderateMin ?? 0}m</span> mod ·{" "}
                <span className="font-mono-num text-emerald-300">{data.healthSummary.vigorousMin ?? 0}m</span> vig
              </div>
            </GlassCard>
          )}
        </div>
      )}

      {/* Race Predictions */}
      <GlassCard>
        <SectionHeader eyebrow="Garmin Race Predictor" title="Projected Finish Times" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {data.racePredictions.map((rp) => (
            <div key={rp.distance} className="rounded-xl border border-slate-800 bg-slate-950/60 p-3.5">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>{rp.distance}</span>
                <Timer className="h-3.5 w-3.5 text-emerald-400" />
              </div>
              <div className="font-mono-num mt-1 text-2xl font-bold text-slate-100">
                {rp.time ?? "--"}
              </div>
              <div className="font-mono-num mt-0.5 text-[11px] text-emerald-300">
                {rp.pace ?? "--"}
              </div>
            </div>
          ))}
        </div>
      </GlassCard>

      {/* Personal Records & Badges */}
      <div className="grid gap-4 lg:grid-cols-2">
        <GlassCard>
          <SectionHeader eyebrow="Hall of Fame" title="Garmin Personal Records" />
          {data.personalRecords.length === 0 ? (
            <div className="py-4 text-xs text-slate-400">No personal records synced yet.</div>
          ) : (
            <div className="space-y-2">
              {data.personalRecords.map((pr, idx) => (
                <button
                  key={`${pr.activityId ?? idx}-${pr.typeId ?? idx}`}
                  type="button"
                  disabled={!pr.activityId}
                  onClick={() => pr.activityId && onSelectActivity(pr.activityId)}
                  className="flex w-full items-center justify-between rounded-xl border border-slate-800/80 bg-slate-950/60 px-3.5 py-2.5 text-left transition hover:border-emerald-500/40 disabled:cursor-default"
                >
                  <div className="flex items-center gap-2.5">
                    <Trophy className="h-4 w-4 text-amber-400" />
                    <div>
                      <div className="text-xs font-semibold text-slate-100">{pr.activityName}</div>
                      <div className="text-[11px] text-slate-400">{pr.activityType} · {pr.date}</div>
                    </div>
                  </div>
                  <span className="text-[11px] font-semibold text-emerald-300">
                    {pr.activityId ? "Inspect →" : ""}
                  </span>
                </button>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard>
          <SectionHeader eyebrow="Milestones" title="Earned Garmin Badges" />
          {data.badges.length === 0 ? (
            <div className="py-4 text-xs text-slate-400">No earned badges synced yet.</div>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {data.badges.map((b, idx) => (
                <div key={`${b.name}-${idx}`} className="flex items-center gap-2.5 rounded-xl border border-slate-800/80 bg-slate-950/60 px-3 py-2.5">
                  <Award className="h-4 w-4 shrink-0 text-cyan-400" />
                  <div className="min-w-0">
                    <div className="truncate text-xs font-semibold text-slate-100">{b.name}</div>
                    <div className="text-[10px] text-slate-400">{b.earnedDate || b.category}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
