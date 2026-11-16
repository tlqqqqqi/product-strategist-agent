"""Shared helpers: paths, time, JSON files, output, errors. Standard library only."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

OK, FAILED, UNAVAILABLE, USER_DECIDES = 0, 1, 2, 3
CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")


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
    if not CASE_ID.match(case):
        raise StratError(f"bad case id {case!r}", USER_DECIDES)
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


# --- seal: the case's record files change only through bin/strat ---------------------------
# Every write of these files by the CLI records the file's sha256 in <case>/.seal.json; a gate
# check fails when a file no longer matches (a weak model once wrote support verdicts into
# claims.jsonl by hand, another rewrote a source snapshot with its own script).

SEAL = ".seal.json"
SEALED_NAMES = {"state.json", "claims.jsonl", "objections.jsonl", "log.jsonl", "index.jsonl"}


def _case_of(path: Path) -> Path | None:
    for d in (path.parent, path.parent.parent):
        if (d / "state.json").is_file() or path == d / "state.json":
            return d
    return None


def sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def seal(path: Path) -> None:
    """Record the current hash of a case record file written by the CLI."""
    cdir = _case_of(path)
    if cdir is None or not path.is_file():
        return
    spath = cdir / SEAL
    data = json.loads(spath.read_text(encoding="utf-8")) if spath.is_file() else {}
    data[path.relative_to(cdir).as_posix()] = sha256_of(path)
    tmp = spath.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(spath)


def next_number(ids: Iterable[str]) -> int:
    """The next id number: one above the highest, so a deleted line never frees an old id."""
    nums = [int(m.group(1)) for i in ids if (m := re.match(r"^[A-Z](\d+)$", str(i)))]
    return max(nums, default=0) + 1


def check_seal(path: Path) -> None:
    """Before the CLI writes a case record file: the case must still match its seal, or the
    write would re-hash a hand edit and make it pass the gate. Nothing is written on a mismatch."""
    cdir = _case_of(path)
    if cdir is None or not (cdir / SEAL).is_file():
        return
    from strat.validate import seal_errors

    errors = seal_errors(cdir)
    if errors:
        raise StratError("; ".join(errors))


def _maybe_seal(path: Path) -> None:
    if path.name in SEALED_NAMES:
        seal(path)


def _guard(path: Path) -> None:
    if path.name in SEALED_NAMES:
        check_seal(path)


def write_json(path: Path, data: Any) -> None:
    """Write atomically so a crash never leaves half a file."""
    _guard(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    _maybe_seal(path)


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
    _guard(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _maybe_seal(path)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    _guard(path)
    tmp =path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(path)
    _maybe_seal(path)


def env(key: str) -> str:
    """A setting from the environment, else from .env (STRAT_ENV_FILE overrides its path).

    .env is parsed as KEY=VALUE lines; it is never printed or logged.
    """
    if os.environ.get(key):
        return os.environ[key]
    path = Path(os.environ.get("STRAT_ENV_FILE") or root() / ".env")
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().removeprefix("export ").strip() == key:
            return value.strip().strip("'\"")
    return ""


def load_config(name: str) -> dict:
    """Read config/<name>.yaml. PyYAML is imported lazily so `strat state` stays stdlib-only."""
    import yaml

    path = root() / "config" / f"{name}.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def emit(text: str, data: Any = None, as_json: bool = False) -> None:
    """Print English text, or JSON when --json was given."""
    if as_json:
        print(json.dumps(data if data is not None else {"message": text}, ensure_ascii=False, indent=2))
    else:
        print(text)


def warn(message: str) -> None:
    print(message, file=sys.stderr)
