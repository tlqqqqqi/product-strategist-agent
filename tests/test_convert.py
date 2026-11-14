"""Materials to snapshots. Expanded in Step 4."""

from conftest import SAMPLE
from strat.convert import convert


def test_xlsx_snapshot_has_one_block_per_sheet():
    text = convert(str(SAMPLE / "materials" / "metrics.xlsx"))
    assert "## sheet: monthly" in text and "## sheet: cohorts" in text
