#!/usr/bin/env python
"""Example: how a Python puppeteering agent uses the CaptchaBreaker SDK.

Two ways shown:
  1. In-process SDK (fastest for Python agents).
  2. HTTP API (for agents in another process/language).
"""
import base64
import sys

# Option 1: in-process SDK ------------------------------------------------
from captchabreaker import solve_image, solve_math, solve_network

def demo_sdk(captcha_path: str):
    print("=== SDK: local image captcha ===")
    answer, ok = solve_image(captcha_path)
    print(f"  OCR result: {answer!r}  success={ok}")

    print("=== SDK: math captcha ===")
    answer, ok = solve_math(captcha_path)  # (would be a different image in real life)
    print(f"  math result: {answer!r}  success={ok}")

    print("=== SDK: reCAPTCHA via network provider (needs API key) ===")
    resp = solve_network("recaptcha_v2", "6LcMyJwUAAAAAG3tW", "https://example.com")
    print(f"  {resp.channel}: {resp.solution!r}")

# Option 2: HTTP API --------------------------------------------------------
def demo_http(captcha_path: str):
    import httpx
    b64 = base64.b64encode(open(captcha_path, "rb").read()).decode()
    print("=== HTTP: POST /solve ===")
    r = httpx.post("http://127.0.0.1:8977/solve",
                   json={"type": "image", "image": b64}, timeout=60)
    print(" ", r.json())

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "examples/sample_captcha.png"
    demo_sdk(path)
    demo_http(path)
