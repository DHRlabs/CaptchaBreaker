"""Configuration for CaptchaBreaker.

All network-provider settings come from environment variables or a `.env` file,
so no credentials are ever hard-coded. The local OCR path needs nothing at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:  # optional convenience
    pass


# ---------------------------------------------------------------------------
# Environment / .env keys
# ---------------------------------------------------------------------------
# CaptchaBreaker can talk to any provider that implements the standard
# "create task with in.php/out.php + JSON" protocol — that includes
# 2Captcha, CapSolver, CapMonster, RuCaptcha, and most self-hosted proxies.
#
#   CAPTCHABREAKER_PROVIDER   : which provider host to use (default: CapSolver)
#   CAPTCHABREAKER_API_KEY    : your provider API key
#   CAPTCHABREAKER_HOST       : full API host override, e.g. https://api.2captcha.com
#   CAPTCHABREAKER_TIMEOUT    : max seconds to poll for a network solve (default 120)
#   CAPTCHABREAKER_PORT       : port for the local HTTP server (default 8977)


DEFAULT_HTTP_PORT = 8977


@dataclass
class Settings:
    provider: str = "capsolver"
    api_key: str = ""
    host: Optional[str] = None
    timeout: int = 120
    port: int = DEFAULT_HTTP_PORT
    debug: bool = False

    @property
    def network_enabled(self) -> bool:
        return bool(self.api_key)

    @property
    def effective_host(self) -> str:
        if self.host:
            return self.host.rstrip("/")
        return _DEFAULT_HOSTS.get(self.provider, _DEFAULT_HOSTS["capsolver"])


_DEFAULT_HOSTS = {
    "capsolver": "https://api.capsolver.com",
    "2captcha": "https://api.2captcha.com",
    "capmonster": "https://api.capmonster.cloud",
    "rucaptcha": "https://rucaptcha.com",
}


def _load_settings() -> Settings:
    return Settings(
        provider=os.getenv("CAPTCHABREAKER_PROVIDER", "capsolver").lower(),
        api_key=os.getenv("CAPTCHABREAKER_API_KEY", "").strip(),
        host=os.getenv("CAPTCHABREAKER_HOST") or None,
        timeout=int(os.getenv("CAPTCHABREAKER_TIMEOUT", "120")),
        port=int(os.getenv("CAPTCHABREAKER_PORT", str(DEFAULT_HTTP_PORT))),
        debug=os.getenv("CAPTCHABREAKER_DEBUG", "").lower() in {"1", "true", "yes"},
    )


# Global settings object. Overridable for tests.
settings = _load_settings()


def get_provider_config() -> dict:
    """Return a plain dict of provider config (safe for logging/secrets display)."""
    return {
        "provider": settings.provider,
        "host": settings.effective_host,
        "network_enabled": settings.network_enabled,
        "network_provider": settings.provider if settings.network_enabled else None,
    }


def is_network_enabled() -> bool:
    return settings.network_enabled
