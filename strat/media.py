"""Audio and video into sources. (Phase 2)"""

from __future__ import annotations


def media(path: str, case: str | None = None, every: int = 10, step: str | None = None, as_json: bool = False) -> int:
    """Transcribe audio; split video into audio and frames."""
    raise NotImplementedError
