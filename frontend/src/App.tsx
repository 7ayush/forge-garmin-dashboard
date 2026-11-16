import React, { useCallback, useEffect, useState } from "react";
import { forgeApi } from "./api/client";
import { ActivityDetailModal } from "./components/layout/ActivityDetailModal";
import { AppShell } from "./components/layout/AppShell";
import { QuickLogModal } from "./components/layout/QuickLogModal";
import { BodyPage } from "./pages/BodyPage";
import { EnginePage } from "./pages/EnginePage";
import { FuelPage } from "./pages/FuelPage";
import { ProgressPage } from "./pages/ProgressPage";
import { TipsPage } from "./pages/TipsPage";
import { RecoveryPage } from "./pages/RecoveryPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StrengthPage } from "./pages/StrengthPage";
import { TodayPage } from "./pages/TodayPage";
import type { PageRoute, SyncState } from "./types/forge";

const VALID_ROUTES = new Set<PageRoute>([
  "today",
  "strength",
  "engine",
  "recovery",
  "body",
  "fuel",
  "progress",
  "tips",
  "settings",
]);

function readRouteFromLocation(): PageRoute {
  const path = window.location.pathname.replace(/^\/+|\/+$/g, "").toLowerCase();
  if (path === "" || path === "today") return "today";
  if (VALID_ROUTES.has(path as PageRoute)) return path as PageRoute;
  return "today";
}

export function App() {
  const [route, setRoute] = useState<PageRoute>(readRouteFromLocation);
  const [refreshTick, setRefreshTick] = useState(0);
  const [quickLogOpen, setQuickLogOpen] = useState(false);
  const [activeActivityId, setActiveActivityId] = useState<number | null>(null);
  const [syncingNow, setSyncingNow] = useState(false);
  const [syncState, setSyncState] = useState<SyncState | null>(null);
  const [athleteName, setAthleteName] = useState<string>("Ayush Kaushik");
  const [deviceName, setDeviceName] = useState<string>("Forerunner 965");
  const [latestWeight, setLatestWeight] = useState<number>(73.2);

  const navigate = useCallback((nextRoute: PageRoute) => {
    setRoute(nextRoute);
    const targetPath = nextRoute === "today" ? "/" : `/${nextRoute}`;
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, "", targetPath);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  useEffect(() => {
    const onPop = () => setRoute(readRouteFromLocation());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    forgeApi
      .getToday()
      .then((res) => {
        setSyncState(res.sync);
        setAthleteName(res.athlete.name);
        setDeviceName(res.athlete.device);
        if (res.athlete.weight_kg) setLatestWeight(res.athlete.weight_kg);
      })
      .catch(() => {});
  }, [refreshTick]);

  const triggerSync = async () => {
    setSyncingNow(true);
    try {
      const res = await forgeApi.syncNow(7);
      setSyncState(res.sync);
      setRefreshTick((t) => t + 1);
    } catch {
      // keep previous state cleanly
    } finally {
      setSyncingNow(false);
    }
  };

  const bumpRefresh = () => setRefreshTick((t) => t + 1);

  return (
    <AppShell
      activeRoute={route}
      onNavigate={navigate}
      athleteName={athleteName}
      deviceName={deviceName}
      syncState={syncState}
      syncingNow={syncingNow}
      onSyncNow={() => void triggerSync()}
      onOpenQuickLog={() => setQuickLogOpen(true)}
      onAccountChange={bumpRefresh}
    >
      {route === "today" && (
        <TodayPage
          refreshTick={refreshTick}
          onNavigate={navigate}
          onSelectActivity={setActiveActivityId}
          onOpenQuickLog={() => setQuickLogOpen(true)}
        />
      )}
      {route === "strength" && (
        <StrengthPage
          refreshTick={refreshTick}
          onSelectActivity={setActiveActivityId}
          onDataChanged={bumpRefresh}
        />
      )}
      {route === "engine" && (
        <EnginePage refreshTick={refreshTick} onSelectActivity={setActiveActivityId} />
      )}
      {route === "recovery" && <RecoveryPage refreshTick={refreshTick} />}
      {route === "body" && <BodyPage refreshTick={refreshTick} onDataChanged={bumpRefresh} />}
      {route === "fuel" && <FuelPage refreshTick={refreshTick} onDataChanged={bumpRefresh} />}
      {route === "progress" && <ProgressPage refreshTick={refreshTick} />}
      {route === "tips" && <TipsPage refreshTick={refreshTick} onSelectActivity={setActiveActivityId} />}
      {route === "settings" && <SettingsPage refreshTick={refreshTick} onDataChanged={bumpRefresh} />}

      <QuickLogModal
        open={quickLogOpen}
        defaultWeight={latestWeight}
        onClose={() => setQuickLogOpen(false)}
        onSaved={bumpRefresh}
      />
      <ActivityDetailModal
        activityId={activeActivityId}
        onClose={() => setActiveActivityId(null)}
        onEffortUpdated={bumpRefresh}
      />
    </AppShell>
  );
}

export default App;
