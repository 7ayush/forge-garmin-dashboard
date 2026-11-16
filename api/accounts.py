"""Single-user Garmin session & storage configuration for FORGE Dashboard."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class GarminAccount:
    id: str
    label: str
    email: str
    token_dir: Path
    db_path: Path

    @property
    def is_authenticated(self) -> bool:
        return self.token_dir.exists() and any(
            p.name != "account_meta.json" for p in self.token_dir.glob("*.json")
        )


def _read_saved_email(token_dir: Path) -> str:
    meta_file = token_dir / "account_meta.json"
    if meta_file.exists():
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("email"):
                return str(data["email"])
        except Exception:
            pass
    return os.environ.get("GARMIN_EMAIL", "")


def save_account_meta(token_dir: Path, email: str) -> None:
    token_dir.mkdir(parents=True, exist_ok=True)
    meta_file = token_dir / "account_meta.json"
    meta_file.write_text(json.dumps({"email": email}), encoding="utf-8")
    try:
        os.chmod(meta_file, 0o600)
    except OSError:
        pass


def get_active_account() -> GarminAccount:
    token_dir = Path(
        os.environ.get("GARMIN_TOKEN_DIR", str(Path.home() / ".garminconnect"))
    ).expanduser()
    email = _read_saved_email(token_dir)
    return GarminAccount(
        id="default",
        label=email.split("@")[0] if email else "Garmin Connect",
        email=email,
        token_dir=token_dir,
        db_path=DATA_DIR / "forge.db",
    )


def set_active_account(account_id: str) -> GarminAccount:
    return get_active_account()


def list_accounts() -> List[Dict]:
    acc = get_active_account()
    return [
        {
            "id": acc.id,
            "label": acc.label,
            "email": acc.email,
            "authenticated": acc.is_authenticated,
            "active": True,
        }
    ]
