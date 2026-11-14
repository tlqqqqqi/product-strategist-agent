"""Source index, snapshots and the quote check.

Every source has a plain-text snapshot in sources/Sxxx.md. A claim's quote must occur in that
snapshot after collapsing whitespace and case-folding; "..." or an ellipsis splits a quote into
parts that must occur in order.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

from strat import convert as conv
from strat.core import (
    StratError,
    append_jsonl,
    case_path,
    emit,
    now,
    read_jsonl,
)

SOURCE_ID = re.compile(r"^S\d{3,}$")
_ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…)\s*")


# --- quote check ------------------------------------------------------------------------------

def normalize(text: str) -> str:
    text = text.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return " ".join(text.split()).casefold()


def quote_found(snapshot: str, quote: str) -> bool:
    hay = normalize(snapshot)
    parts = [normalize(p) for p in _ELLIPSIS.split(quote) if normalize(p)]
    if not parts:
        return False
    pos = 0
    for part in parts:
        i = hay.find(part, pos)
        if i < 0:
            return False
        pos = i + len(part)
    return True


# --- index ------------------------------------------------------------------------------------

def index(cdir: Path) -> list[dict]:
    return read_jsonl(cdir / "sources" / "index.jsonl")


def get(cdir: Path, source_id: str) -> dict | None:
    for entry in index(cdir):
        if entry["id"] == source_id:
            return entry
    return None


def snapshot_text(cdir: Path, entry: dict) -> str:
    path = (cdir / entry["snapshot"]).resolve()
    if path.parent != (cdir / "sources").resolve() or not path.is_file():
        raise StratError(f"{entry['id']}: snapshot {entry['snapshot']!r} is not a file in sources/")
    return path.read_text(encoding="utf-8")


def check_quote(cdir: Path, source_id: str, quote: str) -> bool:
    entry = get(cdir, source_id)
    if entry is None:
        raise StratError(f"unknown source {source_id}")
    return quote_found(snapshot_text(cdir, entry), quote)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def register(cdir: Path, *, kind: str, origin: str, title: str, text: str, digest: str,
             fmt: str, **extra) -> dict:
    """Write the snapshot, then append the index line. Returns the index entry."""
    entries = index(cdir)
    for entry in entries:
        if entry["origin"] == origin and entry["sha256"] == digest:
            return dict(entry, existing=True)
    sid = f"S{len(entries) + 1:03d}"
    snapshot = f"sources/{sid}.md"
    (cdir / snapshot).write_text(text, encoding="utf-8")
    entry = {"id": sid, "kind": kind, "origin": origin, "title": title, "fetched": now(),
             "sha256": digest, "snapshot": snapshot, "format": fmt, **extra}
    append_jsonl(cdir / "sources" / "index.jsonl", entry)
    return entry


# --- command ----------------------------------------------------------------------------------

def add(path: str, case: str | None = None, title: str | None = None, step: str | None = None,
        as_json: bool = False) -> int:
    """Register a material, write its snapshot, print the S id."""
    from strat.state import log_action, replay

    cdir = case_path(case)
    if replay(cdir, step, as_json, "source add"):
        return 0
    src = Path(path)
    if not src.is_absolute():
        src = cdir / path if (cdir / path).exists() else Path.cwd() / path
    if not src.is_file():
        raise StratError(f"{path}: file not found")
    src = src.resolve()
    materials = (cdir / "materials").resolve()
    if materials not in src.parents:
        dest = materials / src.name
        if dest.exists() and sha256(dest.read_bytes()) != sha256(src.read_bytes()):
            raise StratError(f"materials/{src.name} already exists with other content; rename "
                             "the file")
        shutil.copy2(src, dest)
        src = dest
    text = conv.convert(str(src))
    origin = str(src.relative_to(cdir.resolve()))
    entry = register(cdir, kind="file", origin=origin, title=title or src.name, text=text,
                     digest=sha256(src.read_bytes()), fmt=conv.fmt_of(src))
    if step:
        log_action(cdir, step=step, tool="source add", in_=origin, out=entry["snapshot"],
                   ref=entry["id"])
    verb = "already registered as" if entry.get("existing") else "registered as"
    emit(f"{origin} {verb} {entry['id']}; snapshot: {entry['snapshot']}",
         {"id": entry["id"], "snapshot": entry["snapshot"], "origin": origin,
          "existing": bool(entry.get("existing"))}, as_json)
    return 0
