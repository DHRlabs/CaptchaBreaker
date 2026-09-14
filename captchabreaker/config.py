"""Configuration for CaptchaBreaker.

The default OCR and HumanPass paths run locally without keys. HumanPass can
optionally use an explicitly enabled external vision backend.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except ImportError:  # optional convenience
    pass


DEFAULT_HTTP_PORT = 8977
DEFAULT_HTTP_HOST = "127.0.0.1"


@dataclass
class Settings:
    port: int = DEFAULT_HTTP_PORT
    debug: bool = False
    host: str = DEFAULT_HTTP_HOST


def _load_settings() -> Settings:
    return Settings(
        port=int(os.getenv("CAPTCHABREAKER_PORT", str(DEFAULT_HTTP_PORT))),
        host=os.getenv("CAPTCHABREAKER_HOST", DEFAULT_HTTP_HOST),
        debug=os.getenv("CAPTCHABREAKER_DEBUG", "").lower() in {"1", "true", "yes"},
    )


# Global settings object. Overridable for tests.
settings = _load_settings()
