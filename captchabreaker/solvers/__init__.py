"""Solver backend registry.

CaptchaBreaker solves image/text/math CAPTCHAs entirely with the local, offline
OCR engine — no paid network provider, no API key. Browser-level challenges
(reCAPTCHA / hCaptcha / Turnstile checkboxes) are handled separately by the
HumanPass module, which clicks through them behaviorally for free. Unknown
captcha types fail gracefully so an agent can fall back to its own logic.
"""

from __future__ import annotations

from typing import Dict, Optional

from captchabreaker.models import CaptchaType, SolveRequest, SolveResponse
from captchabreaker.solvers.image_ocr import LocalOCRSolver


_LOCAL_TYPES = {CaptchaType.IMAGE, CaptchaType.TEXT, CaptchaType.MATH}


class SolverRegistry:
    """Routes captcha types to the local OCR backend and caches repeat solutions."""

    def __init__(self, local: Optional[LocalOCRSolver] = None):
        self.local = local or LocalOCRSolver()
        self._cache: Dict[str, str] = {}
        self.cache_hits = 0

    # -- cache -------------------------------------------------------------
    def cache_key(self, req: SolveRequest) -> Optional[str]:
        if req.type in _LOCAL_TYPES:
            return f"{req.type.value}:{req.image}" if req.image else None
        return None

    def _from_cache(self, key: Optional[str]) -> Optional[str]:
        if key and key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        return None

    # -- solving -----------------------------------------------------------
    def solve(self, req: SolveRequest) -> SolveResponse:
        key = self.cache_key(req)
        cached = self._from_cache(key)
        if cached is not None:
            return SolveResponse.ok(req.type, cached, channel="cache")

        if req.type in _LOCAL_TYPES:
            resp = self.local.solve(req)
            if resp.success and key:
                self._cache[key] = resp.solution
            return resp

        return SolveResponse.fail(req.type, f"unknown captcha type: {req.type}")


# Module-level singleton (shared across server, SDK, CLI).
registry = SolverRegistry()
