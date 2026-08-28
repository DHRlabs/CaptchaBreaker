"""High-level pass: find a CAPTCHA widget and get through it like a human.

HumanPass drives a live Chrome (via the minimal CDP client) to:

  1. Locate the CAPTCHA (reCAPTCHA / hCaptcha / Turnstile iframe or a
     "prove you are human" button) by running JS in the page.
  2. Move the cursor there along a human trajectory and click with human timing.
     For reCAPTCHA v2/checkbox challenges, that alone triggers the silent
     behavioral challenge and completes the pass — no vision needed.
  3. If an image grid challenge appears AND a vision solver is configured,
     screenshot the page, ask the vision model where to click, then human-click
     each tile. Without vision it degrades gracefully (the checkbox attempt
     still goes through).
  4. Human scroll/type helpers so the rest of the page interaction also reads
     natural.

Separating concerns: `motion` is the hand (pure), `cdp` is the transport,
`vision` is the brain (optional), and this class is the conductor.
"""

from __future__ import annotations

import random
import time
from typing import Dict, List, Optional

from captchabreaker.humanpass import motion
from captchabreaker.humanpass.cdp import CDPClient
from captchabreaker.humanpass import vision as vision_mod

# JS: find the captcha widget's on-screen box (cross-origin iframe or button text).
_FIND_BOX_JS = r"""
(() => {
  const selectors = [
    'iframe[title="reCAPTCHA"]',
    '.g-recaptcha',
    'iframe[src*="recaptcha"]',
    'iframe[title*="hCaptcha"]',
    'iframe[src*="hcaptcha"]',
    'iframe[src*="challenges.cloudflare"]',
    'iframe[title*="Turnstile"]',
  ];
  for (const s of selectors) {
    const el = document.querySelector(s);
    if (el) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0) {
        return {found:true, x:r.x, y:r.y, w:r.width, h:r.height,
                cx:r.x+r.width/2, cy:r.y+r.height/2, tag:s};
      }
    }
  }
  const phrases = ['prove you are human','prove your humanity',
                   'verify you are human','continue'];
  for (const b of document.querySelectorAll('button, a[role="button"]')) {
    const txt = (b.textContent||'').trim().toLowerCase();
    const r = b.getBoundingClientRect();
    if (phrases.some(p => txt.includes(p)) && r.width > 0 && r.height > 0) {
      return {found:true, x:r.x, y:r.y, w:r.width, h:r.height,
              cx:r.x+r.width/2, cy:r.y+r.height/2, tag:'button:'+txt.slice(0,40)};
    }
  }
  return {found:false};
})()
"""


class HumanPass:
    """Drive human-like input against a real Chrome to get past CAPTCHAs."""

    def __init__(self, cdp: CDPClient, *, seed: Optional[int] = None,
                 vision: Optional[bool] = None):
        self.cdp = cdp
        self.rng = random.Random(seed)
        self.vision = vision if vision is not None else vision_mod.vision_enabled()
        self._cursor: Optional[tuple] = None

    # -- cursor -------------------------------------------------------------
    def _cursor_pos(self):
        if self._cursor is None:
            dims = self.cdp.evaluate("{w:innerWidth,h:innerHeight}")
            w = (dims or {}).get("w", 0) or int(self.cdp.evaluate("innerWidth") or 0)
            h = (dims or {}).get("h", 0) or int(self.cdp.evaluate("innerHeight") or 0)
            self._cursor = (w / 2, h / 2)
        return self._cursor

    # -- motion -------------------------------------------------------------
    def _human_move(self, x: float, y: float) -> None:
        cx, cy = self._cursor_pos()
        traj = motion.human_trajectory(cx, cy, x, y, seed=self.rng.random())
        for delay_ms, px, py in traj:
            self.cdp.mouse_move(px, py)
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
        self._cursor = (x, y)

    def _human_click(self, x: float, y: float) -> None:
        self._human_move(x, y)
        hold = self.rng.uniform(70, 160)
        self.cdp.mouse_down(x, y)
        time.sleep(hold / 1000.0)
        self.cdp.mouse_up(x, y)
        # humans drift away slightly after a click
        try:
            self._human_move(x + self.rng.uniform(-8, 22) / 2, y + self.rng.uniform(-8, 18) / 2)
        except Exception:  # noqa: BLE001
            pass

    # -- public actions -----------------------------------------------------
    def settle(self, min_ms: float = 250, max_ms: float = 900) -> None:
        """An idle pause before acting, scaled like a human deciding what to do."""
        time.sleep(self.rng.uniform(min_ms, max_ms) / 1000.0)

    def find_box(self) -> Optional[Dict]:
        box = self.cdp.evaluate(_FIND_BOX_JS)
        return box if box and box.get("found") else None

    def scroll(self, delta_y: int) -> None:
        for step, pause in motion.human_scroll_steps(delta_y, seed=self.rng.random()):
            self.cdp.wheel(step)
            if pause:
                time.sleep(pause / 1000.0)

    def type_text(self, text: str, into_selector: str = "") -> None:
        """Human-paced typing (per-char timing). If into_selector given, focus it first."""
        if into_selector:
            self.cdp.evaluate(
                f"document.querySelector({json_quote(into_selector)}).focus()")
        for ch, ivl in zip(text, motion.human_type_intervals(
                text, seed=self.rng.random())):
            self.cdp.key(ch, ch)
            time.sleep(ivl / 1000.0)

    def pass_captcha(self, *, grid_timeout: float = 6.0) -> bool:
        """Attempt to click through the CAPTCHA human-ly. Returns True if it did

        anything (a widget was clicked), False if no captcha was found.
        """
        self.settle(200, 700)
        box = self.find_box()
        if not box:
            return False

        self._human_click(box["cx"], box["cy"])
        self._human_move(box["cx"], box["cy"] + 30)  # look away, human behavior

        # Optional grid round: after the checkbox, a challenge grid may appear.
        if self.vision:
            self._try_grid(grid_timeout)
        return True

    def _try_grid(self, timeout: float) -> None:
        """If a vision model is configured, screenshot and click any image tiles."""
        deadline = time.time() + timeout
        seen = False
        while time.time() < deadline and not seen:
            try:
                shot = self.cdp.screenshot()
            except Exception:  # noqa: BLE001
                return
            result = vision_mod.solve_image_with_vision(shot)
            clicks = result.get("clicks")
            if isinstance(clicks, list) and clicks:
                seen = True
                for x, y in clicks:
                    self._human_click(float(x), float(y))
                    time.sleep(self.rng.uniform(0.2, 0.4))
            time.sleep(0.6)
        _ = seen


def json_quote(s: str) -> str:
    import json as _json
    return _json.dumps(s)
