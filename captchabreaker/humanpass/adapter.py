"""Adapt an existing duck-typed CDP session into HumanPass's CDP interface.

HypeFarm's scrapers already have their own minimal CDP sessions exposing
`command(method, params) -> dict` (see reddit_dragnet.py's CDPSession and
x_browser_search.py's CDPSession). CommandAdapter wraps such a session so
HumanPass can drive it without those pipelines adopting CaptchaBreaker's own
CDPClient. This keeps the integration a guarded-import dependency: the scrapers
keep working untouched if captchabreaker isn't installed.
"""

from __future__ import annotations

import base64
from typing import Any, Optional


class CommandAdapter:
    """Wraps any object with `command(method, params) -> dict` into the CDP
    surface HumanPass expects (evaluate / mouse_* / wheel / screenshot / close).
    """

    def __init__(self, session):
        self._session = session
        if not hasattr(session, "command"):
            raise TypeError("session must expose command(method, params)")

    # -- passthrough --------------------------------------------------------
    def command(self, method: str, params: Optional[dict] = None) -> dict:
        return self._session.command(method, params or {})

    def close(self) -> None:
        close = getattr(self._session, "close", None)
        if close:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass

    # -- HumanPass interface ------------------------------------------------
    def evaluate(self, expression: str) -> Any:
        res = self._session.command("Runtime.evaluate", {
            "expression": expression, "returnByValue": True})
        result = res.get("result") or {}
        value = result.get("value")
        # Runtime.evaluate may return a "type" but no serializable value for
        # object literals in some shapes; fall back to unserializedValue.
        if value is None and "unserializableValue" in result:
            value = result["unserializableValue"]
        return value

    def mouse_move(self, x: float, y: float, buttons: int = 0) -> None:
        self._session.command("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": float(x), "y": float(y), "buttons": buttons})

    def mouse_down(self, x: float, y: float, button: str = "left") -> None:
        self._session.command("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": float(x), "y": float(y),
            "button": button, "buttons": 1, "clickCount": 1})

    def mouse_up(self, x: float, y: float, button: str = "left") -> None:
        self._session.command("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": float(x), "y": float(y),
            "button": button, "buttons": 0, "clickCount": 1})

    def wheel(self, delta_y: int, x: float = 8, y: float = 8) -> None:
        self._session.command("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": delta_y})

    def screenshot(self, format: str = "png") -> bytes:
        res = self._session.command("Page.captureScreenshot", {"format": format})
        return base64.b64decode(res["data"])


def adapt_session(session) -> CommandAdapter:
    """Convenience constructor; keeps call sites terse."""
    return CommandAdapter(session)
