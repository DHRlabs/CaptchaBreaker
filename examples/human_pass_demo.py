#!/usr/bin/env python
"""Live end-to-end demo: HumanPass clicks through a real reCAPTCHA v2 checkbox.

Spawns its own headless Chrome (does NOT interfere with your running scrapers on
9222/9224), loads Google's official reCAPTCHA demo, finds the widget, clicks it
with human motion, and reports whether reCAPTCHA answered with a token.

Usage:
    .venv/bin/python examples/human_pass_demo.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
DEMO_URL = "https://www.google.com/recaptcha/api2/demo"


def _wait_for_devtools(port, tries=80):
    for _ in range(tries):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as r:
                pages = json.load(r)
            if any(p.get("type") == "page" for p in pages):
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def main() -> int:
    try:
        from captchabreaker.humanpass import CDPClient, HumanPass, find_ws_url_for
    except ImportError as e:
        print("need the [browser] extra:", e)
        return 1

    proc = subprocess.Popen([
        CHROME, "--headless=new",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",      # allow CDP websocket connections
        "--disable-gpu",
        "--no-first-run",
        f"--user-data-dir=/tmp/chrome_hm_uddir",
        "--disable-features=Translate,OptimizeHints",
        DEMO_URL,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        if not _wait_for_devtools(PORT):
            print("Chrome devtools did not come up")
            return 1

        ws = find_ws_url_for(f"http://127.0.0.1:{PORT}")
        print("connected:", ws)
        with CDPClient(ws) as cdp:
            # Navigate explicitly (the CLI-arg URL is unreliable in headless).
            cdp.command("Page.navigate", {"url": DEMO_URL})
            for _ in range(60):
                if cdp.current_url() == DEMO_URL:
                    break
                time.sleep(0.5)
            time.sleep(5.0)  # let reCAPTCHA widget finish loading
            print("page:", cdp.current_url())

            hp = HumanPass(cdp, seed=11)   # vision auto-disabled unless configured
            box = hp.find_box()
            if not box:
                print("no captcha widget found on this page — nothing to do.")
                print("(selectors tried: reCAPTCHA/hCaptcha/Turnstile iframes + buttons)")
                return 0

            print(f"captcha widget found: {box.get('tag')} at "
                  f"({box.get('cx'):.0f},{box.get('cy'):.0f})")
            did = hp.pass_captcha()
            print(f"pass_captcha attempted: {did}")

            # Wait for any silent challenge to resolve, then probe reCAPTCHA state.
            time.sleep(4.0)
            token = cdp.evaluate(
                "(() => { const els = document.querySelectorAll("
                "'.g-recaptcha-response, [name=g-recaptcha-response]'); "
                "for (const e of els) if (e.value) return e.value; return ''; })()")
            if token:
                print("SUCCESS: reCAPTCHA issued a token (challenge passed).")
                print("token:", token[:40], "...")
            else:
                print("No token yet (headless often escalates to an image grid, "
                      "which needs the optional vision backend).")
            return 0
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
