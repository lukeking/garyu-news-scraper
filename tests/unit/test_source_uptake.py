"""Unit tests for the source-uptake measurement (spec 011, FR-005c / FR-005d).

Synthetic data only — these never touch Supabase. What they guard is the window
selection, because both contamination sources were found empirically and would
silently corrupt the configured values if the exclusions regressed.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.measure_source_uptake import (  # noqa: E402
    MIN_SAMPLE,
    build_config,
    measure,
    select_window,
)


def rows_for(week, source, analysed, unanalysed):
    return (
        [{"week_id": week, "source": source, "hot_topic_analyzed": True}] * analysed
        + [{"week_id": week, "source": source, "hot_topic_analyzed": False}] * unanalysed
    )


class TestSelectWindow:
    def test_excludes_pruned_week_with_no_unanalysed_rows(self):
        """A fully-analysed week has had its un-analysed rows expired away.

        Keeping it would report 100% uptake for whatever sources appear in it.
        """
        rows = (
            rows_for("2026-W20", "s", analysed=10, unanalysed=0)
            + rows_for("2026-W22", "s", analysed=2, unanalysed=8)
            + rows_for("2026-W23", "s", analysed=1, unanalysed=9)  # in-flight tail
        )
        assert select_window(rows) == {"2026-W22"}

    def test_excludes_latest_week_with_no_analysed_rows(self):
        """The current week's report has not run; 0% means 'not yet eligible'."""
        rows = rows_for("2026-W22", "s", analysed=2, unanalysed=8) + rows_for(
            "2026-W30", "s", analysed=0, unanalysed=90
        )
        assert select_window(rows) == {"2026-W22"}

    def test_excludes_latest_week_even_when_partly_analysed(self):
        """Regression: the weekly job runs on the Monday *inside* the week it
        closes out, so the latest week can hold a few analysed rows and still
        be in flight. Treating that as measurable scored a freshly added source
        at 0% and would have written it into config as maximum noise."""
        rows = rows_for("2026-W22", "s", analysed=2, unanalysed=8) + rows_for(
            "2026-W30", "s", analysed=5, unanalysed=85
        )
        assert select_window(rows) == {"2026-W22"}

    def test_brand_new_source_gets_no_value_at_all(self):
        """A source that exists only in the in-flight week must fall through to
        the FR-006 default rather than be measured at zero uptake."""
        rows = (
            rows_for("2026-W22", "established", analysed=3, unanalysed=17)
            + rows_for("2026-W30", "established", analysed=5, unanalysed=15)
            + rows_for("2026-W30", "brand-new", analysed=0, unanalysed=20)
        )
        window = select_window(rows)
        _, stats = measure(rows, window)
        assert "brand-new" not in stats
        assert stats["established"]["n"] == 20

    def test_mid_window_zero_uptake_week_is_kept(self):
        """A past week where nothing was selected is a real signal, not noise."""
        rows = (
            rows_for("2026-W22", "s", analysed=0, unanalysed=10)
            + rows_for("2026-W23", "s", analysed=2, unanalysed=8)
            + rows_for("2026-W24", "s", analysed=1, unanalysed=9)
        )
        assert "2026-W22" in select_window(rows)

    def test_window_is_derived_not_hardcoded(self):
        """FR-005c: shifting every week forward must shift the window with it."""
        rows = rows_for("2027-W05", "s", analysed=1, unanalysed=9) + rows_for(
            "2027-W06", "s", analysed=1, unanalysed=9
        )
        assert select_window(rows) == {"2027-W05"}

    def test_single_week_yields_no_window(self):
        """One week of data is always the in-flight week — nothing measurable."""
        assert select_window(rows_for("2026-W22", "s", analysed=1, unanalysed=9)) == set()

    def test_empty_input(self):
        assert select_window([]) == set()


class TestMeasure:
    def test_multiple_is_relative_to_baseline(self):
        rows = (
            rows_for("2026-W22", "low", analysed=1, unanalysed=9)     # 10%
            + rows_for("2026-W22", "high", analysed=6, unanalysed=4)  # 60%
        )
        baseline, stats = measure(rows, {"2026-W22"})
        assert baseline == pytest.approx(0.35)
        assert stats["low"]["multiple"] == pytest.approx(0.10 / 0.35)
        assert stats["high"]["multiple"] == pytest.approx(0.60 / 0.35)

    def test_rows_outside_window_are_ignored(self):
        rows = rows_for("2026-W22", "s", analysed=1, unanalysed=9) + rows_for(
            "2026-W20", "s", analysed=50, unanalysed=0
        )
        _, stats = measure(rows, {"2026-W22"})
        assert stats["s"]["n"] == 10

    def test_empty_window_does_not_divide_by_zero(self):
        assert measure(rows_for("2026-W22", "s", 1, 9), set()) == (0.0, {})


class TestBuildConfig:
    def test_omits_sources_below_sample_threshold(self):
        rows = rows_for("2026-W22", "big", analysed=5, unanalysed=MIN_SAMPLE) + rows_for(
            "2026-W22", "tiny", analysed=0, unanalysed=2
        )
        window = {"2026-W22"}
        baseline, stats = measure(rows, window)
        cfg = build_config(baseline, stats, window)
        assert "big" in cfg["sources"]
        assert "tiny" not in cfg["sources"], "FR-005d: n<15 must get no value"

    def test_boundary_n_equal_to_min_sample_is_kept(self):
        rows = rows_for("2026-W22", "edge", analysed=1, unanalysed=MIN_SAMPLE - 1)
        window = {"2026-W22"}
        baseline, stats = measure(rows, window)
        assert stats["edge"]["n"] == MIN_SAMPLE
        assert "edge" in build_config(baseline, stats, window)["sources"]

    def test_explicit_exclude_omits_a_qualifying_source(self):
        """Hand-picked sources stay under the operator's own control."""
        rows = rows_for("2026-W22", "curated", analysed=1, unanalysed=MIN_SAMPLE)
        window = {"2026-W22"}
        baseline, stats = measure(rows, window)
        assert "curated" in build_config(baseline, stats, window)["sources"]
        cfg = build_config(baseline, stats, window, exclude=["curated"])
        assert "curated" not in cfg["sources"]

    def test_carries_traceability_fields(self):
        """Without these the values cannot be judged stale (FR-005)."""
        rows = rows_for("2026-W22", "s", analysed=2, unanalysed=MIN_SAMPLE)
        window = {"2026-W22", "2026-W23"}
        cfg = build_config(*measure(rows, window), window)
        assert cfg["window"] == "2026-W22..2026-W23"
        assert cfg["measured_at"] and cfg["baseline_uptake"] is not None
        assert cfg["threshold"] > 0
