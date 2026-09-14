# CaptchaBreaker

A self-contained, local-first CAPTCHA-solving service for LLM agents and programs that puppeteer browsers.

Your agents run into CAPTCHAs all day (job applications, signups, searches). CaptchaBreaker gives them **one local endpoint** they can call to get the answer — no Chrome extension surgery or account juggling.

It has two capabilities, with local behavior as the default:

| Task | Backend | Cost | API key? |
|---|---|---|---|
| Image / text / math (distorted-text CAPTCHAs) | Local ONNX OCR engine (`RapidOCR`) | free | **no** — works offline |
| reCAPTCHA v2/v3, hCaptcha, Turnstile checkboxes | HumanPass behavioral click-through | free locally | **no by default**; optional vision opt-in |

The default paths need no cloud provider. Image CAPTCHAs are solved offline by OCR; browser-level "I am not a robot" widgets are cleared by HumanPass moving a real cursor like a person does. An explicitly enabled external vision backend can handle image-grid challenges.

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
```

Interactive docs are auto-served at `http://127.0.0.1:8977/docs`.

## Interface 2 — Python SDK (in-process, no HTTP)

```python
from captchabreaker import solve_image, solve_math

answer, ok = solve_image("/tmp/captcha.png")      # (str, bool)
answer, ok = solve_math("/tmp/math.png")
```

## Interface 3 — CLI

```bash
captchabreaker status
captchabreaker solve image captcha.png
captchabreaker solve math captcha.png
```

## Puppeteer (Node) example

See `examples/agent_example.js` — screenshot the captcha element, POST the base64,
type the returned answer into the page.

## Configuration

CaptchaBreaker needs **no configuration** for its local defaults. Copy `.env.example` → `.env` only
if you want to change the server bind, port, debug logging, or opt into external vision:

| Env var | Purpose |
|---|---|
| `CAPTCHABREAKER_HOST` | server bind (default `127.0.0.1`; Docker uses `0.0.0.0` inside the container) |
| `CAPTCHABREAKER_PORT` | local server port (default 8977) |
| `CAPTCHABREAKER_DEBUG` | debug logging |
| `VISION_ENABLED` | set to `1` to opt into external vision requests (off by default) |
| `VISION_BASE_URL` / `VISION_API_KEY` / `VISION_MODEL` | optional vision endpoint, key, and model; used after opt-in |

The `HumanPass` caller can override the environment with `vision=True` or
`vision=False`. An explicit `vision=True` still requires a configured key; the
`OPENAI_*` fallbacks are used only after that caller opt-in.

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
    base.py        # input decoding (base64 / file / data: URL)
  humanpass/
    motion.py      # human-like mouse trajectory + typing/scroll timing
    cdp.py         # minimal Chrome DevTools Protocol client (WebSocket)
    passer.py      # finds & human-clicks CAPTCHA widgets; verifies the pass
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
"prove you are human" widgets. Its motion engine emits realistic paths (resting
cursor, then a quick press — the pattern that reads as human, not scripted).

`pass_captcha()` now **verifies** the result: it re-checks the page after clicking
to confirm the challenge cleared (a response token is present or the widget is
gone) before reporting success. It returns `True` when nothing is blocking (no
CAPTCHA, already cleared, or successfully cleared) and `False` when a genuine
challenge is still blocking — so the caller can fall back honestly instead of
quietly continuing past a window that never opened.

```python
from captchabreaker.humanpass import CDPClient, HumanPass

with CDPClient(find_ws_url_for("http://127.0.0.1:9222")) as cdp:
    hp = HumanPass(cdp)
    if hp.pass_captcha():            # cleared (or nothing to pass)
        ...
    else:
        print(hp.last_outcome)        # e.g. "still_blocking"
```

Requires the `[browser]` extra (`pip install captchabreaker[browser]`), launches
Chrome with `--remote-allow-origins=*`. Vision is optional and fully pluggable:
set `VISION_ENABLED=1` plus `VISION_BASE_URL` / `VISION_API_KEY` / `VISION_MODEL`
to have it screenshot an image-grid challenge and click the correct tiles.
Without vision it degrades to
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
(e.g. reads `000` from `000ju`) — enough for an agent to submit and retry.

Re-run the benchmark:
```bash
.venv/bin/python scripts/benchmark_real.py --sample 40
```

## Deployment — Docker

```bash
docker build -t captchabreaker .
docker run -p 127.0.0.1:8977:8977 captchabreaker  # or: docker compose up
```

The container listens on its interfaces while the published host port stays
local-only. It exposes the HTTP API on port 8977 with a `/status` healthcheck.
The OCR models are pre-fetched at image build time so the default runtime works offline.

## Run the tests

```bash
.venv/bin/python -m pytest -q
```

`tests/` generate synthetic captcha images via `examples/make_test_images.py`
and verify the local OCR backend solves them end-to-end.
