"""Command routing. Each command dispatches to one function in its module.

Modules are imported lazily, so `strat state` (run by the session-start hook) needs only the
standard library. Exit codes: 0 ok, 1 validation failed, 2 tool or capability unavailable,
3 the user must decide.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from strat.core import UNAVAILABLE, StratError

# command name -> "module:function"
COMMANDS: dict[str, str] = {
    "setup": "setup:setup",
    "doctor": "doctor:doctor",
    "new": "state:new_case",
    "state": "state:show",
    "step": "state:step",
    "gate check": "validate:gate_check",
    "gate approve": "state:gate_approve",
    "source add": "sources:add",
    "claim add": "ledger:add",
    "claim check": "ledger:check",
    "claim list": "ledger:list_claims",
    "claim replace": "ledger:replace",
    "claim withdraw": "ledger:withdraw",
    "claim confirm": "ledger:confirm",
    "search": "search:search",
    "read": "read:read",
    "capture": "browser:capture",
    "media": "media:media",
    "judge": "judge:judge",
    "consult": "consult:consult",
    "debate": "consult:debate",
    "ingest": "ingest:ingest",
    "impact": "ingest:impact",
    "review": "review:review",
    "cost": "cost:cost",
    "report": "report:report",
    "replay export": "replay:export",
    "analysis check": "analysis:check",
}


def _common(p: argparse.ArgumentParser, case: bool = True) -> None:
    if case:
        p.add_argument("--case", default=None, help="case id (default: cases/.current)")
    p.add_argument("--json", dest="as_json", action="store_true", help="print JSON")


def _cmd(sub, name: str, help_: str, case: bool = True) -> argparse.ArgumentParser:
    p = sub.add_parser(name, help=help_)
    _common(p, case)
    return p


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="strat", description="Strategist CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = _cmd(sub, "setup", "write keys to .env, sync skills, offer optional installs", case=False)
    p.add_argument("--browser", action="store_true", help="also install the optional browser")
    p.add_argument("--sync", action="store_true", help="copy skills/ and agents/ into .claude/")
    p.set_defaults(target="setup")

    p = _cmd(sub, "doctor", "list each capability as available or missing", case=False)
    p.set_defaults(target="doctor")

    p = _cmd(sub, "new", "create a case from cases/_template and make it current", case=False)
    p.add_argument("case_id")
    p.add_argument("--title", required=True)
    p.set_defaults(target="new")

    p = _cmd(sub, "state", "stage, gates, next action, due items")
    p.set_defaults(target="state")

    p = _cmd(sub, "step", "log one agent action; set stage and next action")
    p.add_argument("step_id")
    p.add_argument("--stage", default=None)
    p.add_argument("--out", default=None, help="file the step wrote, relative to the case")
    p.add_argument("--next", dest="next_", default=None, help="next action for a new chat")
    p.add_argument("--note", default=None)
    p.set_defaults(target="step")

    gate = sub.add_parser("gate", help="gate checks and approvals")
    gsub = gate.add_subparsers(dest="gate_cmd", required=True)
    for name, help_ in (("check", "run the checks for gate n"),
                        ("approve", "record the user's explicit approval and advance")):
        p = _cmd(gsub, name, help_)
        p.add_argument("n", type=int, choices=[1, 2, 3])
        p.set_defaults(target=f"gate {name}")

    source = sub.add_parser("source", help="sources")
    ssub = source.add_subparsers(dest="source_cmd", required=True)
    p = _cmd(ssub, "add", "register a material, write its snapshot, print the S id")
    p.add_argument("path")
    p.add_argument("--title", default=None)
    p.add_argument("--step", default=None)
    p.set_defaults(target="source add")

    claim = sub.add_parser("claim", help="claim ledger")
    csub = claim.add_subparsers(dest="claim_cmd", required=True)
    p = _cmd(csub, "add", "add one claim")
    p.add_argument("--type", dest="type_", required=True)
    p.add_argument("--kind", required=True)
    p.add_argument("--text", required=True)
    p.add_argument("--source", default=None)
    p.add_argument("--where", default=None)
    p.add_argument("--quote", default=None)
    p.add_argument("--as-of", dest="as_of", default=None)
    p.add_argument("--supports", default=None, help="comma-separated claim ids")
    p.add_argument("--historical", action="store_true",
                   help="a claim about a closed past period; never goes stale")
    p.add_argument("--step", default=None)
    p.set_defaults(target="claim add")
    p = _cmd(csub, "check", "quote check, then the support judgment")
    p.add_argument("claim_id", nargs="?", default=None)
    p.add_argument("--all", dest="all_", action="store_true")
    p.set_defaults(target="claim check")
    p = _cmd(csub, "list", "list claims and regenerate claims.md")
    p.add_argument("--type", dest="type_", default=None)
    p.add_argument("--load-bearing", dest="load_bearing", action="store_true")
    p.add_argument("--stale", action="store_true")
    p.set_defaults(target="claim list")
    p = _cmd(csub, "replace", "mark old as replaced by new")
    p.add_argument("old")
    p.add_argument("new")
    p.set_defaults(target="claim replace")
    p = _cmd(csub, "withdraw", "withdraw a claim")
    p.add_argument("claim_id")
    p.add_argument("--reason", required=True)
    p.set_defaults(target="claim withdraw")
    p = _cmd(csub, "confirm", "re-confirm a stale claim with a newer source")
    p.add_argument("claim_id")
    p.add_argument("--source", required=True)
    p.add_argument("--where", required=True)
    p.add_argument("--quote", required=True)
    p.add_argument("--as-of", dest="as_of", required=True)
    p.set_defaults(target="claim confirm")

    p = _cmd(sub, "search", "web search through one provider")
    p.add_argument("query")
    p.add_argument("--kind", choices=["keyword", "text", "semantic"], default="keyword")
    p.add_argument("--step", required=True)
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(target="search")

    p = _cmd(sub, "read", "save a page (URL or saved .html file) as a source")
    p.add_argument("url")
    p.add_argument("--step", required=True)
    p.add_argument("--title", default=None)
    p.set_defaults(target="read")

    p = _cmd(sub, "capture", "walk a public flow into shots/, never submits")
    p.add_argument("url")
    p.add_argument("--flow", required=True)
    p.add_argument("--steps", type=int, default=5,
                   help="most steps to capture (screens of one page when there is no --plan)")
    p.add_argument("--plan", default=None, help="JSON or YAML file: steps with click/goto/targets")
    p.add_argument("--step", default=None, help="log step id (default capture.<flow>)")
    p.set_defaults(target="capture")

    p = _cmd(sub, "media", "audio or video into a timestamped transcript (and frames) as sources")
    p.add_argument("path")
    p.add_argument("--every", type=int, default=10, help="video: seconds between frames")
    p.add_argument("--step", default=None, help="log step id (default media.<name>)")
    p.set_defaults(target="media")

    p = _cmd(sub, "judge", "small judgment through the routing table")
    p.add_argument("question", choices=["type", "support", "contradiction", "sufficient"])
    p.add_argument("--claim", default=None)
    p.add_argument("--other", default=None)
    p.add_argument("--answer", default=None,
                   help="record the IDE agent's own answer (stored with by=agent)")
    p.set_defaults(target="judge")

    p = _cmd(sub, "consult", "challenger call (variants|challenge), verdicts, list")
    p.add_argument("call", choices=["variants", "challenge", "verdict", "list"])
    p.add_argument("objection_id", nargs="?", default=None, help="verdict: the O id")
    p.add_argument("verdict", nargs="?", default=None, help="verdict: accepted|rejected|open")
    p.add_argument("--reason", default=None, help="verdict: the written reason")
    p.add_argument("--from-file", dest="from_file", default=None,
                   help="import the challenger's JSON answer (native subagent, same vendor)")
    p.add_argument("--step", default=None, help="log step id (default consult.<call>)")
    p.set_defaults(target="consult")

    p = _cmd(sub, "debate", "one debate round on a rejected critical objection")
    p.add_argument("objection_id")
    p.add_argument("--from-file", dest="from_file", default=None,
                   help="import the challenger's JSON reply (native subagent, same vendor)")
    p.set_defaults(target="debate")

    p = _cmd(sub, "ingest", "register new material after a decision; case moves to revision")
    p.add_argument("path")
    p.add_argument("--title", default=None)
    p.add_argument("--step", default=None, help="log step id (default ingest.<S id>)")
    p.set_defaults(target="ingest")

    p = _cmd(sub, "impact", "conclusions and document lines that depend on a claim")
    p.add_argument("claim_id")
    p.set_defaults(target="impact")

    p = _cmd(sub, "review", "due checks, fired review conditions, stale and contradicted "
                            "load-bearing claims; at most 3 questions")
    p.set_defaults(target="review")

    p = _cmd(sub, "cost", "time and money by stage")
    p.set_defaults(target="cost")

    p = _cmd(sub, "report", "memo.md to memo.html")
    p.set_defaults(target="report")

    replay = sub.add_parser("replay", help="replay script")
    rsub = replay.add_subparsers(dest="replay_cmd", required=True)
    p = _cmd(rsub, "export", "build the replay script from the recorded session")
    p.add_argument("--transcript", default=None)
    p.set_defaults(target="replay export")

    analysis = sub.add_parser("analysis", help="data analysis scripts in analysis/")
    asub = analysis.add_subparsers(dest="analysis_cmd", required=True)
    p = _cmd(asub, "check", "rerun the script behind an analysis output; report figures that "
                            "do not reproduce, gaps, unit and period mismatches")
    p.add_argument("source_id", nargs="?", default=None)
    p.add_argument("--all", dest="all_", action="store_true")
    p.set_defaults(target="analysis check")

    return parser


_INTERNAL = {"command", "target", "gate_cmd", "source_cmd", "claim_cmd", "replay_cmd",
             "analysis_cmd"}


def resolve(target: str):
    module_name, func_name = COMMANDS[target].split(":")
    module = importlib.import_module(f"strat.{module_name}")
    return getattr(module, func_name)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    kwargs = {k: v for k, v in vars(args).items() if k not in _INTERNAL}
    try:
        return int(resolve(args.target)(**kwargs) or 0)
    except NotImplementedError:
        print(f"strat: `{args.target}` is not available in this version", file=sys.stderr)
        return UNAVAILABLE
    except StratError as exc:
        print(f"strat: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
