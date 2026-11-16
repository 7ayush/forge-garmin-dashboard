import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapPin, Maximize2, Minimize2 } from "lucide-react";
import type { ActivityRoute } from "../../types/forge";

type MapViewMode = "dark" | "street" | "satellite" | "topo";

const MAP_VIEWS: Record<
  MapViewMode,
  { label: string; url: string; className?: string; maxZoom: number }
> = {
  dark: {
    label: "Dark",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    className: "brightness-90 contrast-110 invert hue-rotate-180",
    maxZoom: 19,
  },
  street: {
    label: "Street",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    maxZoom: 19,
  },
  satellite: {
    label: "Satellite",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    maxZoom: 18,
  },
  topo: {
    label: "Topo",
    url: "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    maxZoom: 17,
  },
};

interface RouteMapProps {
  route: ActivityRoute;
  heightClass?: string;
  title?: string;
}

export function RouteMap({
  route,
  heightClass = "h-[240px]",
  title = "GPS Route",
}: RouteMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const polylineRef = useRef<L.Polyline | null>(null);

  const [viewMode, setViewMode] = useState<MapViewMode>("dark");
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || !route.hasRoute || route.points.length === 0) return;

    const map = L.map(el, {
      zoomControl: true,
      attributionControl: false,
      scrollWheelZoom: isFullscreen,
    });
    mapRef.current = map;

    const cfg = MAP_VIEWS[viewMode];
    tileLayerRef.current = L.tileLayer(cfg.url, {
      maxZoom: cfg.maxZoom,
      className: cfg.className,
    }).addTo(map);

    const latLngs: L.LatLngExpression[] = route.points.map(([lat, lon]) => [
      lat,
      lon,
    ]);

    const polyline = L.polyline(latLngs, {
      color: "#10b981",
      weight: 3.5,
      opacity: 0.92,
      lineJoin: "round",
      lineCap: "round",
    }).addTo(map);
    polylineRef.current = polyline;

    const start = route.startPoint ?? [route.points[0][0], route.points[0][1]];
    const end =
      route.endPoint ??
      [
        route.points[route.points.length - 1][0],
        route.points[route.points.length - 1][1],
      ];

    L.circleMarker(start, {
      radius: 6,
      color: "#ecfdf5",
      weight: 2,
      fillColor: "#10b981",
      fillOpacity: 1,
    })
      .bindTooltip("Start", { direction: "top" })
      .addTo(map);

    L.circleMarker(end, {
      radius: 6,
      color: "#fff1f2",
      weight: 2,
      fillColor: "#f43f5e",
      fillOpacity: 1,
    })
      .bindTooltip("Finish", { direction: "top" })
      .addTo(map);

    const bounds = polyline.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [24, 24] });
    }

    const timer = window.setTimeout(() => {
      map.invalidateSize();
    }, 120);

    return () => {
      window.clearTimeout(timer);
      map.remove();
      mapRef.current = null;
      tileLayerRef.current = null;
      polylineRef.current = null;
    };
  }, [route, isFullscreen]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tileLayerRef.current) {
      map.removeLayer(tileLayerRef.current);
    }
    const cfg = MAP_VIEWS[viewMode];
    tileLayerRef.current = L.tileLayer(cfg.url, {
      maxZoom: cfg.maxZoom,
      className: cfg.className,
    }).addTo(map);
  }, [viewMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (isFullscreen) {
      map.scrollWheelZoom.enable();
    } else {
      map.scrollWheelZoom.disable();
    }
    const timer = window.setTimeout(() => {
      map.invalidateSize();
      const bounds = polylineRef.current?.getBounds();
      if (bounds && bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24] });
      }
    }, 100);
    return () => window.clearTimeout(timer);
  }, [isFullscreen]);

  useEffect(() => {
    if (!isFullscreen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isFullscreen]);

  if (!route.hasRoute || route.points.length === 0) {
    return null;
  }

  const content = (
    <div
      className={
        isFullscreen
          ? "fixed inset-0 z-[9999] flex flex-col bg-[#05070b]"
          : "rounded-xl border border-white/10 bg-[#05070b] overflow-hidden"
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 border-b border-white/10 bg-white/[0.02]">
        <div className="flex items-center gap-2">
          <MapPin className="h-3.5 w-3.5 text-emerald-400" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-300">
            {title}
          </span>
          {route.locationName && (
            <span className="text-[11px] text-zinc-400">
              • {route.locationName}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-lg border border-white/10 bg-black/40 p-0.5">
            {(Object.keys(MAP_VIEWS) as MapViewMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`rounded-md px-2 py-0.5 text-[10px] font-semibold transition ${
                  viewMode === mode
                    ? "bg-emerald-500/20 text-emerald-300"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {MAP_VIEWS[mode].label}
              </button>
            ))}
          </div>

          <div className="hidden sm:flex items-center gap-2.5 text-[10px] text-zinc-400">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
              Start
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-rose-500" />
              Finish
            </span>
          </div>

          <button
            type="button"
            onClick={() => setIsFullscreen((f) => !f)}
            title={isFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen map"}
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] font-semibold text-zinc-300 transition hover:border-emerald-500/40 hover:text-emerald-300"
          >
            {isFullscreen ? (
              <>
                <Minimize2 className="h-3 w-3" />
                Exit
              </>
            ) : (
              <>
                <Maximize2 className="h-3 w-3" />
                Full
              </>
            )}
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className={isFullscreen ? "w-full flex-1 min-h-0" : `w-full ${heightClass}`}
      />
    </div>
  );

  return isFullscreen ? createPortal(content, document.body) : content;
}
