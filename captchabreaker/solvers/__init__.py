"""Solver backend registry.

A solver is any callable that takes a SolveRequest and returns a SolveResponse.
CaptchaBreaker routes:
    * image / text / math        -> LocalOCRSolver   (free, offline)
    * recaptcha / hcaptcha / ... -> NetworkSolver     (paid provider, needs API key)

If the network solver is not configured (no API key) and a network captcha comes
in, we fall back to a CLEAR-marker response so the agent knows it was unsolved
and can retry / use its own fallback.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from captchabreaker.models import CaptchaType, SolveRequest, SolveResponse
from captchabreaker.solvers.image_ocr import LocalOCRSolver
from captchabreaker.solvers.network import NetworkSolver


_LOCAL_TYPES = {CaptchaType.IMAGE, CaptchaType.TEXT, CaptchaType.MATH}
_NETWORK_TYPES = set(CaptchaType) - _LOCAL_TYPES


class SolverRegistry:
    """Routes captcha types to the right backend and caches repeat solutions."""

    def __init__(self, local: Optional[LocalOCRSolver] = None,
                 network: Optional[NetworkSolver] = None):
        self.local = local or LocalOCRSolver()
        self.network = network
        self._cache: Dict[str, str] = {}
        self.cache_hits = 0

    def is_network_type(self, type_: CaptchaType) -> bool:
        return type_ in _NETWORK_TYPES

    # -- cache -------------------------------------------------------------
    def cache_key(self, req: SolveRequest) -> Optional[str]:
        if req.type in _LOCAL_TYPES:
            return f"{req.type.value}:{req.image}" if req.image else None
        if req.sitekey:
            return f"{req.type.value}:{req.sitekey}:{req.page_url}"
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
            return self.local.solve(req)

        if req.type in _NETWORK_TYPES:
            if self.network:
                resp = self.network.solve(req)
            else:
                resp = SolveResponse.fail(
                    req.type,
                    "network captcha but no provider API key; set CAPTCHABREAKER_API_KEY",
                )
            if resp.success and key:
                self._cache[key] = resp.solution
            return resp

        return SolveResponse.fail(req.type, f"unknown captcha type: {req.type}")


# Module-level singleton (shared across server, SDK, CLI).
registry = SolverRegistry()


def ensure_network_solver() -> None:
    """Attach the network solver lazily so turning on an API key at runtime works."""
    if registry.network is None:
        registry.network = NetworkSolver()
