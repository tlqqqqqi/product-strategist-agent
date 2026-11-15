"""Task 15: the folder works as the same agent in other IDE agents.

Each adapter's hook config is run the way its environment runs it (cwd, env vars, shell), and
the output must carry the bootstrap under the key that environment reads. Entry files must
resolve to AGENTS.md, and skills must be found where each environment looks for them.
"""

import json
import os
import re
import subprocess

import pytest

from conftest import REPO

# environment -> (config file, how to get the command list, env the harness sets, output reader)
CLAUDE_STYLE = lambda out: out["hookSpecificOutput"]["additionalContext"]  # noqa: E731


def claude_like_commands(cfg):
    return [h["command"] for group in cfg["hooks"]["SessionStart"] for h in group["hooks"]]


ADAPTERS = {
    "cursor": (".cursor/hooks.json",
               lambda cfg: [h["command"] for h in cfg["hooks"]["sessionStart"]],
               {"CURSOR_PROJECT_DIR": "{repo}"},
               lambda out: out["additional_context"]),
    "qwen": (".qwen/settings.json", claude_like_commands,
             {"QWEN_PROJECT_DIR": "{repo}", "CLAUDE_PROJECT_DIR": "{repo}",
              "GEMINI_PROJECT_DIR": "{repo}"},
             CLAUDE_STYLE),
    # GigaCode is a Qwen Code fork; its hook env is not documented, so the command must also
    # work when only the Qwen variables or none at all are set.
    "gigacode": (".gigacode/settings.json", claude_like_commands, {}, CLAUDE_STYLE),
    "gigacode-qwen-env": (".gigacode/settings.json", claude_like_commands,
                          {"QWEN_PROJECT_DIR": "{repo}", "CLAUDE_PROJECT_DIR": "{repo}"},
                          CLAUDE_STYLE),
    "gemini": (".gemini/settings.json", claude_like_commands,
               {"GEMINI_PROJECT_DIR": "{repo}", "CLAUDE_PROJECT_DIR": "{repo}"},
               CLAUDE_STYLE),
    "copilot": (".github/hooks/strategist.json",
                lambda cfg: [h["bash"] for h in cfg["hooks"]["sessionStart"]],
                {"COPILOT_CLI": "1"},
                lambda out: out["additionalContext"]),
    "claude": (".claude/settings.json", claude_like_commands,
               {"CLAUDE_PROJECT_DIR": "{repo}"}, CLAUDE_STYLE),
}


def run_command(command, tmp_path, env):
    full = {k: v for k, v in os.environ.items()
            if not k.startswith(("CLAUDE", "CURSOR", "QWEN", "GEMINI", "COPILOT"))}
    full.update({k: v.format(repo=REPO) for k, v in env.items()})
    full["STRAT_CASES"] = str(tmp_path)
    proc = subprocess.run(["bash", "-c", command], cwd=REPO, capture_output=True, text=True,
                          env=full, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("name", sorted(ADAPTERS))
def test_hook_config_runs_the_one_hook_and_emits_the_right_key(name, tmp_path):
    path, commands, env, read = ADAPTERS[name]
    cfg = json.loads((REPO / path).read_text())
    found = commands(cfg)
    assert found, f"{path} registers no session-start command"
    for command in found:
        assert "hooks/session-start" in command
        out = run_command(command, tmp_path, env)
        assert len(out) == 1, f"{name}: emit only the key this environment reads, got {list(out)}"
        text = read(out)
        assert "name: using-strategist" in text and "no active case" in text


def test_cursor_hook_file_has_the_cursor_schema():
    cfg = json.loads((REPO / ".cursor/hooks.json").read_text())
    assert cfg["version"] == 1 and set(cfg["hooks"]) == {"sessionStart"}


def test_copilot_hook_file_has_the_copilot_schema():
    cfg = json.loads((REPO / ".github/hooks/strategist.json").read_text())
    assert cfg["version"] == 1
    for hook in cfg["hooks"]["sessionStart"]:
        assert hook.get("type", "command") == "command"


def expand_imports(path, depth=0):
    """Resolve `@relative/path` lines the way Claude, Qwen, GigaCode and Gemini memory files do."""
    assert depth < 5, "import cycle"
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"@(\S+)", line.strip())
        if m:
            target = (path.parent / m.group(1)).resolve()
            assert target.is_file(), f"{path.name} imports missing {m.group(1)}"
            out.append(expand_imports(target, depth + 1))
        else:
            out.append(line)
    return "\n".join(out)


@pytest.mark.parametrize("entry", ["CLAUDE.md", "QWEN.md", "GIGACODE.md", "GEMINI.md"])
def test_entry_file_leads_to_agents_md(entry):
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8").strip()
    assert agents in expand_imports(REPO / entry)


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "no frontmatter"
    return dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)


def test_cursor_rule_is_always_applied_and_points_to_agents_md():
    text = (REPO / ".cursor/rules/strategist.mdc").read_text(encoding="utf-8")
    assert frontmatter(text)["alwaysApply"] == "true"
    assert "AGENTS.md" in text and "bin/strat state" in text


def test_gigacode_rule_is_always_applied_and_points_to_agents_md():
    text = (REPO / ".gigacode/rules/strategist.md").read_text(encoding="utf-8")
    assert frontmatter(text)["apply"] == "ALWAYS"
    assert "AGENTS.md" in text and "bin/strat state" in text


SOURCE_SKILLS = sorted(p.parent.name for p in (REPO / "skills").glob("*/SKILL.md"))

# .agents/skills: Cursor, Qwen Code, Codex, Copilot CLI, Gemini CLI, OpenCode, Pi, omp, Kimi.
# .gigacode/skills: the only project path GigaCode documents.
SKILL_ROOTS = [".agents/skills", ".gigacode/skills"]


@pytest.mark.parametrize("root", SKILL_ROOTS)
def test_skills_are_discoverable_and_identical_to_the_source(root):
    base = REPO / root
    assert base.is_symlink(), f"{root} must point to skills/, not hold a copy"
    assert base.resolve() == (REPO / "skills").resolve()
    found = sorted(p.parent.name for p in base.glob("*/SKILL.md"))
    assert found == SOURCE_SKILLS
    for name in found:
        meta = frontmatter((base / name / "SKILL.md").read_text(encoding="utf-8"))
        assert meta["name"] == name and meta["description"]
