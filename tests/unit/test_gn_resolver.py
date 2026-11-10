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
                        lambda s, u: (LONG_DESC, "https://udn.com/img.jpg", ""))
    a = _article()
    stats = enrich_articles([a], throttle=0)
    assert a["link"] == REAL_URL
    assert a["summary"] == LONG_DESC
    assert a["image"] == "https://udn.com/img.jpg"
    assert stats == {"gn_total": 1, "resolved": 1, "summary_filled": 1,
                     "image_filled": 1, "errors": 0, "error_domains": {}, "published_from_page": 0}


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
    # resolve returning None (not raising) must still surface in 失敗網域, under the
    # GN domain, so a total decode outage isn't masked as "nothing blocked".
    assert stats["error_domains"] == {"news.google.com": None}


def test_error_domains_keeps_403_over_later_none(monkeypatch):
    """同一 publisher 先 403 後又出現無 status 的失敗，不能把 403 洗掉——
    403 才是被擋的訊號。"""
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    calls = {"n": 0}

    def flaky(session, url):
        calls["n"] += 1
        if calls["n"] == 1:
            e = RuntimeError("blocked")
            e.response = type("R", (), {"status_code": 403})()
            raise e
        raise ConnectionError("transient")
    monkeypatch.setattr(gn, "fetch_og_meta", flaky)
    stats = enrich_articles([_article(), _article()], throttle=0)
    assert stats["error_domains"] == {"udn.com": 403}


def test_short_or_echo_desc_keeps_original_summary(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    # 過短
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: ("太短", "", ""))
    a = _article()
    enrich_articles([a], throttle=0)
    assert a["summary"] == "機車事故占近8成 UDN"
    # 與標題完全相同（且湊滿長度門檻）
    long_title = "機" * 50
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: (long_title, "", ""))
    b = _article(title=long_title)
    enrich_articles([b], throttle=0)
    assert b["summary"] == "機車事故占近8成 UDN"


def test_existing_image_not_overwritten(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    monkeypatch.setattr(gn, "fetch_og_meta",
                        lambda s, u: (LONG_DESC, "https://other.example/new.jpg", ""))
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


def test_enrich_records_failing_publisher_domain(monkeypatch):
    """og 抓取失敗時，error_domains 記的是 publisher 網域＋HTTP status，
    而不是 news.google.com 連結——這是觀測被擋名單擴散的唯一訊號。"""
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)

    class Blocked(Exception):
        def __init__(self):
            self.response = type("R", (), {"status_code": 403})()

    def boom(session, url):
        raise Blocked()
    monkeypatch.setattr(gn, "fetch_og_meta", boom)
    a = _article()
    stats = enrich_articles([a], throttle=0)
    assert stats["error_domains"] == {"udn.com": 403}


def test_error_domains_falls_back_to_gn_when_resolve_fails(monkeypatch):
    """resolve 階段就失敗（拿不到 publisher URL）時，網域記成 news.google.com，
    自然與 publisher 被擋的訊號區分開。"""
    def boom(session, link):
        raise RuntimeError("Google changed the API")
    monkeypatch.setattr(gn, "resolve_gn_link", boom)
    stats = enrich_articles([_article()], throttle=0)
    assert list(stats["error_domains"]) == ["news.google.com"]


# ── 送出的 UA 與 publisher 頁的解碼（2026-11-10） ─────────────────

class _Resp:
    def __init__(self, text="", content=b"", headers=None):
        self.text, self.content, self.headers = text, content, headers or {}

    def raise_for_status(self):
        pass


class _RecordingSession:
    """記下每個請求帶的 header；GET GN 頁回 decode 參數、POST 回 batch、其他 GET 回 publisher 頁。"""
    def __init__(self, page=b""):
        self.headers_seen, self.page = [], page

    def get(self, url, headers=None, timeout=None):
        self.headers_seen.append(headers)
        if "news.google.com" in url:
            return _Resp(text='data-n-a-id="I" data-n-a-ts="1" data-n-a-sg="S"')
        return _Resp(content=self.page, headers={"Content-Type": "text/html; charset=utf-8"})

    def post(self, url, data=None, headers=None, timeout=None):
        self.headers_seen.append(headers)
        return _Resp(text=")]}'\n\n" + _batch_line(REAL_URL))


def test_requests_identify_as_garyunewsbot_not_a_browser():
    """憲章 IV：GN 還原（GET＋POST）與 publisher 頁都送正式 UA；11-10 本機三輪量測，換 UA 不改變結果。"""
    session = _RecordingSession(page=b'<meta property="og:description" content="x">')
    assert gn.resolve_gn_link(session, GN_LINK) == REAL_URL
    gn.fetch_og_meta(session, REAL_URL)
    agents = [h["User-Agent"] for h in session.headers_seen]
    assert len(agents) == 3
    assert all("GaryuNewsBot" in ua and "Chrome" not in ua for ua in agents), agents


def test_declared_utf8_page_is_not_decoded_by_charset_guess(monkeypatch):
    """GNS-20261108-b6c：頁面宣告 utf-8 但位元組不全合法時，不交給偵測去猜（當時猜成 PT154／cp866 → 西里爾亂碼）。"""
    import bs4.dammit
    monkeypatch.setattr(bs4.dammit, "chardet_dammit", lambda s: "ptcp154")
    html = ('<html><head><meta charset="utf-8"><meta property="og:description" content="'
            + LONG_DESC + '"></head><body>').encode("utf-8") + b"\xe4\xba"  # 截在一個中文字中間
    desc, _, _ = gn.fetch_og_meta(_RecordingSession(page=html), REAL_URL)
    assert desc == LONG_DESC


# ── 媒體頁的刊出日期（GNS-20261108-a7k，2026-11-10） ─────────────────

def _page(head):
    return f"<html><head>{head}</head><body></body></html>".encode("utf-8")


def test_page_date_from_article_published_time_in_utc():
    head = '<meta property="article:published_time" content="2026-10-01T10:56:00+08:00">'
    _, _, published = gn.fetch_og_meta(_RecordingSession(page=_page(head)), REAL_URL)
    assert published == "2026-10-01T02:56:00+00:00"


def test_page_date_falls_back_to_jsonld_date_published():
    head = ('<script type="application/ld+json">{"@context": "https://schema.org", '
            '"@graph": [{"@type": "NewsArticle", "datePublished": "2019-03-05T08:00:00Z"}]}</script>')
    _, _, published = gn.fetch_og_meta(_RecordingSession(page=_page(head)), REAL_URL)
    assert published == "2019-03-05T08:00:00+00:00"


def test_page_without_date_returns_empty():
    _, _, published = gn.fetch_og_meta(_RecordingSession(page=_page('<meta property="og:title" content="t">')), REAL_URL)
    assert published == ""


def test_enrich_replaces_gn_published_with_page_date(monkeypatch):
    """GN 給的 published 跟刊出媒體對不上（公視 41 篇被固定成 09-14）；讀得到媒體頁日期就用它。"""
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: (LONG_DESC, "", "2019-03-05T08:00:00+00:00"))
    a = _article(published="2026-09-14T07:00:00+00:00")
    stats = enrich_articles([a], throttle=0)
    assert a["published"] == "2019-03-05T08:00:00+00:00"
    assert stats["published_from_page"] == 1


def test_enrich_keeps_gn_published_when_page_has_no_date(monkeypatch):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: (LONG_DESC, "", ""))
    a = _article(published="2026-11-09T07:00:00+00:00")
    stats = enrich_articles([a], throttle=0)
    assert a["published"] == "2026-11-09T07:00:00+00:00"
    assert stats["published_from_page"] == 0


def test_summary_line_counts_page_dates(monkeypatch, caplog):
    """FOCUS (3) 逐字引用這行；「用媒體頁日期」是 0 時，看得出是頁面都沒日期，不是沒有舊文（`[充實後過時]` 只印擋下數）。"""
    import logging
    dates = iter(["2026-11-09T01:00:00+00:00", ""])
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, l: REAL_URL)
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, u: (LONG_DESC, "", next(dates)))
    with caplog.at_level(logging.INFO, logger="src.gn_resolver"):
        enrich_articles([_article(), _article()], throttle=0)
    assert "GN 充實：2 篇中 2 還原連結、2 補摘要、0 補圖、1 用媒體頁日期、0 失敗" in caplog.text
