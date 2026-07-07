"""
Unit tests for gn_resolver — GN 連結判定、batchexecute 回應解析、
enrich_articles 的欄位更新規則與 per-item fail-soft。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import src.gn_resolver as gn
from src.gn_resolver import (
    _parse_batch_response,
    enrich_articles,
    is_gn_article_link,
)


# ── is_gn_article_link ────────────────────────────────────────

def test_gn_rss_articles_link_matches():
    assert is_gn_article_link("https://news.google.com/rss/articles/CBMiVkFV")


def test_gn_articles_link_without_rss_matches():
    assert is_gn_article_link("https://news.google.com/articles/CBMiVkFV")


def test_publisher_link_does_not_match():
    assert not is_gn_article_link("https://udn.com/news/story/7326/9612655")


def test_empty_and_none_do_not_match():
    assert not is_gn_article_link("")
    assert not is_gn_article_link(None)


# ── _parse_batch_response ─────────────────────────────────────

def _batch_line(url):
    inner = json.dumps(["garturlres", url])
    return json.dumps([["wrb.fr", "Fbv4je", inner]])


def test_parse_batch_response_extracts_url():
    text = ")]}'\n\n123\n" + _batch_line("https://udn.com/news/story/1/2")
    assert _parse_batch_response(text) == "https://udn.com/news/story/1/2"


def test_parse_batch_response_rejects_gn_url():
    """解回來還是 news.google.com 表示沒解成功，不能當結果。"""
    text = _batch_line("https://news.google.com/articles/xyz")
    assert _parse_batch_response(text) is None


def test_parse_batch_response_rejects_non_http():
    assert _parse_batch_response(_batch_line("intent://foo")) is None


def test_parse_batch_response_garbage_returns_none():
    assert _parse_batch_response("Fbv4je not-json") is None
    assert _parse_batch_response(")]}'\n\nno match here") is None


# ── enrich_articles ───────────────────────────────────────────

GN_LINK = "https://news.google.com/rss/articles/CBMiVkFV"
REAL_URL = "https://udn.com/news/story/7326/9612655"
LONG_DESC = "為提升機車騎士交通安全觀念，台南市政府響應中央推動機車駕訓政策，攜手監理所加碼補助。"


def _article(**over):
    a = {"title": "機車事故占近8成", "link": GN_LINK,
         "summary": "機車事故占近8成 UDN", "image": ""}
    a.update(over)
    return a


def test_enrich_replaces_link_summary_image(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    monkeypatch.setattr(gn, "fetch_og_meta",
                        lambda s, u: (LONG_DESC, "https://udn.com/img.jpg"))
    a = _article()
    stats = enrich_articles([a], throttle=0)
    assert a["link"] == REAL_URL
    assert a["summary"] == LONG_DESC
    assert a["image"] == "https://udn.com/img.jpg"
    assert stats == {"gn_total": 1, "resolved": 1, "summary_filled": 1,
                     "image_filled": 1, "errors": 0}


def test_enrich_skips_non_gn_link(monkeypatch):
    def boom(*args):
        raise AssertionError("should not be called for non-GN links")
    monkeypatch.setattr(gn, "resolve_gn_link", boom)
    a = _article(link=REAL_URL)
    stats = enrich_articles([a], throttle=0)
    assert a["link"] == REAL_URL
    assert stats["gn_total"] == 0


def test_enrich_failure_keeps_original_fields(monkeypatch):
    def boom(session, link):
        raise RuntimeError("Google changed the API")
    monkeypatch.setattr(gn, "resolve_gn_link", boom)
    a = _article()
    stats = enrich_articles([a], throttle=0)
    assert a["link"] == GN_LINK
    assert a["summary"] == "機車事故占近8成 UDN"
    assert stats["errors"] == 1 and stats["resolved"] == 0


def test_enrich_unresolved_counts_error(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: None)
    a = _article()
    stats = enrich_articles([a], throttle=0)
    assert a["link"] == GN_LINK
    assert stats["errors"] == 1


def test_short_or_echo_desc_keeps_original_summary(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    # 過短
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: ("太短", ""))
    a = _article()
    enrich_articles([a], throttle=0)
    assert a["summary"] == "機車事故占近8成 UDN"
    # 與標題完全相同（且湊滿長度門檻）
    long_title = "機" * 50
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: (long_title, ""))
    b = _article(title=long_title)
    enrich_articles([b], throttle=0)
    assert b["summary"] == "機車事故占近8成 UDN"


def test_existing_image_not_overwritten(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    monkeypatch.setattr(gn, "fetch_og_meta",
                        lambda s, u: (LONG_DESC, "https://other.example/new.jpg"))
    a = _article(image="https://udn.com/original.jpg")
    stats = enrich_articles([a], throttle=0)
    assert a["image"] == "https://udn.com/original.jpg"
    assert stats["image_filled"] == 0


def test_og_meta_failure_after_resolve_keeps_summary(monkeypatch):
    """連結已還原後 og 抓取失敗：link 保留新值、summary/image 保持原樣。"""
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    def boom(session, url):
        raise RuntimeError("publisher timeout")
    monkeypatch.setattr(gn, "fetch_og_meta", boom)
    a = _article()
    stats = enrich_articles([a], throttle=0)
    assert a["link"] == REAL_URL
    assert a["summary"] == "機車事故占近8成 UDN"
    assert stats["resolved"] == 1 and stats["errors"] == 1
