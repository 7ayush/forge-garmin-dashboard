import React from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";
import type { SeverityTone } from "../../types/forge";

const TONE_MAP: Record<SeverityTone, string> = {
  emerald: "bg-emerald-500/12 text-emerald-300 border-emerald-500/30",
  lime: "bg-lime-400/12 text-lime-300 border-lime-400/30",
  cyan: "bg-cyan-400/12 text-cyan-300 border-cyan-400/30",
  amber: "bg-amber-400/12 text-amber-300 border-amber-400/35",
  crimson: "bg-rose-500/15 text-rose-300 border-rose-500/35",
  neutral: "bg-slate-800/70 text-slate-300 border-slate-700/60",
};

export function StatusBadge({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: SeverityTone;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide ${TONE_MAP[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function GlassCard({
  children,
  className = "",
  interactive = false,
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  interactive?: boolean;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={`telemetry-card rounded-2xl p-4 sm:p-5 ${
        interactive ? "telemetry-card-interactive cursor-pointer" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  subtitle,
  right,
}: {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div>
        {eyebrow && (
          <div className="font-mono-num text-[10px] font-semibold tracking-[0.18em] text-emerald-400/90 uppercase">
            {eyebrow}
          </div>
        )}
        <h2 className="font-display text-lg font-bold tracking-tight text-slate-100 sm:text-xl">
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

export function KpiTile({
  label,
  value,
  unit,
  subtext,
  tone = "neutral",
  sparkline,
  onClick,
}: {
  label: string;
  value: string | number | null | undefined;
  unit?: string;
  subtext?: string;
  tone?: SeverityTone;
  sparkline?: (number | null)[];
  onClick?: () => void;
}) {
  const accentText =
    tone === "emerald"
      ? "text-emerald-300"
      : tone === "lime"
      ? "text-lime-300"
      : tone === "cyan"
      ? "text-cyan-300"
      : tone === "amber"
      ? "text-amber-300"
      : tone === "crimson"
      ? "text-rose-300"
      : "text-slate-100";

  return (
    <GlassCard interactive={Boolean(onClick)} onClick={onClick} className="flex flex-col justify-between gap-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold tracking-wider text-slate-400 uppercase">{label}</span>
        {sparkline && <MiniSparkline values={sparkline} tone={tone} />}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className={`font-mono-num text-2xl font-bold tracking-tight ${accentText}`}>
          {value ?? "--"}
        </span>
        {unit && <span className="font-mono-num text-xs text-slate-400">{unit}</span>}
      </div>
      {subtext && <div className="text-[11px] leading-snug text-slate-400">{subtext}</div>}
    </GlassCard>
  );
}

export function MiniSparkline({
  values,
  tone = "emerald",
}: {
  values: (number | null)[];
  tone?: SeverityTone;
}) {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (nums.length < 2) return null;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const w = 64;
  const h = 20;
  const pts = nums
    .map((v, i) => {
      const x = (i / Math.max(nums.length - 1, 1)) * w;
      const y = h - ((v - min) / span) * (h - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const stroke =
    tone === "amber"
      ? "#f59e0b"
      : tone === "crimson"
      ? "#ef4444"
      : tone === "cyan"
      ? "#22d3ee"
      : tone === "lime"
      ? "#a3e635"
      : "#10b981";

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="overflow-visible opacity-85" aria-hidden="true">
      <polyline fill="none" stroke={stroke} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}

export function ProgressBar({
  value,
  max = 100,
  tone = "emerald",
  heightClass = "h-2",
}: {
  value: number;
  max?: number;
  tone?: SeverityTone;
  heightClass?: string;
}) {
  const pct = Math.max(0, Math.min(100, (value / Math.max(max, 1)) * 100));
  const fill =
    tone === "crimson"
      ? "bg-rose-500"
      : tone === "amber"
      ? "bg-amber-400"
      : tone === "cyan"
      ? "bg-cyan-400"
      : tone === "lime"
      ? "bg-lime-400"
      : "bg-emerald-400";

  return (
    <div className={`w-full overflow-hidden rounded-full bg-slate-800/90 ${heightClass}`}>
      <div className={`h-full rounded-full transition-all duration-300 ${fill}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function LoadingState({ label = "Loading bio-telemetry..." }: { label?: string }) {
  return (
    <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 text-slate-400">
      <Loader2 className="h-6 w-6 animate-spin text-emerald-400" />
      <span className="font-mono-num text-xs tracking-wider uppercase">{label}</span>
    </div>
  );
}

export function ErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/35 bg-rose-500/10 px-4 py-3 text-xs text-rose-200">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
        <span>{message}</span>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg border border-rose-400/40 bg-rose-500/15 px-3 py-1 font-medium hover:bg-rose-500/25"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function InfoCallout({
  tone = "cyan",
  children,
}: {
  tone?: "cyan" | "amber" | "emerald";
  children: React.ReactNode;
}) {
  const icon =
    tone === "amber" ? (
      <AlertTriangle className="h-4 w-4 shrink-0 text-amber-300" />
    ) : tone === "emerald" ? (
      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" />
    ) : (
      <Info className="h-4 w-4 shrink-0 text-cyan-300" />
    );
  const style =
    tone === "amber"
      ? "border-amber-500/30 bg-amber-500/10 text-amber-100"
      : tone === "emerald"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
      : "border-cyan-500/30 bg-cyan-500/10 text-cyan-100";

  return <div className={`flex items-start gap-2.5 rounded-xl border px-3.5 py-2.5 text-xs ${style}`}>{icon}<div>{children}</div></div>;
}

export const CHART_TOOLTIP_STYLE: React.CSSProperties = {
  backgroundColor: "#0a0f18",
  borderColor: "rgba(148, 163, 184, 0.22)",
  borderRadius: "10px",
  fontSize: "12px",
  color: "#e6edf5",
};
