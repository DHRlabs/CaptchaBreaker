"""Human-like pointer motion + input timing.

This is the "hand" of HumanPass: it turns a desire to click (x, y) / type text /
scroll into realistic human motor behavior — curved paths with acceleration and
deceleration, micro-jitter, slight overshoot, hesitation, and natural inter-key
timing. Browser anti-bot classifiers score heavily on these signals, and a real
human session is genuinely simulable.

All functions are pure (no I/O) so they are deterministic-testable.
"""

from __future__ import annotations

import math
import random
import time
from typing import Iterable, List, Optional, Tuple

Frame = Tuple[float, float, float]  # (delay_ms, x, y)


def _rng(seed) -> random.Random:
    if seed is None:
        return random.Random()
    return random.Random(seed)


# ---------------------------------------------------------------------------
# Trajectory
# ---------------------------------------------------------------------------

def _bezier(p0, p1, p2, p3, t):
    """Cubic Bezier point."""
    u = 1 - t
    return (u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1])


def _ease(t: float) -> float:
    """Asymmetric S-curve: slower start, faster mid, decelerating end."""
    # cubic ease-in-out is symmetric; add slight asymmetry for inertia feel.
    eased = 3 * t**2 - 2 * t**3
    if t < 0.5:
        scaled = eased * 1.10
    else:
        scaled = eased * 0.96 + 0.04
    return max(0.0, min(1.0, scaled))


def human_trajectory(x0: float, y0: float, x1: float, y1: float,
                     *,
                     seed: Optional[int] = None,
                     duration_ms: Optional[float] = None,
                     overshoot: bool = True) -> List[Frame]:
    """Return a realistic human mouse path from (x0,y0) to (x1,y1).

    Produces a frame list of (delay_ms, x, y) at ~60 Hz that starts exactly at
    the origin and ends exactly at the destination. The path is an eased Bezier
    curve with curvature, micro-jitter (largest mid-flight, smallest on landing),
    and optional slight overshoot for longer moves.
    """
    rng = _rng(seed)
    dist = math.hypot(x1 - x0, y1 - y0)

    if dist < 3.0:
        return [(0.0, x1, y1)]

    # Humans never move in a perfectly straight line: deflect control points.
    # The deflection is proportional to the movement length but bounded.
    deflection = max(8.0, dist * rng.uniform(0.12, 0.28))
    ang = rng.uniform(-math.pi / 2, math.pi / 2)
    mid = ((x0 + x1) / 2, (y0 + y1) / 2)
    p1 = (mid[0] - deflection * math.cos(ang), mid[1] - deflection * math.sin(ang))
    p2 = (mid[0] + deflection * math.cos(ang), mid[1] + deflection * math.sin(ang))
    p0, p3 = (x0, y0), (x1, y1)

    # Duration scales with distance but with per-move human variance.
    if duration_ms is None:
        duration_ms = max(260.0, min(950.0, 180 + dist * 0.55 + rng.uniform(0, 140)))

    dt = 16.7  # ~60 Hz
    n = max(2, int(duration_ms / dt))

    # Optional overshoot: treat the real destination as slightly beyond, then
    # settle back. Only for non-trivial moves.
    overshoot_by = 0.0
    if overshoot and dist > 90 and rng.random() < 0.55:
        overshoot_by = min(14.0, dist * 0.10)
        ux, uy = (x1 - x0) / dist, (y1 - y0) / dist
        p3 = (x1 + ux * overshoot_by, y1 + uy * overshoot_by)

    frames: List[Frame] = []
    for i in range(n):
        t = i / (n - 1)
        et = _ease(t)
        x, y = _bezier(p0, p1, p2, p3, et)
        # Micro-jitter with a sine envelope: zero at both ends (precise start /
        # landing, like real hands) and peaking mid-flight.
        jitter = rng.gauss(0, 1.6 * math.sin(math.pi * t))
        frames.append((dt, x + jitter, y + jitter))

    # Guarantee exact arrival (real users end precisely on target).
    frames.append((dt, x1, y1))
    return frames


# ---------------------------------------------------------------------------
# Typing
# ---------------------------------------------------------------------------

def human_type_intervals(text: str, *, seed: Optional[int] = None,
                         base_interval: Tuple[float, float] = (60, 150)) -> List[float]:
    """Per-character inter-key delays (ms) that look human.

    Typing is jittery, has occasional hesitation, and pauses at word boundaries.
    """
    rng = _rng(seed)
    out: List[float] = []
    for i, ch in enumerate(text):
        lo, hi = base_interval
        if ch == " ":
            lo, hi = lo * 2.2, hi * 2.2
        ivl = rng.uniform(lo, hi)
        # Periodic hesitation spikes (~6% of chars).
        if rng.random() < 0.06:
            ivl += rng.uniform(150, 400)
        out.append(ivl)
    return out


# ---------------------------------------------------------------------------
# Scrolling
# ---------------------------------------------------------------------------

def human_scroll_steps(total_delta_y: int, *, seed: Optional[int] = None,
                       max_step: int = 240) -> List[Tuple[int, float]]:
    """Split a scroll into human-like wheel increments with pauses.

    Returns [(delta_y, pause_ms), ...] summing to total_delta_y (signed), with
    variable step sizes and micro-pauses between, as a real Scroller would.
    """
    rng = _rng(seed)
    signed = 1 if total_delta_y >= 0 else -1
    remaining = abs(total_delta_y)
    steps: List[Tuple[int, float]] = []
    while remaining > 0:
        step = int(min(remaining, rng.uniform(60, max_step)))
        step = max(1, step)  # never emit a 0-px wheel event, never overshoot
        # Occasionally a longer dwell (human reads/judges), otherwise a short pause.
        pause = rng.uniform(140, 420) if rng.random() < 0.25 else rng.uniform(30, 80)
        steps.append((signed * step, pause))
        remaining -= step
    return steps


# Convenience: play a trajectory with real wall-clock sleeps (for use by fail-soft)
def play_frames(frames: Iterable[Frame], emit) -> None:
    """Emit each frame and sleep its delay. `emit(x, y)` performs the mouse move."""
    for delay_ms, x, y in frames:
        emit(x, y)
        if delay_ms:
            time.sleep(delay_ms / 1000.0)
