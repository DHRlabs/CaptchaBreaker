# CaptchaBreaker — self-contained CAPTCHA-solving service.
# Build:   docker build -t captchabreaker .
# Run:     docker run -p 127.0.0.1:8977:8977 captchabreaker
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CAPTCHABREAKER_PORT=8977 \
    CAPTCHABREAKER_HOST=0.0.0.0

WORKDIR /app

# System libraries required by the OCR stack (opencv + onnxruntime) at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install the package (base deps only; the OCR engine downloads its ONNX models
# on first use, which we pre-fetch in the next layer so runtime stays offline).
COPY pyproject.toml README.md ./
COPY captchabreaker ./captchabreaker
RUN pip install .
RUN python -c "from captchabreaker.solvers.image_ocr import _get_engine; _get_engine(); print('OCR models cached')"

# The HTTP API is the primary interface for agents.
EXPOSE 8977
CMD ["python", "-m", "captchabreaker.server"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/status'%os.getenv('CAPTCHABREAKER_PORT','8977'))" || exit 1
