"""The user's own messages, written by the harness, not by the agent.

A hook in the harness (Claude Code: UserPromptSubmit, `hooks/user-prompt`; OpenCode: the project
plugin `.opencode/plugins/strat-inbox.js`) appends every message the user sends to
`cases/.inbox.jsonl`. The CLI only reads it: `gate approve` needs a yes from the user after the
gate became ready, and a `risk-accepted` verdict must quote the user's real words. There is no
CLI command that writes the inbox. A weak model once approved Gate 2 after the user said only
«Продолжай.», another took the sign-off «Подписываю.» as acceptance of risks it never asked
about.

Without the hook (a harness that has none) the file does not exist and these checks are skipped;
`strat doctor` reports it.
"""

from __future__ import annotations

import re
from pathlib import Path

from strat.core import cases_dir, read_jsonl

NAME = ".inbox.jsonl"
YES = re.compile(r"(^|[^\w])(да|ага|утвержд\w*|одобр\w*|подпис\w*|соглас\w*|выбира\w*|"
                 r"выбрал\w*|принима\w*|принял\w*|ок|окей|хорошо|поехали|согласовано|"
                 r"yes|ok|okay|approve\w*)(?=$|[^\w])", re.I)
QUOTE = re.compile(r"«([^»]{3,})»|\"([^\"]{3,})\"")


def path() -> Path:
    return cases_dir() / NAME


def available() -> bool:
    return path().is_file()


def messages() -> list[dict]:
    return [r for r in read_jsonl(path()) if isinstance(r.get("text"), str)]


def since(t: float | None) -> list[dict]:
    """Messages the user sent after the moment t (epoch seconds; each row has `t`)."""
    return [m for m in messages() if t is None or float(m.get("t") or 0) > t]


def is_yes(text: str) -> bool:
    return bool(YES.search(text or ""))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower().strip(".!")


def quoted_by_user(reason: str) -> bool:
    """True when the reason quotes («...» or "...") words that appear in a user message."""
    quotes = [_norm(a or b) for a, b in QUOTE.findall(reason or "")]
    if not quotes:
        return False
    said = [_norm(m["text"]) for m in messages()]
    return any(q and any(q in s for s in said) for q in quotes)
