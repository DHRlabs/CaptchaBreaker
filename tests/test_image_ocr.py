"""Tests for the local OCR solver and math handling."""

import importlib

import pytest


def _load_image(name: str):
    from pathlib import Path
    return str(Path("examples") / name)


@pytest.fixture(autouse=True)
def _reset_registry():
    from captchabreaker.solvers import registry
    registry._cache.clear()
    registry.cache_hits = 0
    yield


def test_image_captcha_end_to_end():
    """Generate a captcha and solve it with the local OCR backend."""
    import subprocess, sys
    from captchabreaker import solve_image

    # ensure sample images exist
    subprocess.run([sys.executable, "examples/make_test_images.py"], check=True)

    answer, ok = solve_image(_load_image("sample_captcha.png"))
    assert ok, f"OCR failed: {answer}"
    # K7pM2Q — allow minor misreads but require correct chars mostly
    normalized = "".join(ch for ch in answer if ch.isalnum())
    assert normalized == "K7pM2Q"


def test_math_solver():
    from captchabreaker.solvers.image_ocr import _solve_math
    assert _solve_math("3 + 5 = ?") == "8"
    assert _solve_math("12 x 4 = ?") == "48"
    assert _solve_math("7 - 2 = ?") == "5"
    assert _solve_math("3+5=?") == "8"          # compact, no spaces
    assert _solve_math("12X4") == "48"          # uppercase X multiplication


def test_math_image_end_to_end():
    import subprocess, sys
    from captchabreaker import solve_math
    subprocess.run([sys.executable, "examples/make_test_images.py"], check=True)

    answer, ok = solve_math(_load_image("sample_math.png"))
    assert ok
    assert answer == "8"


def test_decode_image_helpers():
    from captchabreaker.solvers.base import decode_image
    import base64
    raw = b"fake-png-bytes"
    b64 = base64.b64encode(raw).decode()
    assert decode_image(b64) == raw
    assert decode_image(f"data:image/png;base64,{b64}") == raw
    assert decode_image("data:image/png;base64," + base64.b64encode(b"\x00").decode()) == b"\x00"
