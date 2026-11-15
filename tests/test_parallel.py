"""Agents in some harnesses run several tool calls at once (seen in OpenCode, Pi, Kimi on
DeepSeek). Parallel CLI calls on one case must not lose writes or hand out one id twice."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from conftest import REPO


def run_cli(env, *args):
    return subprocess.run([sys.executable, "-m", "strat.cli", *args], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=60)


def test_parallel_claim_and_source_adds_keep_every_write(case, cases, tmp_path):
    env = {**os.environ, "STRAT_CASES": str(cases), "STRAT_ROOT": str(REPO)}
    files = []
    for i in range(4):
        f = tmp_path / f"note{i}.html"
        f.write_text(f"<html><body><p>Заметка номер {i}</p></body></html>", encoding="utf-8")
        files.append(str(f))
    jobs = [("claim", "add", "--type", "gap", "--kind", "market", "--text", f"Пробел {i}")
            for i in range(10)] + [("source", "add", f) for f in files]
    with ThreadPoolExecutor(max_workers=14) as pool:
        results = list(pool.map(lambda a: run_cli(env, *a), jobs))
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results if r.returncode]
    claims = [json.loads(l) for l in (case / "claims.jsonl").read_text().splitlines()]
    assert len(claims) == 10 and len({c["id"] for c in claims}) == 10
    sources = [json.loads(l) for l in (case / "sources" / "index.jsonl").read_text().splitlines()]
    ids = [s["id"] for s in sources]
    assert len(ids) == len(set(ids)) and len([s for s in sources if "note" in s["origin"]]) == 4
