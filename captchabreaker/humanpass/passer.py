"""High-level pass: find a CAPTCHA widget and get through it like a human.

HumanPass drives a live Chrome (via the minimal CDP client) to:

  1. Locate the CAPTCHA (reCAPTCHA / hCaptcha / Turnstile iframe, a
     "prove you are human" button, or a page already carrying a response token)
     by running JS in the page.
  2. Move the cursor there along a human trajectory, REST a beat, then click
     with human timing. A resting cursor before a quick press is how a person
     clicks — a click that never moved reads as scripted. This exact
     hover-dwell-then-press pattern is what live deployment uses to pass
     reCAPTCHA (rolled in from jscan's bot-check hook, proven against Indeed's
     reCAPTCHA). For v2/checkbox challenges that alone triggers the silent
     behavioral challenge and completes the pass — no vision needed.
  3. Verify the pass: re-run detection and confirm the CAPTCHA cleared (a
     response token is now present or the widget is gone). If it is genuinely
     still blocking and a vision solver is configured, offer it an image-grid
     attempt before reporting stuck.
  4. Human scroll/type helpers so the rest of the page also reads natural.

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

# JS: detect the captcha widget's on-screen box, any response token already
# issued, and whether the page text hints at a not-a-robot challenge. Token
# inputs are included so an already-cleared challenge is treated as done.
_DETECT_JS = r"""
(() => {
  const sel = [
    'iframe[title="reCAPTCHA"]', '.g-recaptcha', 'iframe[src*="recaptcha"]',
    'iframe[title*="hCaptcha"]', 'iframe[src*="hcaptcha"]',
    'iframe[src*="challenges.cloudflare"]', 'iframe[title*="Turnstile"]',
    'textarea[name="g-recaptcha-response"]', 'input[name="cf-turnstile-response"]',
  ];
  let box = null;
  for (const s of sel) {
    const el = document.querySelector(s);
    if (!el) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      box = {tag:s, x:r.x, y:r.y, w:r.width, h:r.height,
             cx:r.x+r.width/2, cy:r.y+r.height/2};
      break;
    }
  }
  let token = '';
  for (const s of ['textarea[name="g-recaptcha-response"]','input[name="cf-turnstile-response"]']) {
    const el = document.querySelector(s);
    if (el && el.value) { token = el.value; break; }
  }
  if (!box) {
    const phrases = ['prove you are human','prove your humanity',
                     'verify you are human','continue'];
    for (const b of document.querySelectorAll('button, a[role="button"]')) {
      const txt = (b.textContent||'').trim().toLowerCase();
      const r = b.getBoundingClientRect();
      if (phrases.some(p => txt.includes(p)) && r.width > 0 && r.height > 0) {
        box = {tag:'button:'+txt.slice(0,30), x:r.x, y:r.y, w:r.width, h:r.height,
                cx:r.x+r.width/2, cy:r.y+r.height/2};
        break;
      }
    }
  }
  const body = (document.body && document.body.innerText || '').slice(0, 2000);
  const phrases = /i'?m not a robot|verify you are human|prove you are human|hcaptcha|recaptcha|captcha/i.test(body);
  return {found: !!box, box: box, token: token, phrases: phrases};
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
        self.last_outcome: str = "never_run"

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
        # Resting cursor, then a quick press: how a person clicks. A click that
        # never moved reads as scripted. (Live-proven hover-dwell click from
        # jscan's bot-check hook.)
        time.sleep(self.rng.uniform(40, 120) / 1000.0)
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

    def detect(self) -> Dict:
        """Run widget/token/phrase detection in the page. Returns the raw state."""
        return self.cdp.evaluate(_DETECT_JS) or {}

    def find_box(self) -> Optional[Dict]:
        """Return the captcha widget's box dict (cx/cy/tag/...) or None."""
        state = self.detect()
        return state.get("box") if state.get("found") else None

    def _state_clear(self, state: Dict) -> bool:
        """True when nothing is blocking: a token is present, or no widget or
        challenge phrase remains on the page."""
        if state.get("token"):
            return True
        return not (state.get("found") or state.get("phrases"))

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

    def pass_captcha(self, *, grid_timeout: float = 6.0,
                     verify_delay: float = 1.2) -> bool:
        """Attempt to get past the CAPTCHA human-ly.

        Returns True when nothing is blocking: no CAPTCHA present, it already
        carried a response token, or our human click cleared it. Returns False
        when a CAPTCHA was found and is still blocking after the attempt — the
        caller should treat that as genuinely stuck and fall back (e.g. report
        it for a human). Diagnostics are left on `self.last_outcome`.
        """
        self.settle(200, 700)
        state = self.detect()
        if self._state_clear(state):
            self.last_outcome = "absent" if not state.get("found") else "already_cleared"
            return True

        box = state.get("box")
        if box:
            self._human_click(box["cx"], box["cy"])
            time.sleep(verify_delay)
            after = self.detect()
            if self._state_clear(after):
                self.last_outcome = "cleared"
                return True

        # A widget is still blocking. If a vision solver is configured, give it
        # a shot at an image-grid challenge before reporting stuck.
        if self.vision:
            self._try_grid(grid_timeout)
            retry = self.detect()
            if self._state_clear(retry):
                self.last_outcome = "cleared_by_vision"
                return True

        self.last_outcome = "still_blocking" if box else "challenge_phrase_no_target"
        return False

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
