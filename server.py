"""FORGE Garmin Performance Dashboard server (Starlette + SQLite WAL + React SPA)."""

from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
for p in (str(ROOT_DIR), str(SRC_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dashboard.api.db import DEFAULT_DB_PATH, ensure_schema, get_conn
from dashboard.api.routes import build_api_routes
from dashboard.api.garmin_sync import trigger_background_sync

HOST = os.environ.get("FORGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("FORGE_PORT", "8765"))
SYNC_INTERVAL_S = 30 * 60


def _start_sync_loop(stop_event: threading.Event, db_path: Path) -> threading.Thread:
    def _loop():
        # Initial warmup: full backfill on empty DB, else fast incremental sync
        try:
            with get_conn(db_path) as conn:
                act_count = conn.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"]
            if act_count == 0:
                trigger_background_sync(scope="backfill", days=30, activity_limit=150, db_path=db_path)
            else:
                trigger_background_sync(scope="incremental", days=7, activity_limit=40, db_path=db_path)
        except Exception:
            pass

        while not stop_event.wait(SYNC_INTERVAL_S):
            try:
                trigger_background_sync(scope="incremental", days=7, activity_limit=40, db_path=db_path)
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True, name="forge-sync-scheduler")
    t.start()
    return t


def create_app(db_path: Path = DEFAULT_DB_PATH, start_scheduler: bool = True) -> Starlette:
    """Create the FORGE Starlette application."""
    ensure_schema(db_path)
    stop_event = threading.Event()

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        if start_scheduler:
            _start_sync_loop(stop_event, db_path)
        yield
        stop_event.set()

    app = Starlette(routes=build_api_routes(db_path=None), lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://127.0.0.1:8765"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


app = create_app()


def main() -> None:
    print(f"\n  FORGE // Garmin Performance Dashboard")
    print(f"  Listening on http://{HOST}:{PORT}\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
