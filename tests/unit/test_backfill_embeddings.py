"""scripts/backfill_embeddings.py：只補 null、生成失敗不寫、乾跑不動任何東西。"""
import os
import sys

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import backfill_embeddings as bf  # noqa: E402
from src.analyzer import EMBED_DIMENSIONS  # noqa: E402


class _Query:
    def __init__(self, client, op, payload=None):
        self.client, self.op, self.payload, self.filters = client, op, payload, []

    def select(self, cols):
        self.filters.append(("select", cols))
        return self

    def update(self, payload):
        return _Query(self.client, "update", payload)

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def is_(self, col, val):
        self.filters.append(("is", col, val))
        return self

    def order(self, col):
        return self

    def range(self, lo, hi):
        self.filters.append(("range", lo, hi))
        return self

    def execute(self):
        class R:
            pass
        r = R()
        if self.op == "update":
            self.client.updates.append((self.payload, self.filters))
            row_id = next(f[2] for f in self.filters if f[:2] == ("eq", "id"))
            r.data = [] if row_id in self.client.already_filled else [{"id": row_id}]
        else:
            self.client.selects.append(self.filters)
            r.data = self.client.rows if ("range", 0, 999) in self.filters else []
        return r


class _Client:
    def __init__(self, rows, already_filled=()):
        self.rows, self.already_filled = rows, set(already_filled)
        self.selects, self.updates = [], []

    def table(self, name):
        assert name == "articles"
        return _Query(self, "select")


_ROWS = [{"id": 1, "title": "甲", "summary": "a"}, {"id": 2, "title": "乙", "summary": "b"}]


def _embed_ok(candidates):
    for c in candidates:
        c["embedding"] = [0.1] * EMBED_DIMENSIONS


def test_fetch_asks_only_for_null_traffic_rows():
    sb = _Client(_ROWS)
    bf.fetch_missing(sb)
    assert ("eq", "content_type", "traffic") in sb.selects[0]
    assert ("is", "embedding", "null") in sb.selects[0]


def test_dry_run_neither_embeds_nor_writes():
    sb, called = _Client(_ROWS), []
    out = bf.backfill(sb, apply=False, embed=called.append)
    assert called == [] and sb.updates == []
    assert out == {"missing": 2, "written": 0, "failed": 0, "skipped_filled": 0}


def test_candidates_carry_no_embedding_key():
    """attach_embeddings 只替缺 `embedding` 鍵的 dict 生成；帶著 None 進去會一次都不呼叫。"""
    seen = []
    bf.backfill(_Client(_ROWS), apply=True, embed=lambda cs: seen.extend(dict(c) for c in cs) or _embed_ok(cs))
    assert seen and all("embedding" not in c for c in seen)
    assert [c["title"] for c in seen] == ["甲", "乙"]


def test_failed_generation_is_not_written_and_every_write_is_guarded():
    def embed_half(cs):
        cs[0]["embedding"] = None
        cs[1]["embedding"] = [0.2] * EMBED_DIMENSIONS
    sb = _Client(_ROWS)
    out = bf.backfill(sb, apply=True, embed=embed_half)
    assert out == {"missing": 2, "written": 1, "failed": 1, "skipped_filled": 0}
    payload, filters = sb.updates[0]
    assert len(sb.updates) == 1 and len(payload["embedding"]) == EMBED_DIMENSIONS
    assert ("eq", "id", 2) in filters and ("is", "embedding", "null") in filters


def test_wrong_dimension_is_treated_as_failure():
    out = bf.backfill(_Client(_ROWS[:1]), apply=True,
                      embed=lambda cs: cs[0].update(embedding=[0.1] * 3))
    assert out["failed"] == 1 and out["written"] == 0


def test_guard_hit_is_counted_not_reported_as_written():
    sb = _Client(_ROWS, already_filled={1})
    out = bf.backfill(sb, apply=True, embed=_embed_ok)
    assert out == {"missing": 2, "written": 1, "failed": 0, "skipped_filled": 1}
