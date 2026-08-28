"""Base solver interfaces and image input helpers."""

from __future__ import annotations

import base64
import io
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from captchabreaker.models import SolveRequest, SolveResponse


class Solver(ABC):
    @abstractmethod
    def solve(self, req: SolveRequest) -> SolveResponse:
        ...

    # -- capability --------------------------------------------------------
    def supports(self, type_) -> bool:
        return True


def decode_image(image: str, max_bytes: int = 8 * 1024 * 1024) -> Optional[bytes]:
    """Decode an image payload into raw bytes.

    Accepts:
      * base64 data
      * data: URL  (data:image/png;base64,....)
      * a filesystem path
      * a http(s) URL (fetched... actually left to caller via load_image)
    Returns None if it can't determine the source.
    """
    if not image:
        return None

    s = image.strip()

    # data: URL
    if s.startswith("data:"):
        try:
            _, b64 = s.split(",", 1)
            return base64.b64decode(b64)
        except Exception:
            return None

    # Plain base64 (common: agents screenshot to clipboard-style base64)
    if _looks_like_base64(s):
        try:
            return base64.b64decode(s)
        except Exception:
            return None

    # Filesystem path
    p = Path(s)
    if p.exists() and p.is_file():
        try:
            return p.read_bytes()
        except OSError:
            return None

    return None


def _looks_like_base64(s: str, min_len: int = 16) -> bool:
    if len(s) < min_len:
        return False
    # Guard: a path like "C:\x.png" or "/tmp/x.png" shouldn't be treated as b64.
    if "/" in s and "." in s.split("/")[-1]:
        return False
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n")
    return all(c in allowed for c in s)
