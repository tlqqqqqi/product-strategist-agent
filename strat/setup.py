"""Setup: write keys to .env, sync skills into .claude/, offer optional installs."""

from __future__ import annotations


def setup(browser: bool = False, sync: bool = False, as_json: bool = False) -> int:
    """Write keys to .env; --sync copies skills/ and agents/ into .claude/."""
    raise NotImplementedError
