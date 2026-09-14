"""CaptchaBreaker HTTP API server.

This is the primary interface for puppeteering agents: they POST the captcha
they hit and get back the solution. Run with:

    python -m captchabreaker.server          # or: captchabreaker serve

Agents reach it at  http://127.0.0.1:8977  (see README for the API contract).
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from captchabreaker import __version__
from captchabreaker.config import settings
from captchabreaker.models import SolveRequest, SolveResponse, StatusResponse
from captchabreaker.solvers import registry

log = logging.getLogger("captchabreaker.server")

app = FastAPI(
    title="CaptchaBreaker",
    version=__version__,
    description="Self-contained CAPTCHA-solving service for browser agents.",
)


@app.get("/", tags=["meta"])
def root() -> dict:
    return {"service": "captchabreaker", "version": __version__,
            "docs": "/docs", "status": "/status"}


@app.get("/status", response_model=StatusResponse, tags=["meta"])
def status() -> StatusResponse:
    return StatusResponse(
        status="ok",
        version=__version__,
        cache_hits=registry.cache_hits,
    )


@app.post("/solve", response_model=SolveResponse, tags=["solve"])
async def solve(req: SolveRequest) -> SolveResponse:
    """Generic solve endpoint. Sets `type` (default 'image') and payload."""
    start = time.perf_counter()
    resp = registry.solve(req)
    if resp.duration_ms == 0:
        resp.duration_ms = (time.perf_counter() - start) * 1000
    return resp


@app.post("/solve/{captcha_type}", response_model=SolveResponse, tags=["solve"])
async def solve_typed(captcha_type: str, req: SolveRequest) -> SolveResponse:
    """Typed solve endpoint: /solve/image, /solve/text, /solve/math.

    The path segment overrides req.type.
    """
    from captchabreaker.models import CaptchaType
    try:
        resolved = CaptchaType(captcha_type)
    except ValueError:
        return SolveResponse.fail(req.type, f"unknown captcha type: {captcha_type}")
    req.type = resolved
    return await solve(req)


@app.exception_handler(Exception)
async def _unhandled(req, exc) -> JSONResponse:
    from captchabreaker.models import CaptchaType
    return JSONResponse(
        status_code=200,
        content=SolveResponse.fail(CaptchaType.IMAGE,
                                   f"server error: {exc}").model_dump(),
    )


def main() -> None:
    import uvicorn
    log.info("CaptchaBreaker serving on http://%s:%d", settings.host, settings.port)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
