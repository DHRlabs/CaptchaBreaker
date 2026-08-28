"""CaptchaBreaker — self-contained CAPTCHA-solving service for LLM agents that puppeteer browsers.

Pipelines:
    image  -> local OCR engine (free, no API key, works offline)
    recaptcha/hcaptcha/turnstile -> paid network provider (CapSolver/2Captcha protocol) when configured
"""

from captchabreaker.config import (  # noqa: F401
    settings,
    get_provider_config,
    is_network_enabled,
)
from captchabreaker.client import solve, solve_image, solve_math, solve_network  # noqa: F401
from captchabreaker.models import (  # noqa: F401
    CaptchaType,
    SolveRequest,
    SolveResponse,
)

__version__ = "0.1.0"
