"""Shared helpers: paths, time, JSON files, output, errors. Standard library only."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

OK, FAILED, UNAVAILABLE, USER_DECIDES = 0, 1, 2, 3


class StratError(Exception):
    """An expected failure: printed to stderr, exits with `code`."""

    def __init__(self, message: str, code: int = FAILED):
        super().__init__(message)
        self.code = code


def root() -> Path:
    env = os.environ.get("STRAT_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[1]


def cases_dir() -> Path:
    """Where cases live: STRAT_CASES (tests use a temp dir), else <root>/cases."""
    env = os.environ.get("STRAT_CASES")
    return Path(env).resolve() if env else root() / "cases"


def current_case() -> str | None:
    marker = cases_dir() / ".current"
    if marker.is_file():
        value = marker.read_text(encoding="utf-8").strip()
        return value or None
    return None


def resolve_case(case: str | None) -> str:
    """Return a case id that exists, from --case or cases/.current."""
    case = case or current_case()
    if not case:
        raise StratError("no active case: run `strat new <id> --title T` or pass --case", USER_DECIDES)
    if not (cases_dir() / case / "state.json").is_file():
        raise StratError(f"case not found: {case}", USER_DECIDES)
    return case


def case_path(case: str | None) -> Path:
    return cases_dir() / resolve_case(case)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def today() -> date:
    env = os.environ.get("STRAT_TODAY")
    return date.fromisoformat(env) if env else date.today()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    """Write atomically so a crash never leaves half a file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(path)


def emit(text: str, data: Any = None, as_json: bool = False) -> None:
    """Print English text, or JSON when --json was given."""
    if as_json:
        print(json.dumps(data if data is not None else {"message": text}, ensure_ascii=False, indent=2))
    else:
        print(text)


def warn(message: str) -> None:
    print(message, file=sys.stderr)
