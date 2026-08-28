#!/usr/bin/env python
"""Benchmark the local OCR solver against REAL labeled CAPTCHAs.

Pulls a sample of images from the public HF dataset `nakasyou/captcha-like-suica`
(filename convention: <label>-<rand>.gif), runs the local solver on each, and
reports exact-match and per-character accuracy. No external labels needed —
the answer is encoded in the filename.

Usage:
    .venv/bin/python scripts/benchmark_real.py --sample 30
"""
from __future__ import annotations

import argparse
import io
import json
import os
import urllib.request
from pathlib import Path

from PIL import Image

from captchabreaker import solve_image

HF_DATASET = "nakasyou/captcha-like-suica"
HF_API = "https://huggingface.co/api/datasets"
HF_RESOLVE = "https://huggingface.co/datasets"

CACHE_DIR = Path(__file__).resolve().parent.parent / "examples" / "real"


def http_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "captchabreaker-bench/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def list_dirs() -> list[str]:
    """Top-level captcha directories (00, 01, ...)."""
    return [d["path"] for d in http_json(f"{HF_API}/{HF_DATASET}/tree/main")
            if d.get("type") == "directory"]


def list_images(limit_dirs: int = 12) -> list[str]:
    """Collect .gif image paths from the first `limit_dirs` directories."""
    paths: list[str] = []
    for d in list_dirs()[:limit_dirs]:
        entries = http_json(f"{HF_API}/{HF_DATASET}/tree/main/{d}")
        for e in entries:
            p = e.get("path", "")
            if p.lower().endswith(".gif"):
                paths.append(p)
    return paths


def label_from_path(path: str) -> str:
    """filename convention: <label>-<rand>.gif  ->  label before the first '-'."""
    name = Path(path).stem          # e.g. 000ju-95746
    return name.split("-", 1)[0]


def fetch_image(path: str, timeout: int = 30) -> bytes:
    url = f"{HF_RESOLVE}/{HF_DATASET}/resolve/main/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "captchabreaker-bench/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def char_accuracy(pred: str, truth: str) -> float:
    """Fraction of character positions correct (case-insensitive)."""
    pred, truth = pred.lower().ljust(len(truth)), truth.lower()
    if len(truth) == 0:
        return 0.0
    return sum(a == b for a, b in zip(pred, truth)) / len(truth)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=25, help="images to test")
    ap.add_argument("--dirs", type=int, default=12, help="directories to scan")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    paths = list_images(args.dirs)
    # Deterministic spread across the sample.
    step = max(1, len(paths) // args.sample)
    sample = paths[::step][: args.sample]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sample:
        truth = label_from_path(path)
        try:
            data = fetch_image(path)
        except Exception as e:  # noqa: BLE001
            print(f"  [fetch fail] {path}: {e}")
            continue
        # base64-encode first (the SDK image field is a b64/path string)
        import base64
        pred, ok = solve_image("data:image/gif;base64," + base64.b64encode(data).decode())
        results.append({
            "image": path,
            "truth": truth,
            "pred": pred,
            "ok": ok,
            "char_acc": char_accuracy(pred, truth),
            "exact": pred.strip().lower() == truth.strip().lower(),
        })

    if not results:
        print("no images tested")
        return 1

    n = len(results)
    exact = sum(1 for r in results if r["exact"])
    char_acc = sum(r["char_acc"] for r in results) / n
    first3 = sum(1 for r in results if r["char_acc"] >= 0.6)

    if args.json:
        print(json.dumps({"tested": n, "exact": exact,
                          "exact_rate": round(exact / n, 3),
                          "char_accuracy": round(char_acc, 3),
                          "near_miss_60pct": first3,
                          "results": results}, indent=2))
        return 0

    print(f"\n=== REAL CAPTCHA BENCHMARK ===")
    print(f"tested    : {n}")
    print(f"exact     : {exact}  ({exact / n:.1%})")
    print(f"char acc  : {char_acc:.1%}")
    print(f"ge 60%    : {first3} images")
    print("-" * 46)
    for r in results:
        mark = "OK " if r["exact"] else "   "
        print(f"{mark} {r['image']:<28} truth={r['truth']:<6} pred={r['pred']:<6} char={r['char_acc']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
