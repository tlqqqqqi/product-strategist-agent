"""Skills, knowledge and templates are consistent with the CLI and with each other."""

import re

import pytest

from conftest import REPO
from strat.cli import COMMANDS

SKILLS = ["using-strategist", "intake", "plan", "research", "materials", "options", "strategy",
          "signoff", "report", "ux-capture", "data-analysis", "review", "revise", "media", "challenge", "interview"]
TEMPLATES = ["brief", "plan", "table", "options", "product", "comms", "verification",
             "decision-record", "memo"]
KNOWLEDGE = ["INDEX", "claims", "case-types", "product-strategy", "comms-strategy",
             "verification-plan", "objections"]


def all_text_files():
    for folder in ("skills", "knowledge"):
        yield from (REPO / folder).rglob("*.md")
    yield REPO / "AGENTS.md"


@pytest.mark.parametrize("name", SKILLS)
def test_skill_has_frontmatter_matching_its_folder(name):
    text = (REPO / "skills" / name / "SKILL.md").read_text()
    m = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", text)
    assert m and m.group(1) == name and len(m.group(2)) > 40


def test_bootstrap_routes_only_to_existing_skills():
    text = (REPO / "skills" / "using-strategist" / "SKILL.md").read_text()
    for ref in set(re.findall(r"skills/([a-z-]+)", text)):
        assert (REPO / "skills" / ref / "SKILL.md").is_file(), ref


def test_every_strat_command_in_the_docs_exists():
    names = {c.split()[0] for c in COMMANDS} | set(COMMANDS)
    for f in all_text_files():
        for cmd in re.findall(r"bin/strat ([a-z]+(?: [a-z]+)?)", f.read_text()):
            first = cmd.split()[0]
            assert cmd in COMMANDS or first in names, f"{f.name}: bin/strat {cmd}"


@pytest.mark.parametrize("name", TEMPLATES)
def test_template_has_a_title_and_sections(name):
    text = (REPO / "knowledge" / "templates" / f"{name}.md").read_text()
    assert text.startswith("# ")
    assert len(re.findall(r"^## ", text, re.M)) >= 3


@pytest.mark.parametrize("name", KNOWLEDGE)
def test_knowledge_file_exists_and_is_indexed(name):
    assert (REPO / "knowledge" / f"{name}.md").is_file()
    if name != "INDEX":
        assert f"{name}.md" in (REPO / "knowledge" / "INDEX.md").read_text()


def test_links_between_files_resolve():
    for f in all_text_files():
        for ref in re.findall(r"`((?:skills|knowledge)/[\w./-]+\.md)`", f.read_text()):
            assert (REPO / ref).is_file(), f"{f.relative_to(REPO)} -> {ref}"


def test_intake_asks_one_question_per_window():
    """The owner wants intake questions one at a time in the harness's question window (Claude
    Code AskUserQuestion), answers kept as **Q**/**A**; never a numbered list in one message."""
    text = (REPO / "skills" / "intake" / "SKILL.md").read_text()
    assert "AskUserQuestion" in text and "**Q**" in text and "**A**" in text
    assert "one question per" in text
    assert "numbered questions" not in text
