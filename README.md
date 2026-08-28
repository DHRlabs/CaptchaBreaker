# CaptchaBreaker

A self-contained CAPTCHA-solving service for LLM agents and programs that puppeteer browsers.

Your agents run into CAPTCHAs all day (job applications, signups, searches). CaptchaBreaker gives
them **one local endpoint** they can call to get the answer — no Chrome extension surgery, no
account juggling.

It has **two solving backends**, chosen automatically by captcha type:

| Captcha family | Backend | Cost | API key? |
|---|---|---|---|
| Image / text / math (distorted-text CAPTCHAs) | Local ONNX OCR engine (`RapidOCR`) | free | **no** — works offline |
| reCAPTCHA v2/v3, hCaptcha, Turnstile, FunCaptcha, GeeTest | Cloud provider (CapSolver / 2Captcha / CapMonster / RuCaptcha) | per-solve (~$1–3 / 1k) | yes — optional |

If no API key is set)Skip and a network CAPTCHA arrives,Skip it returns a graceful "unconfigured" response
so your agent can fall back to its own retry logic instead of erroring.

---

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/captchabreaker serve        # starts HTTP API on http://127.0.0.1:8977
```

That's it for image CAPTCHAs — no keys, no internet required.

## Interface 1 — HTTP API (for agents in any language)

```bash
# Image captcha: POST base64 of the screenshot
curl -X POST http://127.0.0.1:8977/solve \
  -H 'content-type: application/json' \
  -d '{"type":"image","image":"<base64-or-path>"}'
# -> {"success":true,"channel":"local","solution":"K7PM2Q","confidence":0.98,...}

# Math captcha
curl -X POST http://127.0.0.1:8977/solve/math -d '{"image":"/tmp/cap.png"}'

# Network captcha (needs CAPTCHABREAKER_API_KEY)
curl -X POST http://127.0.0.1:8977/solve \
  -d '{"type":"recaptcha_v2","sitekey":"6Lc...","page_url":"https://site.com"}'
```

Interactive docs are auto-served at `http://127.0.0.1:8977/docs`.

## Interface 2 — Python SDK (in-process, no HTTP)

```python
from captchabreaker import solve_image, solve_math, solve_network

answer, ok = solve_image("/tmp/captcha.png")      # (str, bool)
answer, ok = solve_math("/tmp/math.png")
resp = solve_network("recaptcha_v2", "6Lc...", "https://site.com")
```

## Interface 3 — CLI

```bash
captchabreaker status
captchabreaker solve image captcha.png
captchabreaker solve math captcha.png
captchabreaker recaptcha 6Lc... https://site.com
```

## Puppeteer (Node) example

See `examples/agent_example.js` — screenshot the captcha element, POST the base64,
type the returned answer into the page.

## Configuration

Copy `.env.example` → `.env`. Only the provider key is ever required, and only for
network CAPTCHAs:

| Env var | Purpose |
|---|---|
| `CAPTCHABREAKER_PROVIDER` | capsolver (default) · 2captcha · capmonster · rucaptcha |
| `CAPTCHABREAKER_API_KEY` | provider key for reCAPTCHA/hCaptcha/etc. |
| `CAPTCHABREAKER_HOST` | override provider host |
| `CAPTCHABREAKER_TIMEOUT` | poll timeout for network solves (s) |
| `CAPTCHABREAKER_PORT` | local server port (default 8977) |

## Project layout

```
captchabreaker/
  server.py        # FastAPI HTTP service (agents' primary interface)
  client.py        # Python SDK (in-process + remote client)
  cli.py           # command-line interface
  config.py        # env/.env configuration
  models.py        # request/response schemas
  captcha_ocr_config.yaml  # OCR detection thresholds tuned for CAPTCHAs
  solvers/
    image_ocr.py   # free, offline OCR for image/text/math
    network.py     # CapSolver/2Captcha-style provider protocol
    base.py        # input decoding (base64 / file / data: URL)
  humanpass/
    motion.py      # human-like mouse trajectory + typing/scroll timing
    cdp.py         # minimal Chrome DevTools Protocol client (WebSocket)
    passer.py      # finds & human-clicks CAPTCHA widgets; drives grids via vision
    vision.py      # optional OpenAI-compatible vision solver (click coords/text)
examples/          # agent examples (Py + Puppeteer), captcha + human_pass demos
scripts/benchmark_real.py   # accuracy benchmark vs real labeled CAPTCHAs
tests/             # pytest suite
Dockerfile / docker-compose.yml   # container deployment
```

## HumanPass — get past "I am not a robot" in the live browser

CaptchaBreaker's solvers handle captcha *images*. **HumanPass** handles the
browser-level challenge: it drives a real Chrome (over CDP, no Playwright) and
moves the cursor like a human to click through reCAPTCHA / hCaptcha / Turnstile /
"prove you are human" widgets. Its motion engine emits realistic paths (Bezier
curves with acceleration, micro-jitter, overshoot, human timing) — the signals
anti-bot classifiers actually score on.

```python
from captchabreaker.humanpass import CDPClient, HumanPass

with CDPClient(find_ws_url_for("http://127.0.0.1:9222")) as cdp:
    hp = HumanPass(cdp)
    if hp.pass_captcha():        # found & clicked the widget human-ly
        ...
```

Requires the `[browser]` extra (`pip install captchabreaker[browser]`), launches
Chrome with `--remote-allow-origins=*`. Vision is optional and fully pluggable:
set `VISION_BASE_URL` / `VISION_API_KEY` / `VISION_MODEL` to have it screenshot an
image-grid challenge and click the correct tiles. Without vision it degrades to
the silent behavioral checkbox path (which passes most v2/v3 challenges).

Live demo (spawns its own headless Chrome, no interference with your scrapers):
```bash
.venv/bin/python examples/human_pass_demo.py
```

## Real-world accuracy (local OCR)

The local OCR engine is free and offline but, honestly, it does **not** crack heavily
distorted CAPTCHAs reliably on its own. Benchmarked against a real labeled dataset
(30–40 images from `nakasyou/captcha-like-suica` on HuggingFace):

| Metric | Result |
|---|---|
| Exact match | ~7% |
| Per-character accuracy | ~43% |
| Reads ≥60% of chars correctly | ~half of images |

It fully solves clean/light captchas and returns **partial answers** on hard ones
(e.g. reads `000` from `000ju`) — enough for an agent to submit and retry. For sites
with serious distortion, use the paid provider (#2 below) for reliable solves.

Re-run the benchmark:
```bash
.venv/bin/python scripts/benchmark_real.py --sample 40
```

## Deployment — Docker

```bash
docker build -t captchabreaker .
docker run -p 8977:8977 captchabreaker          # or: docker compose up
```

The container exposes the HTTP API on port 8977 with a `/status` healthcheck. The
OCR models are pre-fetched at image build time so the runtime works offline.

## Configure the paid provider (reCAPTCHA / hCaptcha / Turnstile)

The local OCR only handles image/text/math captchas. For the browser-level
challenges (reCAPTCHA v2/v3, hCaptcha, Turnstile), set a provider key. These are
third-party cloud services that solve them for you:

```bash
export CAPTCHABREAKER_API_KEY=your_key_here      # from 2Captcha / CapSolver / etc.
export CAPTCHABREAKER_PROVIDER=capsolver         # optional, default
```

Then an agent just sends the page's `sitekey` + `page_url` and receives a token
to inject into the page. See `.env.example`.

## Run the tests

```bash
.venv/bin/python -m pytest -q
```

`tests/` generate synthetic captcha images via `examples/make_test_images.py`
and verify the local OCR backend solves them end-to-end.
