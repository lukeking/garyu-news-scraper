"""各呼叫端自己的模型變數（GNS-20261019-1vk）：驗 requests.post 實際收到的 url、payload、timeout。
沒設或空字串時退回 GEMINI_MODEL_NAME 那個模型；Gemini 一律換成假的，不碰網路。
"""
import logging
import os
import sys

import pytest
import yaml

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import auto_kb  # noqa: E402
from src import analyzer  # noqa: E402

BASE = "gemini-base-model"
FAKE_KEY = "fake-not-a-real-key"
ENV_NAMES = ("GEMINI_MODEL_HOT_TOPIC", "GEMINI_MODEL_DIGEST", "GEMINI_MODEL_FFXIV", "GEMINI_MODEL_AUTO_KB",
             "GEMINI_HOT_TOPIC_MAX_OUTPUT_TOKENS", "GEMINI_HOT_TOPIC_TIMEOUT_SECONDS", "GEMINI_MAX_OUTPUT_TOKENS")
ARTICLES = [{"title": "台中市科技執法上路", "summary": "台中市自下月起在三處路口啟用科技執法設備，取締闖紅燈與未禮讓行人。" * 5,
             "initial_quality_score": 8, "published": "2026-10-03T01:00:00+00:00", "link": "https://b"}]
FFXIV_ARTICLE = {"title": "t", "source": "s", "summary": "x", "link": "https://l", "content_type": "ffxiv"}


class _Resp:
    status_code = 200
    headers = {}
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def sent(monkeypatch):
    """每次 requests.post 實際送出的模型、輸出上限、timeout。"""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(analyzer, "GEMINI_MODEL", BASE)
    monkeypatch.setattr(analyzer, "load_knowledge_base", lambda: {})
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    calls = []

    def fake_post(url, json=None, timeout=None, headers=None, **kwargs):
        calls.append({"model": url.rsplit("/", 1)[-1].split(":")[0], "timeout": timeout,
                      "max_tokens": json["generationConfig"]["maxOutputTokens"]})
        return _Resp({"candidates": [{"content": {"parts": [{"text": "### 回覆"}]}, "finishReason": "STOP"}]})

    monkeypatch.setattr(analyzer.requests, "post", fake_post)
    return calls


def _hot_topic():
    analyzer.analyze_hot_topic(ARTICLES, "道安政策 · 科技執法", "2026-10-05")


def _digest():
    analyzer.analyze_category_digest(ARTICLES, "道安政策 · 彙整", "2026-10-05")


def _ffxiv():
    analyzer.analyze_article(dict(FFXIV_ARTICLE), FAKE_KEY)


CALLERS = {"GEMINI_MODEL_HOT_TOPIC": _hot_topic, "GEMINI_MODEL_DIGEST": _digest, "GEMINI_MODEL_FFXIV": _ffxiv}


@pytest.mark.parametrize("env_name", sorted(CALLERS))
def test_each_caller_reads_only_its_own_model_variable(sent, monkeypatch, env_name):
    monkeypatch.setenv(env_name, "gemini-own-model")
    for call in CALLERS.values():
        call()
    used = dict(zip(CALLERS, (c["model"] for c in sent)))
    assert used == {name: ("gemini-own-model" if name == env_name else BASE) for name in CALLERS}


@pytest.mark.parametrize("value", [None, "", "   "])
def test_unset_or_blank_variable_falls_back_to_the_shared_model(sent, monkeypatch, value):
    for name in CALLERS:
        if value is not None:
            monkeypatch.setenv(name, value)
    for call in CALLERS.values():
        call()
    assert [c["model"] for c in sent] == [BASE, BASE, BASE]


def test_non_ffxiv_article_ignores_the_ffxiv_model(sent, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL_FFXIV", "gemini-own-model")
    analyzer.analyze_article({"title": "t", "source": "s", "summary": "x", "link": "https://l"}, FAKE_KEY)
    assert sent[0]["model"] == BASE


def test_limits_stay_at_prod_values_when_nothing_is_set(sent):
    _hot_topic()
    _digest()
    assert [(c["max_tokens"], c["timeout"]) for c in sent] == [(8192, 120), (8192, 120)]


def test_hot_topic_has_its_own_output_cap_and_timeout(sent, monkeypatch):
    monkeypatch.setenv("GEMINI_HOT_TOPIC_MAX_OUTPUT_TOKENS", "65536")
    monkeypatch.setenv("GEMINI_HOT_TOPIC_TIMEOUT_SECONDS", "600")
    _hot_topic()
    _digest()
    assert [(c["max_tokens"], c["timeout"]) for c in sent] == [(65536, 600), (8192, 120)]


def test_hot_topic_cap_falls_back_to_the_shared_cap(sent, monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_OUTPUT_TOKENS", "4096")
    _hot_topic()
    assert sent[0]["max_tokens"] == 4096


def test_invalid_hot_topic_number_keeps_the_default_and_says_so(sent, monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_HOT_TOPIC_TIMEOUT_SECONDS", "ten minutes")
    with caplog.at_level(logging.WARNING):
        _hot_topic()
    assert sent[0]["timeout"] == 120
    assert "GEMINI_HOT_TOPIC_TIMEOUT_SECONDS" in caplog.text


def test_own_settings_leave_a_log_line_and_shared_settings_do_not(sent, monkeypatch, caplog):
    with caplog.at_level(logging.INFO):
        _hot_topic()
        assert "這條路徑自己的設定" not in caplog.text
        monkeypatch.setenv("GEMINI_MODEL_HOT_TOPIC", "gemini-4-own")
        _hot_topic()
    assert "這條路徑自己的設定：模型尾段=own，maxOutputTokens=8192，timeout=120 秒" in caplog.text


def test_analyze_all_log_names_the_model_the_batch_uses(sent, monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_MODEL_FFXIV", "gemini-4-own")
    with caplog.at_level(logging.INFO):
        analyzer.analyze_all([dict(FFXIV_ARTICLE)], delay=0)
    assert "模型尾段=own，" in caplog.text


@pytest.mark.parametrize("candidate", [
    {"finishReason": "MAX_TOKENS"},
    {"content": {}, "finishReason": "MAX_TOKENS"},
    {"content": {"parts": [{"thoughtSignature": "sig"}]}, "finishReason": "STOP"},
])
def test_response_without_text_returns_none_once_and_logs_the_reason(monkeypatch, caplog, candidate):
    posts = []

    def fake_post(url, **kwargs):
        posts.append(url)
        return _Resp({"candidates": [candidate]})

    monkeypatch.setattr(analyzer.requests, "post", fake_post)
    with caplog.at_level(logging.WARNING):
        assert analyzer._call_gemini("prompt", FAKE_KEY) is None
    assert len(posts) == 1
    assert f"回應沒有文字（finishReason={candidate['finishReason']}" in caplog.text


@pytest.mark.parametrize("own, shared, expected", [
    ("gemini-own", "gemini-shared", "gemini-own"),
    ("", "gemini-shared", "gemini-shared"),
    (None, "gemini-shared", "gemini-shared"),
    (None, None, "gemini-2.5-flash"),
])
def test_auto_kb_reads_its_own_model_variable_first(monkeypatch, own, shared, expected):
    for name, value in (("GEMINI_MODEL_AUTO_KB", own), ("GEMINI_MODEL_NAME", shared)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert auto_kb._gemini_model() == expected


@pytest.mark.parametrize("workflow, command, names", [
    ("weekly.yml", "python main.py", ["GEMINI_MODEL_FFXIV"]),
    ("weekly.yml", "python scripts/traffic_weekly_analysis.py",
     ["GEMINI_MODEL_HOT_TOPIC", "GEMINI_MODEL_DIGEST", "GEMINI_HOT_TOPIC_MAX_OUTPUT_TOKENS", "GEMINI_HOT_TOPIC_TIMEOUT_SECONDS"]),
    ("auto-kb.yml", "python scripts/auto_kb.py", ["GEMINI_MODEL_AUTO_KB"]),
])
def test_workflow_passes_each_variable_to_the_step_that_reads_it(workflow, command, names):
    with open(os.path.join(_REPO, ".github", "workflows", workflow), encoding="utf-8") as f:
        jobs = yaml.safe_load(f)["jobs"].values()
    env = next(s["env"] for job in jobs for s in job["steps"] if s.get("run") == command)
    assert {n: env.get(n) for n in names} == {n: "${{ vars.%s }}" % n for n in names}
