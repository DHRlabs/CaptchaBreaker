"""Tests for the HumanPass module (motion engine, CDP client, passer, vision).

Pure logic is tested directly. CDP/vision/passer I/O is tested against fakes —
no live Chrome required.
"""

import math

import pytest


# ---------------------------------------------------------------------------
# motion engine
# ---------------------------------------------------------------------------
def test_trajectory_starts_and_ends_exactly():
    from captchabreaker.humanpass.motion import human_trajectory
    frames = human_trajectory(10, 10, 300, 200, seed=1)
    assert frames[0][1:] == (10.0, 10.0)      # begins at origin
    assert frames[-1][1:] == (300.0, 200.0)   # ends precisely on target
    assert len(frames) >= 3


def test_trajectory_is_seeded_deterministic():
    from captchabreaker.humanpass.motion import human_trajectory
    a = human_trajectory(0, 0, 150, 80, seed=42)
    b = human_trajectory(0, 0, 150, 80, seed=42)
    assert a == b


def test_trajectory_moves_toward_target():
    from captchabreaker.humanpass.motion import human_trajectory
    frames = human_trajectory(0, 0, 200, 0, seed=7)
    # Path may overshoot slightly (human overshoot) but stays in sane bounds.
    xs = [x for _, x, _ in frames]
    assert all(-40 <= x <= 235 for x in xs)


def test_tiny_move_still_lands():
    from captchabreaker.humanpass.motion import human_trajectory
    frames = human_trajectory(5, 5, 6, 7, seed=1)
    assert frames[-1][1:] == (6.0, 7.0)


def test_typing_intervals_have_jitter():
    from captchabreaker.humanpass.motion import human_type_intervals
    ivl = human_type_intervals("hello world", seed=1)
    assert len(ivl) == len("hello world")
    assert all(i > 0 for i in ivl)
    assert len(set(ivl)) > 1  # jittery, not uniform


def test_scroll_steps_sum_and_pause():
    from captchabreaker.humanpass.motion import human_scroll_steps
    steps = human_scroll_steps(1000, seed=1)
    assert sum(abs(d) for d, _ in steps) == 1000
    assert all(d > 0 for d, _ in steps)
    # negative scroll preserved
    neg = human_scroll_steps(-500, seed=2)
    assert sum(d for d, _ in neg) == -500


# ---------------------------------------------------------------------------
# CDP client (against a fake transport)
# ---------------------------------------------------------------------------
class FakeWS:
    def __init__(self, responses):
        self._responses = list(responses)
        self.sent = []
        self.closed = False

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        return self._responses.pop(0)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_cdp(monkeypatch):
    import websocket  # noqa: F401  (required for the client)
    resp = '{"id":1,"result":{"value":42}}'
    fake = FakeWS([resp])
    monkeypatch.setattr("websocket.create_connection", lambda *a, **k: fake)
    from captchabreaker.humanpass.cdp import CDPClient
    client = CDPClient("ws://fake")
    return client, fake


def test_cdp_command_roundtrip(fake_cdp):
    import json as _j
    client, fake = fake_cdp
    assert client.command("Runtime.evaluate", {"expression": "1+1"}) == {"value": 42}
    msg = _j.loads(fake.sent[0])
    assert msg["id"] == 1 and msg["method"] == "Runtime.evaluate"


def test_cdp_raises_on_error(monkeypatch):
    import websocket  # noqa
    resp = '{"id":1,"error":{"message":"boom"}}'
    monkeypatch.setattr("websocket.create_connection", lambda *a, **k: FakeWS([resp]))
    from captchabreaker.humanpass.cdp import CDPClient, CDPError
    c = CDPClient("ws://fake")
    with pytest.raises(CDPError):
        c.command("Runtime.evaluate", {})


def test_cdp_mouse_and_close(fake_cdp):
    import json as _j
    client, fake = fake_cdp
    client.mouse_move(10, 20)
    msg = _j.loads(fake.sent[-1])
    assert msg["method"] == "Input.dispatchMouseEvent"
    assert msg["params"]["x"] == 10 and msg["params"]["y"] == 20
    client.close()
    assert fake.closed


# ---------------------------------------------------------------------------
# HumanPass coordination (against a fake CDP)
# ---------------------------------------------------------------------------
class FakeCDP:
    """Serves a fixed sequence of detect() states; counts issued input."""

    def __init__(self, detections):
        self.detections = list(detections)
        self.moves = []
        self.downs = []
        self.ups = []
        self._n = 0

    def evaluate(self, js):
        if "innerWidth" in js or "innerHeight" in js:
            return {"w": 800, "h": 600}
        i = min(self._n, len(self.detections) - 1)
        self._n += 1
        return self.detections[i]

    def mouse_move(self, x, y, buttons=0):
        self.moves.append((x, y))

    def mouse_down(self, x, y, button="left"):
        self.downs.append((x, y))

    def mouse_up(self, x, y, button="left"):
        self.ups.append((x, y))

    def screenshot(self):
        return b"png-bytes"


_BOX = {"found": True, "box": {"cx": 120.0, "cy": 60.0, "x": 100, "y": 50,
        "w": 40, "h": 20, "tag": "iframe"}, "token": "", "phrases": True}


def test_pass_captcha_absent_returns_true():
    from captchabreaker.humanpass.passer import HumanPass
    hp = HumanPass(FakeCDP([{"found": False, "box": None, "token": "",
                             "phrases": False}]), seed=1)
    assert hp.pass_captcha() is True
    assert hp.cdp.downs == []  # didn't click anything
    assert hp.last_outcome == "absent"


def test_pass_captcha_click_clears_widget(monkeypatch):
    from captchabreaker.humanpass.passer import HumanPass
    cleared = dict(_BOX, token="tok123")
    cdp = FakeCDP([_BOX, cleared])
    hp = HumanPass(cdp, seed=1, vision=False)
    monkeypatch.setattr("captchabreaker.humanpass.passer.time.sleep", lambda s: None)
    assert hp.pass_captcha() is True
    assert hp.last_outcome == "cleared"
    assert len(cdp.downs) == 1          # one hover-dwell click on the widget
    assert cdp.downs[0][0] == 120.0
    assert len(cdp.moves) > 1           # human trajectory had multiple frames


def test_pass_captcha_still_blocking_returns_false(monkeypatch):
    from captchabreaker.humanpass.passer import HumanPass
    cdp = FakeCDP([_BOX, _BOX])  # still blocking after the click
    hp = HumanPass(cdp, seed=1, vision=False)
    monkeypatch.setattr("captchabreaker.humanpass.passer.time.sleep", lambda s: None)
    assert hp.pass_captcha() is False
    assert hp.last_outcome == "still_blocking"
    assert len(cdp.downs) == 1


# ---------------------------------------------------------------------------
# CommandAdapter (wrapping an existing duck-typed CDP session)
# ---------------------------------------------------------------------------
class _FakeCommandSession:
    def __init__(self):
        self.calls = []
        self._eval_value = {"w": 800, "h": 600}

    def command(self, method, params=None):
        self.calls.append((method, params))
        if method == "Runtime.evaluate":
            return {"result": {"type": "object", "value": self._eval_value}}
        if method == "Page.captureScreenshot":
            import base64
            return {"data": base64.b64encode(b"PNG").decode()}
        return {}


def test_command_adapter_evaluate_and_mouse():
    from captchabreaker.humanpass.adapter import CommandAdapter
    sess = _FakeCommandSession()
    ada = CommandAdapter(sess)
    assert ada.evaluate("1+1") == {"w": 800, "h": 600}
    assert sess.calls[0][0] == "Runtime.evaluate"
    ada.mouse_move(10, 20)
    assert sess.calls[-1][0] == "Input.dispatchMouseEvent"
    assert sess.calls[-1][1]["x"] == 10.0
    shot = ada.screenshot()
    assert shot == b"PNG"


def test_command_adapter_requires_command_attr():
    from captchabreaker.humanpass.adapter import CommandAdapter
    import pytest as _pt
    with _pt.raises(TypeError):
        CommandAdapter(object())


# ---------------------------------------------------------------------------
# vision solver (against a mocked HTTP client)
# ---------------------------------------------------------------------------
def test_vision_disabled_returns_empty(monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from captchabreaker.humanpass import vision as v
    assert v.vision_enabled() is False
    assert v.solve_image_with_vision(b"x") == {}


class _Resp:
    def raise_for_status(self): pass
    def json(self):
        return {"choices": [{"message": {"content":
            '```json\n{"clicks": [[5,6],[120,80]]}\n```'}}]}


def test_vision_parses_clicks(monkeypatch):
    monkeypatch.setenv("VISION_API_KEY", "k")
    monkeypatch.setenv("VISION_MODEL", "m")
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp())
    from captchabreaker.humanpass import vision as v
    assert v.vision_enabled() is True
    out = v.solve_image_with_vision(b"png")
    assert out.get("clicks") == [[5, 6], [120, 80]]
