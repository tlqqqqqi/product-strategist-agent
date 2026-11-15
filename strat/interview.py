"""Interview transcripts and model respondents as `interview` sources.

- `strat interview add <file>` registers a transcript the user supplies. Phones and e-mails are
  masked by script, and so are the names the agent passes with --mask; the masked copy is written
  to interviews/<name>.md and registered, the raw file never enters the case. `strat source add`
  of a file that looks like a transcript takes the same path.
- `strat interview persona <persona-file> --guide <guide> --step ID` plays a model respondent on
  the peer model: agents/persona.md plus the persona file as the system prompt, one call per
  guide question (each its own logged step with its price, so a restart continues after the last
  answer). The session goes to interviews/persona_<name>.md, starts with a Russian banner that it
  is a model's imitation, and is registered with "synthetic": true; the ledger then accepts only
  `synthetic` claims citing it. Without a peer key: exit 3 and the import path for a native
  subagent's output (`interview add --persona NAME`, marked same-vendor).
- A guide must carry a consent line (`> Согласие: ...`) before its questions, or it is refused.
"""

from __future__ import annotations

import re
from pathlib import Path

from strat import convert as conv
from strat import models, net, sources
from strat.core import (
    UNAVAILABLE,
    USER_DECIDES,
    StratError,
    append_jsonl,
    case_path,
    emit,
    load_config,
    read_jsonl,
    root,
    warn,
)

BANNER = ("> ВНИМАНИЕ: это имитация респондента языковой моделью ({who}), а не ответы реального "
          "человека. Утверждения из этого файла имеют тип synthetic и не могут быть фактами.")
WHO_PEER = "модель {model}, вызванная через peer-эндпоинт"
WHO_SAME = "субагент той же модели, что ведёт анализ (same-vendor)"
CONSENT = re.compile(r"^\s*>?\s*Согласие\s*:", re.M)
QUESTION = re.compile(r"^\s*(\d+)[.)]\s+(.+?)\s*$", re.M)
BLOCK = re.compile(r"^## Q\d+\s*$", re.M)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<![\w+])(?:\+7|8|\+\d{1,3})[\s\-]*\(?\d{3,4}\)?[\s\-]*\d{2,3}"
                   r"[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")
LOOKS_LIKE = re.compile(r"interview|интервью|transcript|транскрипт|respondent|респондент|"
                        r"persona|персона", re.I)
IMPORT_HINT = ("run the persona as a native subagent from agents/persona.md (give it the persona "
               "file and the guide; it writes `## Q<n>` blocks), save its output, then import it "
               "with `bin/strat interview add <file> --persona {name}`: it is stored as "
               "synthetic and marked same-vendor")


def _conf() -> dict:
    return load_config("routes").get("persona", {})


def _safe(name: str) -> str:
    name = re.sub(r"[^\w-]+", "_", name.strip().lower()).strip("_")
    if not name:
        raise StratError("empty name")
    return name


def _resolve(cdir: Path, path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = cdir / path if (cdir / path).exists() else Path.cwd() / path
    if not p.is_file():
        raise StratError(f"{path}: file not found")
    return p.resolve()


# --- personal data ----------------------------------------------------------------------------

def mask(text: str, names: list[str] | None = None) -> tuple[str, dict]:
    """Replace e-mails, phones and the given names with placeholders. Returns (text, counts)."""
    counts = {"phone": 0, "email": 0, "name": 0}
    text, counts["email"] = EMAIL.subn("[EMAIL]", text)
    text, counts["phone"] = PHONE.subn("[ТЕЛЕФОН]", text)
    items: list[str] = []
    for item in names or []:
        item = item.strip()
        if item:
            items.append(item)
            items += [w for w in item.split() if len(w) >= 3]
    for item in sorted(set(items), key=len, reverse=True):
        pattern = re.compile(rf"(?<!\w){re.escape(item)}(?!\w)", re.I)
        text, n = pattern.subn("[ИМЯ]", text)
        counts["name"] += n
    return text, counts


def looks_like_transcript(origin: Path) -> bool:
    """An interview transcript by name or folder; media/ transcripts keep their own path."""
    parts = origin.parts
    if "media" in parts[:-1]:
        return False
    return bool(LOOKS_LIKE.search(origin.name)) or "interviews" in parts[:-1]


# --- guide ------------------------------------------------------------------------------------

def guide_questions(text: str, label: str) -> list[str]:
    qs = [(m.start(), m.group(2)) for m in QUESTION.finditer(text)]
    if not qs:
        raise StratError(f"{label}: no numbered questions (`1. ...`)")
    consent = CONSENT.search(text)
    if consent is None or consent.start() > qs[0][0]:
        raise StratError(f"{label}: no consent line before the questions; start the guide with "
                         "`> Согласие: ...` (ask for consent to record, no names, phones or "
                         "e-mails)")
    return [q for _, q in qs]


# --- add --------------------------------------------------------------------------------------

def register_transcript(cdir: Path, src: Path, *, title: str | None, names: list[str],
                        persona: str | None, step: str | None, tool: str) -> dict:
    """Mask, write the copy into interviews/, register it as an `interview` source."""
    from strat.state import log_action

    text, counts = mask(conv.convert(str(src)), names)
    (cdir / "interviews").mkdir(exist_ok=True)
    if persona:
        name = _safe(persona.removeprefix("persona_"))
        if not BLOCK.search(text):
            raise StratError(f"{src.name}: no `## Q<n>` blocks; the persona session must have one "
                             "block per question (see agents/persona.md)")
        if not text.lstrip().startswith(BANNER[:20]):
            text = BANNER.format(who=WHO_SAME) + "\n\n" + text
        dest = cdir / "interviews" / f"persona_{name}.md"
        extra = {"synthetic": True, "by": "same-vendor"}
        fmt = "persona"
    else:
        dest = cdir / "interviews" / f"{_safe(src.stem)}.md"
        extra = {}
        fmt = "text"
    dest.write_text(text, encoding="utf-8")
    origin = str(dest.relative_to(cdir))
    entry = sources.register(cdir, kind="interview", origin=origin, title=title or src.name,
                             text=text, digest=sources.sha256(text.encode("utf-8")), fmt=fmt,
                             masked=counts, **extra)
    raw_inside = cdir.resolve() in src.parents and src != dest.resolve()
    if raw_inside and any(counts.values()):
        warn(f"strat: the raw file {src.relative_to(cdir.resolve())} still holds the personal "
             f"data that was masked in {origin}; ask the user to delete it from the case")
    if step:
        log_action(cdir, step=step, tool=tool, in_=src.name, out=origin, ref=entry["id"],
                   note="masked " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return dict(entry, masked=counts)


def add(path: str, case: str | None = None, title: str | None = None, mask: str | None = None,
        persona: str | None = None, step: str | None = None, as_json: bool = False) -> int:
    """Register a transcript (masked) or import a persona session as synthetic."""
    from strat.state import replay

    cdir = case_path(case)
    if replay(cdir, step, as_json, "interview add"):
        return 0
    src = _resolve(cdir, path)
    names = [n for n in (mask or "").split(",") if n.strip()]
    entry = register_transcript(cdir, src, title=title, names=names, persona=persona, step=step,
                                tool="interview add")
    return _report(entry, as_json)


def _report(entry: dict, as_json: bool) -> int:
    counts = entry["masked"]
    verb = "already registered as" if entry.get("existing") else "registered as"
    note = (" synthetic (a model respondent): claims citing it must be --type synthetic"
            if entry.get("synthetic") else " (interview)")
    emit(f"{entry['origin']} {verb} {entry['id']}{note}; masked: phones {counts['phone']}, "
         f"e-mails {counts['email']}, names {counts['name']}. Names the script does not know "
         "are not masked: read the copy and rerun with --mask if one is left.",
         {"id": entry["id"], "origin": entry["origin"], "snapshot": entry["snapshot"],
          "synthetic": bool(entry.get("synthetic")), "masked": counts,
          "existing": bool(entry.get("existing")), "replayed": False}, as_json)
    return 0


# --- persona ----------------------------------------------------------------------------------

def _persona_prompt() -> str:
    text = (root() / "agents" / "persona.md").read_text(encoding="utf-8")
    if text.startswith("---\n"):
        text = text.split("\n---\n", 1)[1]
    return text.strip()


def persona(persona_file: str, guide: str, step: str, case: str | None = None,
            questions: int | None = None, as_json: bool = False) -> int:
    """Run a model respondent through the guide on the peer model."""
    from strat.state import log_action, replay

    cdir = case_path(case)
    if replay(cdir, step, as_json, "interview persona"):
        return 0
    pfile, gfile = _resolve(cdir, persona_file), _resolve(cdir, guide)
    qs = guide_questions(gfile.read_text(encoding="utf-8"), gfile.name)
    conf = _conf()
    limit = questions or int(conf.get("max_questions", 8))
    qs = qs[:max(1, limit)]
    name = _safe(pfile.stem.removeprefix("persona_"))
    if models.endpoint("peer") is None:
        hint = IMPORT_HINT.format(name=name)
        warn(f"strat: no STRAT_PEER_API_KEY, so no outside model can play the respondent. "
             f"{hint}.")
        emit(hint, {"status": "needs_agent", "by": "same-vendor", "persona": name,
                    "agent": "agents/persona.md", "questions": qs,
                    "import": f"bin/strat interview add <file> --persona {name}"}, as_json)
        return USER_DECIDES

    system = (_persona_prompt() + "\n\n## Persona\n\n"
              + pfile.read_text(encoding="utf-8").strip())
    (cdir / "interviews").mkdir(exist_ok=True)
    partial = cdir / "interviews" / f"persona_{name}.partial.jsonl"
    done = [r for r in read_jsonl(partial) if r.get("step") == step]
    model_conf = conf.get("model") or None
    used_model = done[-1]["model"] if done else ""
    for n, q in enumerate(qs, start=1):
        if n <= len(done):
            continue
        messages = [{"role": "system", "content": system}]
        for r in done:
            messages += [{"role": "user", "content": r["q"]},
                         {"role": "assistant", "content": r["a"]}]
        messages.append({"role": "user", "content": q})
        try:
            r = models.chat("peer", messages, cdir=cdir, step=f"{step}.q{n}", model=model_conf,
                            temperature=float(conf.get("temperature", 0.7)),
                            max_tokens=int(conf.get("max_tokens", 600)))
        except net.HttpError as exc:
            raise StratError(f"persona call for question {n} failed ({exc}); {len(done)} of "
                             f"{len(qs)} answers are kept: run the same command again to "
                             "continue", UNAVAILABLE) from None
        row = {"step": step, "n": n, "q": q, "a": r["text"].strip(), "model": r["model"],
               "usd": round(r["usd"], 6)}
        append_jsonl(partial, row)
        done.append(row)
        used_model = r["model"]

    blocks = "\n\n".join(f"## Q{r['n']}\n\n**Вопрос:** {r['q']}\n\n**Ответ:** {r['a']}"
                         for r in done)
    text = (BANNER.format(who=WHO_PEER.format(model=used_model)) + "\n\n"
            f"# Сессия модельного респондента: {name}\n\n"
            f"> Персона: {pfile.name}; гайд: {gfile.name}; вопросов: {len(done)}.\n\n"
            + blocks + "\n")
    dest = cdir / "interviews" / f"persona_{name}.md"
    dest.write_text(text, encoding="utf-8")
    origin = str(dest.relative_to(cdir))
    entry = sources.register(cdir, kind="interview", origin=origin,
                             title=f"Модельный респондент: {name}", text=text,
                             digest=sources.sha256(text.encode("utf-8")), fmt="persona",
                             synthetic=True, by="peer", model=used_model,
                             masked={"phone": 0, "email": 0, "name": 0})
    usd = round(sum(r["usd"] for r in done), 6)
    # The calls are already in the log with their price; this line records the result only.
    log_action(cdir, step=step, tool="interview persona", in_=gfile.name, out=origin,
               ref=entry["id"], note=f"{len(done)} answers by {used_model}, {usd} USD")
    partial.unlink(missing_ok=True)
    emit(f"{origin} registered as {entry['id']}: synthetic, {len(done)} answers by "
         f"{used_model}, {usd} USD. Claims citing it must be --type synthetic, --where Q<n>.",
         {"id": entry["id"], "origin": origin, "synthetic": True, "by": "peer",
          "model": used_model, "answers": len(done), "usd": usd, "replayed": False}, as_json)
    return 0
