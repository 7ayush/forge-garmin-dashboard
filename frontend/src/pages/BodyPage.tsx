import React, { useState } from "react";
import { Camera, Ruler, Trash2, Upload } from "lucide-react";
import {
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
  SectionHeader,
  StatusBadge,
} from "../components/ui/Primitives";
import { useAsyncData } from "../hooks/useAsyncData";

export function BodyPage({
  refreshTick,
  onDataChanged,
}: {
  refreshTick: number;
  onDataChanged: () => void;
}) {
  const { data, setData, loading, error, reload } = useAsyncData(() => forgeApi.getBody(), [refreshTick]);

  const [weightKg, setWeightKg] = useState("73.2");
  const [bodyFatPct, setBodyFatPct] = useState("");
  const [weighSync, setWeighSync] = useState(true);
  const [waist, setWaist] = useState("");
  const [chest, setChest] = useState("");
  const [arm, setArm] = useState("");
  const [thigh, setThigh] = useState("");
  const [shoulder, setShoulder] = useState("");
  const [neck, setNeck] = useState("");
  const [pose, setPose] = useState<"front" | "side" | "back">("front");
  const [photoNotes, setPhotoNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  if (loading && !data) return <LoadingState label="Loading Physique & Recomp Telemetry..." />;
  if (error && !data) return <ErrorBanner message={error} onRetry={() => void reload()} />;
  if (!data) return null;

  const submitWeight = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const updated = await forgeApi.postWeighIn({
        weight_kg: Number(weightKg),
        body_fat_pct: bodyFatPct ? Number(bodyFatPct) : null,
        sync_to_garmin: weighSync,
      });
      setData(updated);
      onDataChanged();
      setNotice(
        updated.garmin_synced
          ? `Weigh-in (${updated.latest_weight_kg} kg) saved & pushed to Garmin Connect.`
          : `Weigh-in (${updated.latest_weight_kg} kg) saved locally.`
      );
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to save weigh-in");
    } finally {
      setBusy(false);
    }
  };

  const submitTape = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const updated = await forgeApi.postTape({
        waist_cm: waist || undefined,
        chest_cm: chest || undefined,
        arm_cm: arm || undefined,
        thigh_cm: thigh || undefined,
        shoulder_cm: shoulder || undefined,
        neck_cm: neck || undefined,
      });
      setData(updated);
      onDataChanged();
      setNotice("Saved circumference tape measurements & updated Navy BF% / ratios.");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to save tape");
    } finally {
      setBusy(false);
    }
  };

  const handlePhotoUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formEl = e.currentTarget;
    const fileInput = formEl.elements.namedItem("photoFile") as HTMLInputElement | null;
    const file = fileInput?.files?.[0];
    if (!file) {
      setNotice("Choose a JPG, PNG, or WEBP file first.");
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("pose", pose);
      if (photoNotes) fd.append("notes", photoNotes);
      const updated = await forgeApi.uploadPhoto(fd);
      setData(updated);
      formEl.reset();
      setPhotoNotes("");
      setNotice("Progress photo stored locally.");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <KpiTile
          label="EWMA Trend Weight"
          value={data.trend_weight_kg}
          unit="kg"
          subtext={`Latest scale: ${data.latest_weight_kg} kg`}
          tone="emerald"
        />
        <KpiTile
          label="14D Gain Rate"
          value={data.rate_pct_month !== null ? `${data.rate_pct_month}%` : "--"}
          unit="/mo"
          subtext={
            data.rate_kg_week !== null
              ? `${data.rate_kg_week} kg/wk vs ${data.target_gain_pct_month}% target`
              : `${data.weigh_ins_14d}/4 weigh-ins in 14d`
          }
          tone={data.rate_pct_month !== null ? "lime" : "neutral"}
        />
        <KpiTile
          label="Normalized FFMI"
          value={data.nffmi ?? "--"}
          subtext={data.ffmi ? `Raw FFMI ${data.ffmi} · FFM ${data.ffm_kg}kg` : "Log BF% or waist+neck"}
          tone="cyan"
        />
        <KpiTile
          label="Body Fat %"
          value={data.body_fat_pct ?? "--"}
          unit="%"
          subtext={data.body_fat_source || "Pending tape/scale"}
          tone="amber"
        />
        <KpiTile
          label="Waist : Arm"
          value={data.waist_arm_ratio ?? "--"}
          subtext={`Waist:Chest ${data.waist_chest_ratio ?? "--"}`}
        />
        <KpiTile
          label="Height / Gain Goal"
          value={`${data.height_cm}cm`}
          subtext={
            data.rate_pct_month == null
              ? `Target +${data.target_gain_pct_month}%/mo · ${data.weight_series.length} log(s)`
              : data.rate_pct_month > data.target_gain_pct_month * 1.4
              ? "Above lean-bulk rate"
              : "On lean-bulk track"
          }
        />
      </div>

      {data.weigh_ins_14d < 4 && (
        <InfoCallout tone="cyan">
          Need {4 - data.weigh_ins_14d} more weigh-in(s) over the trailing 14 days to compute reliable EWMA
          lean-gain velocity. Log morning weights before food/water.
        </InfoCallout>
      )}
      {notice && <InfoCallout tone="emerald">{notice}</InfoCallout>}

      {/* Weight Trend Chart + Morning Weigh-In Form */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-8">
          <SectionHeader
            eyebrow="Scale Smoothing (EWMA alpha = 0.25)"
            title="Weight & Trend Trajectory"
            subtitle="Separates true tissue gain from daily hydration/glycogen noise"
          />
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.weight_series}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.1)" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                <YAxis stroke="#64748b" fontSize={10} domain={["auto", "auto"]} />
                <Tooltip contentStyle={CHART_TOOLTIP_STYLE} />
                <Line type="monotone" dataKey="weight_kg" name="Raw Scale (kg)" stroke="#64748b" strokeDasharray="4 4" dot={{ r: 3 }} />
                <Line type="monotone" dataKey="trend_kg" name="EWMA Trend (kg)" stroke="#10b981" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </GlassCard>

        <GlassCard className="lg:col-span-4">
          <SectionHeader eyebrow="Scale Entry" title="Log Weigh-In" />
          <form onSubmit={submitWeight} className="space-y-3 text-xs">
            <label className="block">
              <span className="text-slate-400">Weight (kg)</span>
              <input
                type="number"
                step="0.1"
                required
                value={weightKg}
                onChange={(e) => setWeightKg(e.target.value)}
                className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100"
              />
            </label>
            <label className="block">
              <span className="text-slate-400">Body Fat % (optional)</span>
              <input
                type="number"
                step="0.1"
                placeholder="Overrides Navy estimate"
                value={bodyFatPct}
                onChange={(e) => setBodyFatPct(e.target.value)}
                className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-2 text-sm text-slate-100"
              />
            </label>
            <label className="flex items-center gap-2 text-slate-300">
              <input
                type="checkbox"
                checked={weighSync}
                onChange={(e) => setWeighSync(e.target.checked)}
                className="accent-emerald-400"
              />
              Sync weigh-in to Garmin Connect
            </label>
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-xl bg-emerald-500 px-4 py-2.5 font-bold text-slate-950 hover:bg-emerald-400 disabled:opacity-50"
            >
              Save Weigh-In
            </button>
          </form>
        </GlassCard>
      </div>

      {/* Tape Measurements + Progress Photo Vault */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-12">
        <GlassCard className="lg:col-span-5">
          <SectionHeader
            eyebrow="Recomp Proportions"
            title="Circumference Tape (cm)"
            subtitle="Waist + Neck unlocks US Navy Body Fat % & FFMI automatically"
          />
          <form onSubmit={submitTape} className="grid grid-cols-2 gap-3 text-xs">
            {[
              { label: "Waist (cm)", val: waist, set: setWaist, cur: data.latest_tape.waist_cm },
              { label: "Neck (cm)", val: neck, set: setNeck, cur: data.latest_tape.neck_cm },
              { label: "Chest (cm)", val: chest, set: setChest, cur: data.latest_tape.chest_cm },
              { label: "Arm (cm)", val: arm, set: setArm, cur: data.latest_tape.arm_cm },
              { label: "Shoulder (cm)", val: shoulder, set: setShoulder, cur: data.latest_tape.shoulder_cm },
              { label: "Thigh (cm)", val: thigh, set: setThigh, cur: data.latest_tape.thigh_cm },
            ].map((f) => (
              <label key={f.label} className="block">
                <span className="flex items-center justify-between text-slate-400">
                  <span>{f.label}</span>
                  {f.cur && <span className="font-mono-num text-[10px] text-emerald-300">last: {f.cur}</span>}
                </span>
                <input
                  type="number"
                  step="0.1"
                  placeholder={f.cur ? String(f.cur) : "--"}
                  value={f.val}
                  onChange={(e) => f.set(e.target.value)}
                  className="font-mono-num mt-1 w-full rounded-xl border border-slate-700 bg-slate-950/80 px-3 py-1.5 text-sm text-slate-100"
                />
              </label>
            ))}
            <button
              type="submit"
              disabled={busy}
              className="col-span-2 mt-1 inline-flex items-center justify-center gap-1.5 rounded-xl border border-emerald-400/40 bg-emerald-500/15 py-2 font-semibold text-emerald-200 hover:bg-emerald-500/25"
            >
              <Ruler className="h-3.5 w-3.5" /> Save Tape Measurements
            </button>
          </form>
        </GlassCard>

        <GlassCard className="lg:col-span-7">
          <SectionHeader
            eyebrow="Private Local Vault"
            title={`Progress Photos (${data.photos.length})`}
            subtitle="Stored offline in dashboard/data/photos/ — never leaves your Mac"
          />
          <form onSubmit={handlePhotoUpload} className="mb-4 flex flex-wrap items-end gap-2.5 text-xs">
            <label className="block">
              <span className="text-slate-400">Pose</span>
              <select
                value={pose}
                onChange={(e) => setPose(e.target.value as "front" | "side" | "back")}
                className="mt-1 block rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-2 text-slate-100"
              >
                <option value="front">Front</option>
                <option value="side">Side</option>
                <option value="back">Back</option>
              </select>
            </label>
            <label className="min-w-[160px] flex-1">
              <span className="text-slate-400">Image (.jpg / .png / .webp)</span>
              <input
                name="photoFile"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="mt-1 block w-full text-xs text-slate-300 file:mr-2 file:rounded-lg file:border-0 file:bg-slate-800 file:px-2.5 file:py-1.5 file:text-xs file:font-semibold file:text-emerald-300"
              />
            </label>
            <label className="min-w-[140px]">
              <span className="text-slate-400">Notes</span>
              <input
                value={photoNotes}
                onChange={(e) => setPhotoNotes(e.target.value)}
                placeholder="Morning fasted..."
                className="mt-1 block w-full rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-slate-100"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center gap-1.5 rounded-xl bg-emerald-500 px-3.5 py-2 font-bold text-slate-950 hover:bg-emerald-400"
            >
              <Upload className="h-3.5 w-3.5" /> Upload
            </button>
          </form>

          {data.photos.length === 0 ? (
            <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-slate-800 py-8 text-xs text-slate-500">
              <Camera className="h-4 w-4" /> No check-in photos yet.
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {data.photos.map((p) => (
                <div key={p.id} className="group relative overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
                  <img src={p.url} alt={`${p.pose} check-in`} className="h-36 w-full object-cover" />
                  <div className="flex items-center justify-between px-2.5 py-1.5 text-[11px]">
                    <div>
                      <StatusBadge tone="cyan">{p.pose}</StatusBadge>
                      <span className="font-mono-num ml-1.5 text-slate-400">{p.calendar_date}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => void forgeApi.deletePhoto(p.id).then(setData)}
                      className="text-slate-500 hover:text-rose-400"
                      aria-label="Delete photo"
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
    </div>
  );
}
