"""Pydantic request/response models for the HTTP API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CaptchaType(str, Enum):
    """The captcha families CaptchaBreaker solves with its local OCR engine."""

    IMAGE = "image"   # inline distorted text / math captcha -> local OCR
    TEXT = "text"     # alias of image (some CAPTCHAs call it text)
    MATH = "math"


class SolveRequest(BaseModel):
    """Solve request for the local OCR engine."""

    type: CaptchaType = CaptchaType.IMAGE
    image: Optional[str] = Field(
        default=None,
        description="Base64-encoded image OR a path / data: URL. Required for image types.",
    )


class SolveResponse(BaseModel):
    success: bool
    type: CaptchaType
    channel: str = Field(default="", description="'local' or 'cache'. Empty on failure.")
    solution: str = Field(default="", description="The OCR answer to submit.")
    confidence: float = Field(default=0.0, description="Local OCR confidence 0..1.")
    duration_ms: float = Field(default=0.0)
    raw: Optional[Dict[str, Any]] = Field(default=None, description="Error detail on failure.")

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
    cache_hits: int = 0
