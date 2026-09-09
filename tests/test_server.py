"""Tests for the HTTP API server using FastAPI TestClient."""

import base64
import importlib

import pytest
from fastapi.testclient import TestClient
from captchabreaker.server import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_registry():
    from captchabreaker.solvers import registry
    registry._cache.clear()
    registry.cache_hits = 0
    yield


def test_status(client):
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_solve_invalid_payload(client):
    r = client.post("/solve", json={"type": "image", "image": "not-an-image"})
    assert r.status_code == 200
    body = r.json()
    # 'not-an-image' isn't valid base64 but IS a valid "path"-like token;
    # decode_image may treat as b64 (fails) -> OCR error, or file-not-found.
    # Either way the response must be a well-formed SolveResponse.
    assert "success" in body and body["type"] == "image"


def test_solve_image_with_generated_png(client):
    import subprocess, sys
    subprocess.run([sys.executable, "examples/make_test_images.py"], check=True)
    raw = open("examples/sample_captcha.png", "rb").read()
    b64 = base64.b64encode(raw).decode()
    r = client.post("/solve", json={"type": "image", "image": b64})
    body = r.json()
    assert body["success"] is True, body
    assert body["channel"] == "local"
    assert body["solution"].isalnum()


def test_unknown_type(client):
    r = client.post("/solve/notarealtype", json={})
    assert r.status_code == 200
    assert r.json()["success"] is False
