"""Clés API lues dans l'environnement ou dans ouibet/.env (jamais commité)."""
import os
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"


def _load():
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load()
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ODDS_API_MAX_SPORTS = int(os.environ.get("ODDS_API_MAX_SPORTS", "20"))
