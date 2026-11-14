import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from strat.cli import main

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "tests" / "fixtures" / "sample-case"


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def data(self):
        return json.loads(self.out)


@pytest.fixture
def cases(tmp_path, monkeypatch):
    """A temp cases dir; network calls are blocked."""
    d = tmp_path / "cases"
    d.mkdir()
    monkeypatch.setenv("STRAT_CASES", str(d))
    monkeypatch.setenv("STRAT_TODAY", "2026-11-15")
    for key in ("BRAVE_API_KEY", "TAVILY_API_KEY", "EXA_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("STRAT_ENV_FILE", str(tmp_path / "no.env"))  # never the real .env
    monkeypatch.setenv("STRAT_TRANSCRIPTS", str(tmp_path / "no-transcripts"))

    def no_network(*a, **k):
        raise AssertionError("tests must not use the network")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    return d


@pytest.fixture
def strat(cases, capsys):
    def run(*args: str) -> Result:
        code = main(list(args))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return run


@pytest.fixture
def case(strat, cases):
    """A new case 'demo' with the sample materials copied in."""
    r = strat("new", "demo", "--title", "Sample")
    assert r.code == 0, r.err
    shutil.copytree(SAMPLE / "materials", cases / "demo" / "materials", dirs_exist_ok=True)
    return cases / "demo"
