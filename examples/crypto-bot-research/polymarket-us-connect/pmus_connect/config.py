"""Configuration: endpoints and credentials.

Endpoints come from https://docs.polymarket.us/api-reference/introduction.
Credentials are read from the environment, or from a local `.env` file next to the
project. They are never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

GATEWAY_URL = "https://gateway.polymarket.us"   # public market data, no key
API_URL = "https://api.polymarket.us"           # authenticated trading API
WS_URL = "wss://api.polymarket.us"              # /v1/ws/markets and /v1/ws/private

MAX_CLOCK_SKEW_S = 30          # signed timestamps must be within 30 s of server time
PUBLIC_RATE_LIMIT_RPS = 25     # retail API general limit (docs: rate-limits)


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Credentials:
    key_id: str
    secret_key: str

    @property
    def redacted_key_id(self) -> str:
        k = self.key_id
        return f"{k[:4]}…{k[-4:]}" if len(k) > 8 else "****"


def load_credentials(env_file: Path | None = None) -> Credentials | None:
    _load_dotenv(env_file or Path(__file__).resolve().parent.parent / ".env")
    key_id = os.environ.get("POLYMARKET_KEY_ID", "").strip()
    secret = os.environ.get("POLYMARKET_SECRET_KEY", "").strip()
    if not key_id or not secret:
        return None
    return Credentials(key_id=key_id, secret_key=secret)
