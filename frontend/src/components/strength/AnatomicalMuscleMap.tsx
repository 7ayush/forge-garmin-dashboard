import React, { useMemo } from "react";
import type { MuscleVolumeEntry } from "../../types/forge";

function colorForVolume(entry: MuscleVolumeEntry | undefined): string {
  if (!entry || entry.fractional_sets === 0) return "#1e293b"; // untrained slate
  const ratio = entry.fractional_sets / Math.max(entry.target_min, 1);
  if (entry.status === "above_target") return "#f59e0b"; // over MRV amber
  if (entry.status === "optimal") return "#10b981"; // optimal emerald
  if (ratio >= 0.5) return "#22d3ee"; // building cyan
  return "#38bdf8"; // started light cyan
}

function strokeForVolume(entry: MuscleVolumeEntry | undefined, selected: boolean): string {
  if (selected) return "#a3e635";
  if (!entry || entry.fractional_sets === 0) return "#334155";
  return "rgba(255,255,255,0.22)";
}

export function AnatomicalMuscleMap({
  muscles,
  selectedMuscle,
  onSelectMuscle,
}: {
  muscles: MuscleVolumeEntry[];
  selectedMuscle: string | null;
  onSelectMuscle: (muscle: string) => void;
}) {
  const byKey = useMemo(() => {
    const map: Record<string, MuscleVolumeEntry> = {};
    for (const m of muscles) map[m.muscle] = m;
    return map;
  }, [muscles]);

  const shapeProps = (muscleKey: string) => {
    const entry = byKey[muscleKey];
    const isSelected = selectedMuscle === muscleKey;
    return {
      fill: colorForVolume(entry),
      stroke: strokeForVolume(entry, isSelected),
      strokeWidth: isSelected ? 2.2 : 1.1,
      className: "cursor-pointer transition-all duration-150 hover:opacity-85",
      onClick: () => onSelectMuscle(muscleKey),
    };
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-800/80 bg-slate-950/60 p-3">
        {/* ANTERIOR (FRONT) */}
        <div className="flex flex-col items-center">
          <span className="font-mono-num mb-1 text-[10px] font-semibold tracking-widest text-slate-400 uppercase">
            Anterior
          </span>
          <svg viewBox="0 0 180 310" className="h-64 w-full max-w-[165px]">
            {/* Head & Neck silhouette */}
            <circle cx="90" cy="24" r="14" fill="#0f172a" stroke="#334155" strokeWidth="1.2" />
            <rect x="83" y="37" width="14" height="10" rx="4" fill="#0f172a" stroke="#334155" strokeWidth="1" />

            {/* Shoulders (Front/Side Delts) */}
            <path d="M52 54 C42 58 40 72 47 82 L60 72 Z" {...shapeProps("shoulders")} />
            <path d="M128 54 C138 58 140 72 133 82 L120 72 Z" {...shapeProps("shoulders")} />
            <path d="M41 64 C35 72 36 88 45 92 L50 82 Z" {...shapeProps("shoulders")} />
            <path d="M139 64 C145 72 144 88 135 92 L130 82 Z" {...shapeProps("shoulders")} />

            {/* Chest */}
            <path d="M58 55 L88 57 L88 89 C73 91 58 84 55 72 Z" {...shapeProps("chest")} />
            <path d="M122 55 L92 57 L92 89 C107 91 122 84 125 72 Z" {...shapeProps("chest")} />

            {/* Biceps + Neutral Forearms */}
            <rect x="37" y="92" width="13" height="36" rx="6" {...shapeProps("biceps")} />
            <rect x="130" y="92" width="13" height="36" rx="6" {...shapeProps("biceps")} />
            <rect x="34" y="131" width="11" height="38" rx="5" fill="#1e293b" stroke="#334155" strokeWidth="1" />
            <rect x="135" y="131" width="11" height="38" rx="5" fill="#1e293b" stroke="#334155" strokeWidth="1" />

            {/* Core / Abs */}
            <rect x="70" y="93" width="40" height="58" rx="8" {...shapeProps("core")} />
            <line x1="90" y1="95" x2="90" y2="148" stroke="#05070b" strokeWidth="1.2" opacity="0.5" />
            <line x1="72" y1="112" x2="108" y2="112" stroke="#05070b" strokeWidth="1" opacity="0.4" />
            <line x1="72" y1="130" x2="108" y2="130" stroke="#05070b" strokeWidth="1" opacity="0.4" />

            {/* Quads */}
            <path d="M62 156 L86 156 L83 228 L59 224 Z" {...shapeProps("quads")} />
            <path d="M118 156 L94 156 L97 228 L121 224 Z" {...shapeProps("quads")} />

            {/* Calves (anterior shin/gastroc silhouette) */}
            <rect x="61" y="236" width="17" height="52" rx="7" {...shapeProps("calves")} />
            <rect x="102" y="236" width="17" height="52" rx="7" {...shapeProps("calves")} />
          </svg>
        </div>

        {/* POSTERIOR (BACK) */}
        <div className="flex flex-col items-center">
          <span className="font-mono-num mb-1 text-[10px] font-semibold tracking-widest text-slate-400 uppercase">
            Posterior
          </span>
          <svg viewBox="0 0 180 310" className="h-64 w-full max-w-[165px]">
            {/* Head */}
            <circle cx="90" cy="24" r="14" fill="#0f172a" stroke="#334155" strokeWidth="1.2" />

            {/* Traps */}
            <path d="M68 48 L90 39 L112 48 L98 76 L82 76 Z" {...shapeProps("traps")} />

            {/* Rear Delts */}
            <path d="M46 56 L66 52 L60 76 L44 74 Z" {...shapeProps("rear_delts")} />
            <path d="M134 56 L114 52 L120 76 L136 74 Z" {...shapeProps("rear_delts")} />

            {/* Back (Mid/Lats) */}
            <path d="M66 56 L114 56 L106 88 L74 88 Z" {...shapeProps("back")} />
            <path d="M56 78 L84 86 L80 124 L59 112 Z" {...shapeProps("back")} />
            <path d="M124 78 L96 86 L100 124 L121 112 Z" {...shapeProps("back")} />

            {/* Lower Back */}
            <rect x="74" y="114" width="32" height="32" rx="6" {...shapeProps("lower_back")} />

            {/* Triceps */}
            <rect x="37" y="84" width="13" height="40" rx="6" {...shapeProps("triceps")} />
            <rect x="130" y="84" width="13" height="40" rx="6" {...shapeProps("triceps")} />

            {/* Glutes */}
            <path d="M61 148 L88 148 L86 182 C70 184 58 174 61 148 Z" {...shapeProps("glutes")} />
            <path d="M119 148 L92 148 L94 182 C110 184 122 174 119 148 Z" {...shapeProps("glutes")} />

            {/* Hamstrings */}
            <path d="M61 186 L86 186 L82 232 L59 230 Z" {...shapeProps("hamstrings")} />
            <path d="M119 186 L94 186 L98 232 L121 230 Z" {...shapeProps("hamstrings")} />

            {/* Calves */}
            <rect x="61" y="238" width="18" height="50" rx="8" {...shapeProps("calves")} />
            <rect x="101" y="238" width="18" height="50" rx="8" {...shapeProps("calves")} />
          </svg>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-slate-800 border border-slate-600" /> 0 sets
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-cyan-400" /> Building
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-emerald-500" /> Optimal (10-20)
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-amber-500" /> Over MRV
          </span>
        </div>
        <span className="font-mono-num text-[10px] text-slate-500">Click muscle region to inspect</span>
      </div>
    </div>
  );
}
