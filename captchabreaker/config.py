"""Configuration for CaptchaBreaker.

CaptchaBreaker is fully local and offline: the OCR path needs no keys, no
credentials, and no `.env` at all. Browser-level challenges (reCAPTCHA /
hCaptcha / Turnstile checkboxes) are handled by the HumanPass module, which
clicks through them behaviorally — no paid provider, no API key. The only
runtime settings are the HTTP port and debug logging.
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


@dataclass
class Settings:
    port: int = DEFAULT_HTTP_PORT
    debug: bool = False


def _load_settings() -> Settings:
    return Settings(
        port=int(os.getenv("CAPTCHABREAKER_PORT", str(DEFAULT_HTTP_PORT))),
        debug=os.getenv("CAPTCHABREAKER_DEBUG", "").lower() in {"1", "true", "yes"},
    )


# Global settings object. Overridable for tests.
settings = _load_settings()
