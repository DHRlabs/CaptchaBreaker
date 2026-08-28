"""Optional vision-LLM solver for CAPTCHA image grids / distorted text.

HumanPass can be pointed at any OpenAI-compatible vision endpoint so that the
agent genuinely "sees" the captcha and decides where to click or what the text
is — the brain for the motion engine's hand. It is fully optional: when no
vision config is present, HumanPass simply relies on the silent behavioral
checkbox path, which passes most reCAPTCHA v2/v3/Turnstile challenges by itself.

Configuration (env):
    VISION_BASE_URL   e.g. https://api.openai.com/v1   (chat/completions appended)
    VISION_API_KEY     API key
    VISION_MODEL       model id (must support image input)

It falls back to OPENAI_BASE_URL / OPENAI_API_KEY conditions so existing setups
"just work" when they already expose an OpenAI-compatible endpoint.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


def _cfg(name: str, fallback: str = ""):
    return os.getenv(name) or os.getenv(fallback) or ""


def vision_enabled() -> bool:
    return bool(_cfg("VISION_API_KEY", "OPENAI_API_KEY"))


def _endpoint() -> str:
    base = _cfg("VISION_BASE_URL", "OPENAI_BASE_URL") or "https://api.openai.com/v1"
    return base.rstrip("/") + "/chat/completions"


def solve_image_with_vision(image_bytes: bytes,
                            prompt: str = "",
                            timeout: float = 30.0) -> Dict[str, Any]:
    """Ask the configured vision model to interpret a CAPTCHA image.

    The model returns JSON. For grid captchas we request click coordinates; for
    text captchas we request the text. Returning "{...}" JSON keeps parsing easy.

    Returns a dict, or {} on any failure (caller decides how to fail soft).
    """
    if httpx is None:
        raise RuntimeError("httpx is required for the vision solver")
    if not vision_enabled():
        return {}

    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:image/png;base64,{b64}"
    user_msg = prompt or (
        "You are solving a CAPTCHA. Look at the image and answer in STRICT JSON only. "
        'If it is a grid of images to click, return {"clicks":[[x,y],...]} with '
        "viewport pixel coordinates of each required tile. If it is a text/number "
        'captcha, return {"text":"<answer>"}.'
    )
    body = {
        "model": _cfg("VISION_MODEL", "OPENAI_MODEL") or "openai/gpt-4o",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": user_msg},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {_cfg('VISION_API_KEY', 'OPENAI_API_KEY')}"}
    try:
        r = httpx.post(_endpoint(), json=body, headers=headers, timeout=timeout)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return {}

    try:
        parsed = content
        if isinstance(content, str):
            # strip markdown fences if present
            raw = content.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1] if "```" in raw[3:] else raw
                raw = raw.lstrip("json").strip()
            parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (ValueError, TypeError):
        pass
    return {}
