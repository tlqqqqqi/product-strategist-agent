"""One OpenAI-compatible client: 120 s timeout, one retry. (Phase 2)"""

from __future__ import annotations


def chat(role: str, messages: list[dict], **params) -> int:
    """Call the model configured for role (peer, jev, stt)."""
    raise NotImplementedError
