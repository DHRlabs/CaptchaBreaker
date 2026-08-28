"""Minimal Chrome DevTools Protocol (CDP) client over WebSocket.

CaptchaBreaker's scrapers (and the humanpass module) drive a real Chrome that
already has remote debugging enabled. We speak just enough CDP to:

  * simulate human pointer input (Input.dispatchMouseEvent)
  * type text with per-character events (Input.dispatchKeyEvent)
  * scroll (mouseWheel)
  * screenshot the page (Page.captureScreenshot) for optional vision solving
  * run JS in the page to locate widgets (Runtime.evaluate)

No driver executables, no Playwright — a raw WebSocket to the browser's
/devtools endpoint. Requires the `browser` extra (websocket-client).
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

try:
    import websocket  # type: ignore
except ImportError:  # pragma: no cover
    websocket = None


class CDPError(RuntimeError):
    pass


class CDPClient:
    """A wafer-thin synchronous CDP client. One command waits for its reply."""

    def __init__(self, ws_url: str, timeout: float = 30.0):
        if websocket is None:
            raise RuntimeError(
                "websocket-client is required for CDP; install with "
                "`pip install captchabreaker[browser]`")
        self._ws = websocket.create_connection(ws_url, timeout=timeout)
        self._id = 0

    # -- low-level ----------------------------------------------------------
    def command(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        self._id += 1
        mid = self._id
        self._ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self._ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError(msg["error"].get("message", str(msg["error"])))
                return msg.get("result", {})
        # unreachable

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # -- pointer ------------------------------------------------------------
    def mouse_move(self, x: float, y: float, buttons: int = 0) -> None:
        self.command("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y, "buttons": buttons})

    def mouse_down(self, x: float, y: float, button: str = "left") -> None:
        self.command("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": button, "buttons": 1, "clickCount": 1})

    def mouse_up(self, x: float, y: float, button: str = "left") -> None:
        self.command("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": button, "buttons": 0, "clickCount": 1})

    def wheel(self, delta_y: int, x: float = 8, y: float = 8) -> None:
        self.command("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y, "deltaX": 0, "deltaY": delta_y})

    # -- keyboard -----------------------------------------------------------
    def key(self, key: str, char: str, modifiers: int = 0) -> None:
        self.command("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": key, "text": char,
            "code": "Key" + key.upper() if len(key) == 1 else "", "modifiers": modifiers})
        self.command("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": key, "modifiers": modifiers})

    # -- page ---------------------------------------------------------------
    def screenshot(self, format: str = "png") -> bytes:
        res = self.command("Page.captureScreenshot", {"format": format})
        import base64
        return base64.b64decode(res["data"])

    def evaluate(self, expression: str) -> Any:
        res = self.command("Runtime.evaluate", {
            "expression": expression, "returnByValue": True})
        return res.get("result", {}).get("value")

    def current_url(self) -> str:
        return self.evaluate("location.href")


def find_ws_url_for(ws_url: str) -> str:
    """Widen an http devtools endpoint into a debuggable ws URL (best effort).

    Accepts http://host:port/json, http://host:port, or ws://... directly.
    """
    if ws_url.startswith("ws://") or ws_url.startswith("wss://"):
        return ws_url
    base = ws_url.rstrip("/")
    if not base.endswith("/json"):
        base = base + "/json"
    import urllib.request
    try:
        with urllib.request.urlopen(base, timeout=5) as r:
            pages = json.load(r)
        for p in pages:
            if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
                return p["webSocketDebuggerUrl"]
        raise CDPError("no debuggable page target found")
    except (OSError, ValueError) as e:
        raise CDPError(f"could not reach Chrome devtools at {ws_url}: {e}") from e
