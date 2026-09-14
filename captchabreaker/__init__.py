"""CaptchaBreaker — local-first CAPTCHA-solving service for LLM agents that puppeteer browsers.

Pipeline:
    image/text/math -> local OCR engine (free, offline, no API key)
Browser-level reCAPTCHA / hCaptcha / Turnstile checkboxes are handled by the
HumanPass module, which clicks through them behaviorally — still no paid
service by default. An optional external vision backend can handle image grids.
"""

from captchabreaker.config import settings  # noqa: F401
from captchabreaker.client import solve, solve_image, solve_math  # noqa: F401
from captchabreaker.models import (  # noqa: F401
    CaptchaType,
    SolveRequest,
    SolveResponse,
)

__version__ = "0.2.0"
