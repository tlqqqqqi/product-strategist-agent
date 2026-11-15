"""Every command in the spec's CLI table is registered and routes to a function that accepts
the arguments the parser produces."""

import inspect

import pytest

from strat.cli import COMMANDS, _INTERNAL, build_parser, resolve

SAMPLES = {
    "setup": ["setup", "--sync"],
    "doctor": ["doctor"],
    "new": ["new", "x", "--title", "T"],
    "state": ["state"],
    "step": ["step", "intake.brief", "--stage", "plan", "--out", "brief.md", "--next", "n"],
    "gate check": ["gate", "check", "1"],
    "gate approve": ["gate", "approve", "1"],
    "source add": ["source", "add", "f.xlsx", "--step", "s"],
    "source list": ["source", "list"],
    "claim add": ["claim", "add", "--type", "fact", "--kind", "price", "--text", "t",
                  "--source", "S001", "--where", "w", "--quote", "q", "--as-of", "2026-10",
                  "--supports", "C001", "--historical"],
    "claim check": ["claim", "check", "--all"],
    "claim list": ["claim", "list", "--load-bearing"],
    "claim replace": ["claim", "replace", "C001", "C002"],
    "claim withdraw": ["claim", "withdraw", "C001", "--reason", "r"],
    "claim confirm": ["claim", "confirm", "C001", "--source", "S2", "--where", "w",
                      "--quote", "q", "--as-of", "2026-11"],
    "search": ["search", "q", "--kind", "text", "--step", "s"],
    "read": ["read", "https://example.org", "--step", "s"],
    "capture": ["capture", "https://example.org", "--flow", "f", "--steps", "3"],
    "media": ["media", "a.mp3", "--every", "5"],
    "judge": ["judge", "support", "--claim", "C001"],
    "consult": ["consult", "challenge"],
    "debate": ["debate", "O001"],
    "ingest": ["ingest", "f.csv"],
    "impact": ["impact", "C001"],
    "review": ["review"],
    "cost": ["cost"],
    "report": ["report"],
    "replay export": ["replay", "export"],
    "analysis check": ["analysis", "check", "S001"],
    "interview add": ["interview", "add", "t.txt", "--mask", "A", "--persona", "p", "--step", "s"],
    "interview persona": ["interview", "persona", "p.md", "--guide", "g.md", "--step", "s",
                          "--questions", "3"],
}


def test_every_command_has_a_sample():
    assert set(SAMPLES) == set(COMMANDS)


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_command_routes_to_a_matching_function(name):
    args = build_parser().parse_args(SAMPLES[name])
    assert args.target == name
    kwargs = {k: v for k, v in vars(args).items() if k not in _INTERNAL}
    func = resolve(name)
    inspect.signature(func).bind(**kwargs)  # raises TypeError on a mismatch
