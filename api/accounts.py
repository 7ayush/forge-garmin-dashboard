"""Multi-account registry for FORGE Garmin Dashboard.

Each account has its own isolated SQLite database and Garmin OAuth token directory.
Selectable via environment variables (`GARMIN_ACTIVE_ACCOUNT`, `GARMIN_ACCOUNT_1_EMAIL`,
`GARMIN_ACCOUNT_2_EMAIL`, etc.) or at runtime via `/api/accounts/select`.
"""

from __future__ import annotations

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
        return self.token_dir.exists() and any(self.token_dir.glob("*.json"))


def _build_accounts() -> Dict[str, GarminAccount]:
    return {
        "ayush": GarminAccount(
            id="ayush",
            label=os.environ.get("GARMIN_ACCOUNT_1_LABEL", "Ayush"),
            email=os.environ.get("GARMIN_ACCOUNT_1_EMAIL", "ayush.kaushik711@gmail.com"),
            token_dir=Path(
                os.environ.get("GARMIN_ACCOUNT_1_TOKEN_DIR", str(Path.home() / ".garminconnect"))
            ).expanduser(),
            db_path=DATA_DIR / "forge.db",
        ),
        "praveen": GarminAccount(
            id="praveen",
            label=os.environ.get("GARMIN_ACCOUNT_2_LABEL", "Praveen"),
            email=os.environ.get("GARMIN_ACCOUNT_2_EMAIL", "praveen.kaushik111@gmail.com"),
            token_dir=Path(
                os.environ.get("GARMIN_ACCOUNT_2_TOKEN_DIR", str(Path.home() / ".garminconnect_praveen"))
            ).expanduser(),
            db_path=DATA_DIR / "forge_praveen.db",
        ),
    }


ACCOUNTS: Dict[str, GarminAccount] = _build_accounts()


def _normalize_account_id(raw: Optional[str]) -> str:
    if not raw:
        return "ayush"
    val = raw.strip().lower()
    if val in ACCOUNTS:
        return val
    if val in ("1", "account1", "account_1"):
        return "ayush"
    if val in ("2", "account2", "account_2"):
        return "praveen"
    for acc_id, acc in ACCOUNTS.items():
        if acc.email.lower() == val or acc.label.lower() == val:
            return acc_id
    return "ayush"


_ACTIVE_ACCOUNT_ID: str = _normalize_account_id(os.environ.get("GARMIN_ACTIVE_ACCOUNT", "ayush"))


def get_active_account() -> GarminAccount:
    return ACCOUNTS[_ACTIVE_ACCOUNT_ID]


def set_active_account(account_id: str) -> GarminAccount:
    global _ACTIVE_ACCOUNT_ID
    norm = _normalize_account_id(account_id)
    _ACTIVE_ACCOUNT_ID = norm
    return ACCOUNTS[norm]


def list_accounts() -> List[dict]:
    active = get_active_account()
    return [
        {
            "id": acc.id,
            "label": acc.label,
            "email": acc.email,
            "authenticated": acc.is_authenticated,
            "active": acc.id == active.id,
        }
        for acc in ACCOUNTS.values()
    ]
