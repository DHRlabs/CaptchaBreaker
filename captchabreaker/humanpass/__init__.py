"""HumanPass — get your browser agents past "I am not a robot" like a human.

A self-contained companion to CaptchaBreaker's solvers. Instead of (only)
solving captcha IMAGES, HumanPass drives the *live browser*: it finds the
reCAPTCHA / hCaptcha / Turnstile widget or "prove you are human" button in the
DOM, moves the cursor there along a human-looking trajectory, and clicks with
human timing. The silent behavioral challenge does the rest. An optional vision
backend (see captchabreaker.humanpass.vision) can read image grids and tell the
motion engine exactly where to click.

Public API:
    from captchabreaker.humanpass import HumanPass
    hp = HumanPass(cdp_client)          # cdp_client = CDPClient(ws_url)
    hp.pass_captcha()                   # True if it attempted a pass

    # low-level building blocks
    from captchabreaker.humanpass.motion import human_trajectory, ...
    from captchabreaker.humanpass.cdp import CDPClient, find_ws_url_for
"""

from captchabreaker.humanpass.passer import HumanPass  # noqa: F401
from captchabreaker.humanpass.cdp import CDPClient, find_ws_url_for, CDPError  # noqa: F401
from captchabreaker.humanpass.adapter import CommandAdapter, adapt_session  # noqa: F401
from captchabreaker.humanpass.motion import (  # noqa: F401
    human_trajectory,
    human_type_intervals,
    human_scroll_steps,
)

__all__ = [
    "HumanPass",
    "CDPClient",
    "find_ws_url_for",
    "CDPError",
    "human_trajectory",
    "human_type_intervals",
    "human_scroll_steps",
]
