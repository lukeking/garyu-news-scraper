"""
Unit tests for resolve_source_default() and the source-default fallback logic — US2 (009).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import assign_category, resolve_source_default

TAXONOMY = {
    "科技執法": ["測速", "執法"],
    "道安政策": ["道安", "願景"],
    "行人事故": ["行人", "斑馬線"],
}

SOURCE_DEFAULTS = {
    "報導者": "道安政策",
    "區間測速": "科技執法",
}


# ── resolve_source_default (pure helper) ──────────────────────────────────────

def test_resolve_substring_match():
    assert resolve_source_default("Google News 報導者交通", SOURCE_DEFAULTS) == "道安政策"


def test_resolve_no_match_returns_uncategorised():
    assert resolve_source_default("Google News 機車事故", SOURCE_DEFAULTS) == "uncategorised"


def test_resolve_empty_source():
    assert resolve_source_default("", SOURCE_DEFAULTS) == "uncategorised"


def test_resolve_empty_mapping():
    assert resolve_source_default("報導者", {}) == "uncategorised"


# ── fallback-only integration with assign_category (mirrors traffic.py loop) ───

def test_fallback_applied_only_when_uncategorised():
    """Deep source + title with no category token → fallback default (FR-009)."""
    tokens = frozenset(["速度", "城市", "設計"])  # no taxonomy token
    cat = assign_category(tokens, TAXONOMY)
    assert cat == "uncategorised"
    if cat == "uncategorised":
        cat = resolve_source_default("Google News 報導者交通", SOURCE_DEFAULTS)
    assert cat == "道安政策"


def test_title_hit_not_overridden():
    """Title already matched a category → source-default must NOT override (FR-010/SC-005)."""
    tokens = frozenset(["測速", "國道"])  # hits 科技執法
    cat = assign_category(tokens, TAXONOMY)
    assert cat == "科技執法"
    if cat == "uncategorised":  # branch not taken
        cat = resolve_source_default("Google News 報導者交通", SOURCE_DEFAULTS)
    assert cat == "科技執法"  # unchanged


def test_unmapped_uncategorised_stays():
    """Unmapped source + no title hit → stays uncategorised (FR-012)."""
    tokens = frozenset(["速度", "城市"])
    cat = assign_category(tokens, TAXONOMY)
    if cat == "uncategorised":
        cat = resolve_source_default("Google News 機車事故", SOURCE_DEFAULTS)
    assert cat == "uncategorised"
