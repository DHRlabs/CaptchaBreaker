"""Network CAPTCHA provider (reCAPTCHA, hCaptcha, Turnstile, ...).

Implements the "create task -> poll for result" JSON protocol shared by
2Captcha, CapSolver, CapMonster, RuCaptcha and most self-hosted proxies.

Only active when an API key is configured (CAPTCHABREAKER_API_KEY).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from captchabreaker import config
from captchabreaker.models import (
    CaptchaType,
    SolveRequest,
    SolveResponse,
    _PROVIDER_TYPE_MAP,
)

log = logging.getLogger("captchabreaker.network")

# CapSolver calls its poll endpoint differently than 2Captcha; normalize.
# Submitting:  POST {host}/submit  with {"task": {...}, "apiKey": key}
# Polling:     GET  {host}/get    with {"taskId": ..., "apiKey": key}
# The poll payload is our requested task shape; switch it per host if needed.
_TASK_KEY = "task"          # most providers
_ACTION_INS = "submit"
_ACTION_OUT = "get"


class NetworkSolver:
    """Solves network captchas via a configured paid provider."""

    def __init__(self, client: Optional[httpx.Client] = None):
        self.client = client or httpx.Client(timeout=config.settings.timeout + 10)

    # -- public ------------------------------------------------------------
    def solve(self, req: SolveRequest) -> SolveResponse:
        # Without an API key, decline gracefully — no HTTP calls, no provider hit.
        if not config.is_network_enabled():
            return SolveResponse.fail(
                req.type,
                "network captcha but no provider API key; set CAPTCHABREAKER_API_KEY",
                provider=config.settings.provider,
            )
        url = config.settings.effective_host
        task = self._build_task(req)
        if task is None:
            return SolveResponse.fail(req.type,
                                     f"no provider task mapping for {req.type.value}")

        try:
            created = self._create_task(url, task)
            if not created.get("taskId"):
                return SolveResponse.fail(
                    req.type,
                    f"provider refused task: {created.get('error', created)}",
                    provider=config.settings.provider, raw=created,
                )
            task_id = created["taskId"]
            token = self._poll(url, task_id)
            if token is None:
                return SolveResponse.fail(
                    req.type, "provider timed out (no token)",
                    provider=config.settings.provider)
            return SolveResponse.ok(
                req.type, token, channel="network",
                provider=config.settings.provider)
        except httpx.HTTPError as e:
            return SolveResponse.fail(req.type, f"provider request error: {e}",
                                      provider=config.settings.provider)

    # -- task construction ---------------------------------------------------
    def _build_task(self, req: SolveRequest) -> Optional[Dict[str, Any]]:
        type_key = _PROVIDER_TYPE_MAP.get(req.type)
        if type_key is None:
            return None
        task: Dict[str, Any] = {"type": type_key}
        if req.page_url:
            task["websiteURL"] = req.page_url
        if req.sitekey:
            task["websiteKey"] = req.sitekey
        task.update(req.extra)
        return task

    # -- protocol -----------------------------------------------------------
    def _create_task(self, url: str, task: Dict[str, Any]) -> Dict[str, Any]:
        if config.settings.provider in ("2captcha", "capmonster", "rucaptcha"):
            body = {"key": config.settings.api_key, "task": task}
        else:  # capsolver and friends
            body = {"apiKey": config.settings.api_key, "task": task}
        r = self.client.post(f"{url}/{_ACTION_INS}", json=body)
        r.raise_for_status()
        return r.json()

    def _poll(self, url: str, task_id: str, interval: float = 3.0) -> Optional[str]:
        deadline = config.settings.timeout
        import time
        start = time.time()
        while time.time() - start < deadline:
            params: Dict[str, Any] = {"taskId": task_id}
            if config.settings.provider in ("2captcha", "capmonster", "rucaptcha"):
                params["key"] = config.settings.api_key
            else:
                params["apiKey"] = config.settings.api_key
            r = self.client.get(f"{url}/{_ACTION_OUT}", params=params)
            r.raise_for_status()
            data = r.json()
            status = str(data.get("status", "")).lower()
            if data.get("solution", {}).get("gRecaptchaResponse"):
                return data["solution"]["gRecaptchaResponse"]
            if isinstance(data.get("solution"), dict):
                for k, v in data["solution"].items():
                    if isinstance(v, str) and len(v) > 10:
                        return v
            if status in ("processed", "ready"):
                # response may be top-level
                for k in ("gRecaptchaResponse", "value", "solution"):
                    if isinstance(data.get(k), str) and len(data[k]) > 10:
                        return data[k]
            time.sleep(interval)
        return None
