"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CaptchaType(str, Enum):
    """The captcha families CaptchaBreaker knows how to solve."""

    IMAGE = "image"                 # inline distorted text / math captcha -> local OCR
    TEXT = "text"                   # alias of image (some CAPTCHAs call it text)
    MATH = "math"
    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    TURNSTILE = "turnstile"
    FUNCAPTCHA = "funcaptcha"
    GEETEST = "geetest"
    LEMINSCAPTCHA = "leminscaptcha"


# Type names as understood by CapSolver / 2Captcha-style providers.
_PROVIDER_TYPE_MAP = {
    CaptchaType.RECAPTCHA_V2: "ReCaptchaV2TaskProxyLess",
    CaptchaType.RECAPTCHA_V3: "ReCaptchaV3TaskProxyLess",
    CaptchaType.HCAPTCHA: "HCaptchaTaskProxyLess",
    CaptchaType.TURNSTILE: "TurnstileTaskProxyLess",
    CaptchaType.FUNCAPTCHA: "FunCaptchaTaskProxyLess",
    CaptchaType.GEETEST: "GeeTestTaskProxyLess",
}


class SolveRequest(BaseModel):
    """Generic solve request. Agents send this and get back a SolveResponse."""

    type: CaptchaType = CaptchaType.IMAGE
    # For image/text/math:
    image: Optional[str] = Field(
        default=None,
        description="Base64-encoded image OR a path / data: URL. Required for image types.",
    )
    # For network-based captchas:
    sitekey: Optional[str] = Field(default=None, description="Site key shown on the page.")
    page_url: Optional[str] = Field(default=None, description="URL of the page with the captcha.")
    # Optional hints for provider routing:
    provider: Optional[str] = Field(default=None, description="Force a specific provider.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Extra provider params (e.g. invisible for v3).")


class SolveResponse(BaseModel):
    success: bool
    type: CaptchaType
    channel: str = Field(default="", description="'local', 'network', or 'cache'. Empty on failure.")
    solution: str = Field(default="", description="The token/answer to submit.")
    confidence: float = Field(default=0.0, description="Local OCR confidence 0..1 (0 for network).")
    duration_ms: float = Field(default=0.0)
    provider: Optional[str] = None
    raw: Optional[Dict[str, Any]] = Field(default=None, description="Raw provider payload (network only).")

    @staticmethod
    def ok(type_: CaptchaType, solution: str, **kw) -> "SolveResponse":
        return SolveResponse(success=True, type=type_, solution=solution, **kw)

    @staticmethod
    def fail(type_: CaptchaType, error: str, **kw) -> "SolveResponse":
        return SolveResponse(success=False, type=type_,
                             raw={"error": str(error)}, **kw)


class StatusResponse(BaseModel):
    status: str
    version: str
    provider: str
    network_enabled: bool
    cache_hits: int = 0
