"""Local OCR solver for image / text / math CAPTCHAs.

Uses RapidOCR (ONNX) under the hood — fully offline, no API key, no external
binary (no tesseract). Good enough for the distorted text CAPTCHAs found on
login forms, newsletter signups, download gates, etc.

CAPTCHA-specific hardening:
  * grayscale + auto-contrast preprocessing (colored backgrounds / faint glyphs)
  * upscaling of small captchas so the detector & recognizer get enough pixels
  * a captcha-tuned ONNX config (lower detection thresholds)
  * fallback to detection-free full-line recognition if detection finds nothing
  * tolerant parsing for all RapidOCR result shapes

The engine is loaded lazily on first use so importing the package stays fast.
"""

from __future__ import annotations

import io
import os
import re
import time
from typing import List, Tuple

from captchabreaker.models import CaptchaType, SolveRequest, SolveResponse
from captchabreaker.solvers.base import Solver, decode_image

# RapidOCR's PaddleOCR backend is heavy to import; defer it.
_engine = None
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "captcha_ocr_config.yaml")


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        _engine = RapidOCR(config_path=_CONFIG_PATH)
    return _engine


def _preprocess(raw: bytes) -> bytes:
    """Grayscale, auto-contrast, and upscale small captchas for OCR robustness."""
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.grayscale(img)
    img = ImageOps.autocontrast(img)
    w, h = img.size
    if max(w, h) < 360:
        scale = max(2, (700 // max(1, max(w, h))))
        img = img.resize((w * scale, h * scale), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


class LocalOCRSolver(Solver):
    def __init__(self):
        self._calls = 0

    def supports(self, type_) -> bool:
        return type_ in (CaptchaType.IMAGE, CaptchaType.TEXT, CaptchaType.MATH)

    def solve(self, req: SolveRequest) -> SolveResponse:
        start = time.perf_counter()
        raw = decode_image(req.image or "")
        if raw is None:
            return SolveResponse.fail(req.type, "could not decode image payload")

        try:
            image, lines, conf = self._ocr(raw)
        except Exception as e:  # noqa: BLE001
            return SolveResponse.fail(req.type, f"OCR failed: {e}")

        answer = self._finalize(req, image, lines)

        self._calls += 1
        duration = (time.perf_counter() - start) * 1000
        if not answer:
            return SolveResponse.fail(req.type, "OCR produced no text",
                                      duration_ms=duration)
        return SolveResponse.ok(req.type, answer, channel="local",
                                confidence=conf, duration_ms=duration)

    # -- internals ---------------------------------------------------------
    def _ocr(self, raw: bytes) -> Tuple[object, List[str], float]:
        """Return (PIL image, recognized lines (left-to-right), mean confidence)."""
        engine = _get_engine()
        pre = _preprocess(raw)
        from PIL import Image
        image = Image.open(io.BytesIO(raw))

        # PRIMARY: whole-line (detection-free) recognition. CAPTCHAs are almost
        # always a single line, and treating the image as one text line avoids the
        # detector's region fragmentation / duplicate boxes. We trust it as long
        # as it produced any text at all (confidence on distorted captchas is
        # routinely low even for correct reads, so keep the bar very low).
        off = self._collect(engine, pre, det=False)
        if off and (sum(e["score"] for e in off) / len(off)) >= 0.12:
            text = "".join(e["text"] for e in off)
            conf = sum(e["score"] for e in off) / len(off)
            return image, [text], conf

        # FALLBACK: region detection, overlap-deduplicated, sorted left-to-right.
        entries = self._collect(engine, pre, det=True)
        entries = self._dedup_boxes(entries)
        entries.sort(key=lambda e: e["x_min"])
        lines = [e["text"] for e in entries]
        conf = (sum(e["score"] for e in entries) / len(entries)) if entries else 0.0
        return image, lines, conf

    @staticmethod
    def _dedup_boxes(entries, iou_thresh: float = 0.45) -> List[dict]:
        """Drop regions whose bounding boxes heavily overlap an already-chosen one.

        RapidOCR occasionally emits duplicate/overlapping boxes (e.g. a character
        detected both as part of a group and individually). We keep the higher-
        confidence region in each overlapping cluster.
        """
        kept = []
        for e in sorted(entries, key=lambda x: -x["score"]):
            box = e.get("box")
            if not box:
                kept.append(e)
                continue
            dup = False
            for k in kept:
                kbox = k.get("box")
                if kbox and _iou(box, kbox) > iou_thresh:
                    dup = True
                    break
            if not dup:
                kept.append(e)
        return kept

    @staticmethod
    def _collect(engine, img_bytes: bytes, det: bool) -> List[dict]:
        """Invoke the engine and normalize rows into dict records.

        RapidOCR result rows come in a few shapes depending on version/config:
            [box_points, 'text', 0.94]        # detection + recognition
            [box_points, ('text', 0.94)]      # legacy nested tuple
            ['text', 0.94]                    # detection-free recognition
        We handle all of them, retaining box + min-x for ordering/dedup.
        """
        result, _ = engine(img_bytes, use_det=det)
        out: List[dict] = []
        if not result:
            return out
        for entry in result:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                continue
            box = None
            text = None
            score = 0.0
            x_min = float("inf")
            try:
                if isinstance(entry[0], (list, tuple)) and entry[0]:
                    box = list(entry[0])
                    try:
                        x_min = min(float(p[0]) for p in box)
                    except (TypeError, ValueError, IndexError):
                        pass
                if isinstance(entry[1], str):
                    text = entry[1]
                    score = float(entry[2]) if len(entry) >= 3 else 0.0
                elif isinstance(entry[1], (list, tuple)) and isinstance(entry[1][0], str):
                    text = entry[1][0]
                    score = float(entry[1][1]) if len(entry[1]) > 1 else 0.0
                elif isinstance(entry[0], str):
                    text = entry[0]
                    score = float(entry[1])
            except (ValueError, TypeError, IndexError):
                continue
            if text is None:
                continue
            out.append({"text": str(text), "score": float(score),
                        "x_min": x_min, "box": box})
        return out

    def _finalize(self, req: SolveRequest, image, lines: List[str]) -> str:
        """Turn OCR lines into the final answer string."""
        if req.type == CaptchaType.MATH:
            # Regions are sorted left-to-right; join them so the math regex can
            # see the whole expression (e.g. "3","+","5" -> "3+5").
            joined = "".join(lines).replace(" ", "").replace("×", "x")
            return _solve_math(joined)
        text = "".join(ch for ch in "".join(lines) if ch.isalnum())
        return text.strip()


# ---------------------------------------------------------------------------
# Math captcha handling ("3 + 5 = ?")
# ---------------------------------------------------------------------------

def _iou(box_a, box_b) -> float:
    """Intersection-over-union for two quad boxes (each a list of [x, y] points)."""
    def bbox(pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    ax1, ay1, ax2, ay2 = bbox(box_a)
    bx1, by1, bx2, by2 = bbox(box_b)
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    return inter / (area_a + area_b - inter)


_OPERATORS = {"+": lambda a, b: a + b,
              "-": lambda a, b: a - b,
              "x": lambda a, b: a * b,
              "X": lambda a, b: a * b,
              "×": lambda a, b: a * b,
              "*": lambda a, b: a * b,
              "/": lambda a, b: a // b}


def _solve_math(text: str) -> str:
    # Normalize: some OCR models emit uppercase X for multiplication.
    text = text.replace("X", "x").replace("×", "x")
    # Try full expression with optional '= ?' or '='
    for pat in (r"(-?\d+)\s*([+\-x*])\s*(-?\d+)\s*=\s*\??",
                r"(-?\d+)\s*([+\-x*])\s*(-?\d+)"):
        m = re.search(pat, text)
        if m:
            a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
            fn = _OPERATORS.get(op)
            if fn:
                return str(fn(a, b))
    return ""
