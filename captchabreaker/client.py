"""Python SDK so your agents can solve CAPTCHAs in-process, no HTTP needed.

Agents (Codex, Claude Code, custom puppeteer scripts) can either:

    from captchabreaker import solve_image
    answer, ok = solve_image("/tmp/captcha.png")

or hit the HTTP API from any language (see examples/). This module talks to
the same solver backend registry as the server.
"""

from __future__ import annotations

import time
from typing import Optional, Tuple

import httpx

from captchabreaker.config import settings
from captchabreaker.models import CaptchaType, SolveRequest, SolveResponse
from captchabreaker.solvers import ensure_network_solver, registry


def _route(req: SolveRequest) -> SolveResponse:
    ensure_network_solver()
    start = time.perf_counter()
    resp = registry.solve(req)
    if resp.duration_ms == 0:
        resp.duration_ms = (time.perf_counter() - start) * 1000
    return resp


# -- high-level helpers ------------------------------------------------------

def solve_image(image: str) -> Tuple[str, bool]:
    """Solve an image/text CAPTCHA. `image` = path, raw base64, or data: URL.

    Returns (answer, success)."""
    r = _route(SolveRequest(type=CaptchaType.IMAGE, image=image))
    return r.solution, r.success


def solve_math(image: str) -> Tuple[str, bool]:
    """Solve a math CAPTCHA image ('3 + 5 = ?')."""
    r = _route(SolveRequest(type=CaptchaType.MATH, image=image))
    return r.solution, r.success


def solve_network(captcha_type: str, sitekey: str, page_url: str,
                  **extra) -> SolveResponse:
    """Solve reCAPTCHA / hCaptcha / Turnstile via the configured provider."""
    return _route(SolveRequest(
        type=CaptchaType(captcha_type),
        sitekey=sitekey, page_url=page_url, extra=extra,
    ))


def solve(req: SolveRequest) -> SolveResponse:
    """Generic entry — pass your own SolveRequest."""
    return _route(req)


# -- remote client (talks to a running CaptchaBreaker server) -----------------

class RemoteClient:
    """HTTP client for the CaptchaBreaker server, for out-of-process agents."""

    def __init__(self, base_url: str = f"http://127.0.0.1:{settings.port}"):
        self.base_url = base_url.rstrip("/")

    def solve(self, req: SolveRequest) -> SolveResponse:
        r = httpx.post(f"{self.base_url}/solve", json=req.model_dump(mode="json"),
                       timeout=config_timeout())
        r.raise_for_status()
        return SolveResponse.model_validate(r.json())

    def status(self) -> dict:
        return httpx.get(f"{self.base_url}/status").json()


def config_timeout() -> float:
    return float(settings.timeout + 10)
