"""spec 020 SC-001：`scripts/dry_run_counts.py` 的取數與比對。全部離線：假的 requests 只有 `get`，
送出別的方法就 AttributeError；`load_dotenv` 換成不做事的記錄器，真的 `.env` 不載入；憑證都是假值。"""
import json
import os
import re
import sys

import pytest

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _REPO)

import scripts.dry_run_counts as m  # noqa: E402
from src import pipeline_config  # noqa: E402

SUPABASE_URL = "https://fake-project.supabase.test"
SERVICE_KEY = "service-key-for-test-only"
CF_TOKEN = "cf-token-for-test-only"
CF_ACCOUNT = "acct0123"
KEYS = ["hot_topic_reports", "articles", "buffer", "digest_pool", "knowledge_base", "deploy_traffic", "deploy_ffxiv"]
DIGEST_YAML = "category_digest:\n  道安政策:\n    include_categories: [路權政策, 科技執法]\n  行人事故: {}\n"
DIGEST_IN = 'in.("科技執法","行人事故","路權政策","道安政策")'
CF_BASE = "https://api.cloudflare.com/client/v4/accounts/acct0123/pages/projects/"


class FakeResponse:
    def __init__(self, status=206, headers=None, body=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeRequests:
    """假的 requests 模組：只有 get 與例外類別。route(url, params) 回 FakeResponse 或丟例外。"""

    class RequestException(Exception):
        pass

    class ConnectionError(RequestException):
        pass

    def __init__(self, route):
        self.route = route
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
        return self.route(url, dict(params or {}))


SUPABASE_TOTALS = {"hot_topic_reports": 812, "articles": 15234, "knowledge_base": 431}


def ok_route(url, params):
    if url.startswith(CF_BASE):
        project = url[len(CF_BASE):]
        return FakeResponse(200, body={"success": True, "errors": [], "result": {
            "name": project, "latest_deployment": {"id": f"dep-{project}", "created_on": f"2026-11-09T04:{len(project)}:00Z"}}})
    table = url.rsplit("/", 1)[1]
    if table == "articles" and "major_category" in params:
        total = 47
    elif table == "articles" and "content_type" in params:
        total = 760
    else:
        total = SUPABASE_TOTALS[table]
    return FakeResponse(206, headers={"Content-Range": f"0-0/{total}"}, body=[{"id": 1}])


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", CF_TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", CF_ACCOUNT)
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    cfg = tmp_path / "pipeline_config.yml"
    cfg.write_text(DIGEST_YAML, encoding="utf-8")
    monkeypatch.setenv("PIPELINE_CONFIG_YML_PATH", str(cfg))
    monkeypatch.setattr(pipeline_config, "_pipeline_config_cache", None)


def use(monkeypatch, route=ok_route):
    fake = FakeRequests(route)
    monkeypatch.setattr(m, "requests", fake)
    return fake


def lines(capsys):
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]


def take(tmp_path, capsys, name="before.json"):
    out = tmp_path / "pool" / name
    code = m.main(["take", "--out", str(out)])
    return code, out, lines(capsys)


def counts_file(path, overrides=None, drop=()):
    items = {k: {"name": k, "value": i} for i, k in enumerate(KEYS)}
    items.update(overrides or {})
    for k in drop:
        items.pop(k)
    path.write_text(json.dumps({"run_mode": "dry-input", "taken_at": "2026-11-16T00:00:00+00:00", "items": items}),
                    encoding="utf-8")
    return str(path)


def compare(tmp_path, capsys, before, after):
    code = m.main(["compare", before, after])
    return code, lines(capsys)


# ── 比對（T014）

def test_all_same_is_zero_and_last_line_says_so(tmp_path, capsys):
    a, b = counts_file(tmp_path / "a.json"), counts_file(tmp_path / "b.json")
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 0
    assert out[-1] == "[計數比對] 結果：7 項都相同"


def test_one_value_differs_is_nonzero_and_names_the_item(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json")
    b = counts_file(tmp_path / "b.json", {"buffer": {"name": "buffer 筆數", "value": 761}})
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert out[-1] == "[計數比對] 結果：不同 1 項（buffer）；未取得 0 項（無）"
    assert any("buffer" in ln and "2" in ln and "761" in ln and "不同" in ln for ln in out[:-1]), out


@pytest.mark.parametrize("side", ["before", "after"])
def test_unavailable_on_either_side_is_nonzero_and_names_the_item(tmp_path, capsys, side):
    gap = {"deploy_ffxiv": {"name": "最後部署時間（garyu-ffxiv-news）", "unavailable": "HTTP 403"}}
    a = counts_file(tmp_path / "a.json", gap if side == "before" else None)
    b = counts_file(tmp_path / "b.json", gap if side == "after" else None)
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert out[-1] == "[計數比對] 結果：不同 0 項（無）；未取得 1 項（deploy_ffxiv）"
    assert any("deploy_ffxiv" in ln and "HTTP 403" in ln for ln in out[:-1]), out


def test_item_missing_from_one_file_counts_as_unavailable(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json")
    b = counts_file(tmp_path / "b.json", drop=["knowledge_base"])
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert out[-1] == "[計數比對] 結果：不同 0 項（無）；未取得 1 項（knowledge_base）"
    assert any("knowledge_base" in ln and "檔裡沒有這一項" in ln for ln in out), out


def test_expected_item_missing_from_both_files_is_not_silently_dropped(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json", drop=["digest_pool"])
    b = counts_file(tmp_path / "b.json", drop=["digest_pool"])
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert "未取得 1 項（digest_pool）" in out[-1]


def test_extra_item_only_in_one_file_counts_as_unavailable(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json", {"surprise": {"name": "多的", "value": 1}})
    b = counts_file(tmp_path / "b.json")
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert "未取得 1 項（surprise）" in out[-1]


def test_both_differ_and_unavailable_are_listed_in_item_order(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json", {"deploy_traffic": {"name": "x", "unavailable": "沒設 token"}})
    b = counts_file(tmp_path / "b.json", {"articles": {"name": "x", "value": 99}, "hot_topic_reports": {"name": "x", "value": 98}})
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert out[-1] == "[計數比對] 結果：不同 2 項（hot_topic_reports、articles）；未取得 1 項（deploy_traffic）"


def test_value_type_matters(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json", {"articles": {"name": "x", "value": 5}})
    b = counts_file(tmp_path / "b.json", {"articles": {"name": "x", "value": "5"}})
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 1
    assert "不同 1 項（articles）" in out[-1]


def test_missing_file_says_which_and_exits_2(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json")
    missing = str(tmp_path / "nope.json")
    code, out = compare(tmp_path, capsys, a, missing)
    assert code == 2
    assert out[-1] == f"[計數比對] 結果：沒有比對（找不到 {missing}）"


def test_not_json_says_which_and_exits_2(tmp_path, capsys):
    a = counts_file(tmp_path / "a.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    code, out = compare(tmp_path, capsys, str(bad), a)
    assert code == 2
    assert out[-1].startswith(f"[計數比對] 結果：沒有比對（{bad} 不是 JSON：")


@pytest.mark.parametrize("data, why", [
    ([1, 2], "頂層不是物件"),
    ({"items": [1]}, "items 不是物件"),
    ({"taken_at": "x"}, "items 不是物件"),
    ({"items": {"buffer": 3}}, "buffer 不是物件"),
    ({"items": {"buffer": {"name": "x"}}}, "buffer 要剛好有 value 或 unavailable 其中一個"),
    ({"items": {"buffer": {"name": "x", "value": 1, "unavailable": "y"}}}, "buffer 要剛好有 value 或 unavailable 其中一個"),
])
def test_wrong_shape_says_which_and_why_and_exits_2(tmp_path, capsys, data, why):
    a = counts_file(tmp_path / "a.json")
    bad = tmp_path / "shape.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    code, out = compare(tmp_path, capsys, a, str(bad))
    assert code == 2
    assert out[-1] == f"[計數比對] 結果：沒有比對（{bad} 的形狀不對：{why}）"


def test_unexpected_exception_still_ends_with_a_result_line(tmp_path, capsys, monkeypatch):
    a, b = counts_file(tmp_path / "a.json"), counts_file(tmp_path / "b.json")

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(m, "_compare_items", boom)
    code, out = compare(tmp_path, capsys, a, b)
    assert code == 2
    assert out[-1] == "[計數比對] 結果：沒有比對完（RuntimeError: boom）"


# ── 取數（T015）

def test_take_sends_only_the_pinned_get_requests_and_writes_the_file(tmp_path, capsys, monkeypatch):
    fake = use(monkeypatch)
    code, out, printed = take(tmp_path, capsys)
    assert code == 0
    sb = {"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}", "Prefer": "count=exact"}
    rest = SUPABASE_URL + "/rest/v1/"
    buffer = {"select": "id", "limit": "1", "content_type": "eq.traffic", "hot_topic_analyzed": "eq.false"}
    expected = [
        (rest + "hot_topic_reports", {"select": "id", "limit": "1"}, sb),
        (rest + "articles", {"select": "id", "limit": "1"}, sb),
        (rest + "articles", buffer, sb),
        (rest + "articles", {**buffer, "major_category": DIGEST_IN}, sb),
        (rest + "knowledge_base", {"select": "jp_term", "limit": "1"}, sb),
        (CF_BASE + "garyu-traffic-news", {}, {"Authorization": f"Bearer {CF_TOKEN}"}),
        (CF_BASE + "garyu-ffxiv-news", {}, {"Authorization": f"Bearer {CF_TOKEN}"}),
    ]
    assert [(c["url"], c["params"], c["headers"]) for c in fake.calls] == expected
    assert all(c["timeout"] for c in fake.calls), "每個請求都要有 timeout"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["run_mode"] == "formal"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", data["taken_at"])
    values = {k: v.get("value") for k, v in data["items"].items()}
    assert values == {"hot_topic_reports": 812, "articles": 15234, "buffer": 760, "digest_pool": 47,
                      "knowledge_base": 431, "deploy_traffic": "2026-11-09T04:18:00Z", "deploy_ffxiv": "2026-11-09T04:16:00Z"}
    assert list(data["items"]) == KEYS
    assert printed[-1] == f"[計數] 結果：寫入 {out}（7 項，未取得 0 項）"


def test_take_then_compare_round_trip_is_all_same(tmp_path, capsys, monkeypatch):
    use(monkeypatch)
    _, a, _ = take(tmp_path, capsys, "a.json")
    _, b, _ = take(tmp_path, capsys, "b.json")
    code, out = compare(tmp_path, capsys, str(a), str(b))
    assert code == 0
    assert out[-1] == "[計數比對] 結果：7 項都相同"


@pytest.mark.parametrize("level", ["dry-input", "dry-full"])
def test_file_carries_the_run_mode(tmp_path, capsys, monkeypatch, level):
    use(monkeypatch)
    monkeypatch.setenv("GARYU_RUN_MODE", level)
    _, out, _ = take(tmp_path, capsys)
    assert json.loads(out.read_text(encoding="utf-8"))["run_mode"] == level


def test_unknown_run_mode_writes_nothing_and_says_why(tmp_path, capsys, monkeypatch):
    use(monkeypatch)
    monkeypatch.setenv("GARYU_RUN_MODE", "full")
    code, out, printed = take(tmp_path, capsys)
    assert code == 2
    assert not out.exists()
    assert printed[-1].startswith("[計數] 結果：沒有寫檔（ValueError: ")
    assert not any("寫入" in ln for ln in printed)


def test_secrets_never_printed_or_written(tmp_path, capsys, monkeypatch):
    use(monkeypatch)
    code, out, printed = take(tmp_path, capsys)
    text = "\n".join(printed) + out.read_text(encoding="utf-8")
    for secret in (SERVICE_KEY, CF_TOKEN, CF_ACCOUNT, SUPABASE_URL):
        assert secret not in text


def item(out, key):
    return json.loads(out.read_text(encoding="utf-8"))["items"][key]


@pytest.mark.parametrize("header, expected", [
    ("0-0/123", 123),
    ("*/0", 0),
    ("0-0/0", 0),
])
def test_count_comes_from_content_range_total(tmp_path, capsys, monkeypatch, header, expected):
    use(monkeypatch, lambda url, params: ok_route(url, params) if url.startswith(CF_BASE)
        else FakeResponse(206, headers={"Content-Range": header}))
    _, out, _ = take(tmp_path, capsys)
    assert item(out, "articles")["value"] == expected


@pytest.mark.parametrize("status", [200, 206])
def test_postgrest_success_statuses(tmp_path, capsys, monkeypatch, status):
    use(monkeypatch, lambda url, params: ok_route(url, params) if url.startswith(CF_BASE)
        else FakeResponse(status, headers={"Content-Range": "0-0/9"}))
    _, out, _ = take(tmp_path, capsys)
    assert item(out, "hot_topic_reports") == {"name": "報告數（hot_topic_reports）", "value": 9}


@pytest.mark.parametrize("headers, reason", [
    ({"Content-Range": "0-0/*"}, "Content-Range 沒有總數（'0-0/*'）"),
    ({}, "Content-Range 沒有總數（None）"),
])
def test_count_without_total_is_unavailable_not_filled_in(tmp_path, capsys, monkeypatch, headers, reason):
    use(monkeypatch, lambda url, params: ok_route(url, params) if url.startswith(CF_BASE)
        else FakeResponse(206, headers=headers))
    code, out, printed = take(tmp_path, capsys)
    assert code == 0
    assert item(out, "buffer") == {"name": "buffer 筆數", "unavailable": reason}
    assert f"[計數] buffer 筆數：未取得：{reason}" in printed
    assert printed[-1] == f"[計數] 結果：寫入 {out}（7 項，未取得 5 項）"


@pytest.mark.parametrize("status, body, reason", [
    (401, {"code": "PGRST301", "message": "JWT expired"}, "HTTP 401：PGRST301 JWT expired"),
    (500, ValueError("no json"), "HTTP 500"),
    (300, None, "HTTP 300"),
    (199, None, "HTTP 199"),
])
def test_supabase_http_error_is_unavailable(tmp_path, capsys, monkeypatch, status, body, reason):
    use(monkeypatch, lambda url, params: ok_route(url, params) if url.startswith(CF_BASE)
        else FakeResponse(status, headers={"Content-Range": "0-0/9"}, body=body))
    _, out, printed = take(tmp_path, capsys)
    assert item(out, "knowledge_base")["unavailable"] == reason
    assert f"[計數] 術語庫條目數：未取得：{reason}" in printed


def test_request_exception_is_unavailable_and_names_only_the_type(tmp_path, capsys, monkeypatch):
    def route(url, params):
        raise FakeRequests.ConnectionError(f"HTTPSConnectionPool(host='{url}') refused")

    use(monkeypatch, route)
    code, out, printed = take(tmp_path, capsys)
    assert code == 0
    for k in KEYS:
        assert item(out, k)["unavailable"] == "請求失敗（ConnectionError）"
    assert "fake-project" not in "\n".join(printed)


def test_missing_supabase_env_skips_those_requests(tmp_path, capsys, monkeypatch):
    fake = use(monkeypatch)
    monkeypatch.delenv("SUPABASE_URL")
    _, out, printed = take(tmp_path, capsys)
    reason = "未設 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY／SUPABASE_KEY"
    for k in KEYS[:5]:
        assert item(out, k)["unavailable"] == reason
    assert [c["url"] for c in fake.calls] == [CF_BASE + "garyu-traffic-news", CF_BASE + "garyu-ffxiv-news"]
    assert printed[-1] == f"[計數] 結果：寫入 {out}（7 項，未取得 5 項）"


def test_supabase_key_falls_back_to_supabase_key(tmp_path, capsys, monkeypatch):
    fake = use(monkeypatch)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY")
    monkeypatch.setenv("SUPABASE_KEY", "anon-for-test")
    take(tmp_path, capsys)
    assert fake.calls[0]["headers"]["apikey"] == "anon-for-test"


@pytest.mark.parametrize("missing", ["CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"])
def test_missing_cloudflare_env_skips_those_requests(tmp_path, capsys, monkeypatch, missing):
    fake = use(monkeypatch)
    monkeypatch.delenv(missing)
    _, out, _ = take(tmp_path, capsys)
    for k in ("deploy_traffic", "deploy_ffxiv"):
        assert item(out, k)["unavailable"] == "未設 CLOUDFLARE_API_TOKEN 或 CLOUDFLARE_ACCOUNT_ID"
    assert not any(c["url"].startswith("https://api.cloudflare.com") for c in fake.calls)


@pytest.mark.parametrize("status, body, reason", [
    (403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]},
     "HTTP 403：10000 Authentication error"),
    (200, {"result": {"latest_deployment": None}}, "回應沒有 result.latest_deployment.created_on"),
    (200, {"result": {"latest_deployment": {"created_on": ""}}}, "回應沒有 result.latest_deployment.created_on"),
    (200, {"result": {"latest_deployment": {"created_on": 5}}}, "回應沒有 result.latest_deployment.created_on"),
    (200, {"result": []}, "回應沒有 result.latest_deployment.created_on"),
    (200, [], "回應沒有 result.latest_deployment.created_on"),
    (201, {"result": {"latest_deployment": {"created_on": "2026-11-09T04:00:00Z"}}}, "HTTP 201"),
])
def test_cloudflare_without_a_deployment_time_is_unavailable(tmp_path, capsys, monkeypatch, status, body, reason):
    use(monkeypatch, lambda url, params: FakeResponse(status, body=body) if url.startswith(CF_BASE)
        else ok_route(url, params))
    _, out, printed = take(tmp_path, capsys)
    assert item(out, "deploy_traffic")["unavailable"] == reason
    assert f"[計數] 最後部署時間（garyu-traffic-news）：未取得：{reason}" in printed


def test_empty_digest_config_is_unavailable_and_sends_no_request(tmp_path, capsys, monkeypatch):
    fake = use(monkeypatch)
    cfg = tmp_path / "empty.yml"
    cfg.write_text("buffer:\n  max_age_weeks: 8\n", encoding="utf-8")
    monkeypatch.setenv("PIPELINE_CONFIG_YML_PATH", str(cfg))
    _, out, _ = take(tmp_path, capsys)
    assert item(out, "digest_pool")["unavailable"].startswith("pipeline_config 的 category_digest 是空的")
    assert not any("major_category" in c["params"] for c in fake.calls)


def test_invalid_pipeline_config_is_unavailable(tmp_path, capsys, monkeypatch):
    use(monkeypatch)
    cfg = tmp_path / "bad.yml"
    cfg.write_text("quality_score_weights:\n  keyword_match_ratio: 0.9\n", encoding="utf-8")
    monkeypatch.setenv("PIPELINE_CONFIG_YML_PATH", str(cfg))
    _, out, _ = take(tmp_path, capsys)
    assert item(out, "digest_pool")["unavailable"].startswith("讀不了 pipeline_config（RuntimeError: ")


def test_write_failure_says_nothing_was_written(tmp_path, capsys, monkeypatch):
    use(monkeypatch)
    blocker = tmp_path / "pool"
    blocker.write_text("a file, not a directory", encoding="utf-8")
    code, out, printed = take(tmp_path, capsys)
    assert code == 2
    assert printed[-1].startswith(f"[計數] 結果：沒有寫檔（寫不進 {out}：")
    assert not any("結果：寫入" in ln for ln in printed)


def test_unexpected_exception_in_take_still_ends_with_a_result_line(tmp_path, capsys, monkeypatch):
    use(monkeypatch)

    def boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(m, "take_counts", boom)
    code, out, printed = take(tmp_path, capsys)
    assert code == 2
    assert printed[-1] == "[計數] 結果：沒有寫檔（RuntimeError: boom）"


# ── 只發 GET、腳本本身的約束

def test_source_only_uses_requests_get():
    with open(m.__file__, encoding="utf-8") as fh:
        src = fh.read()
    assert set(re.findall(r"\brequests\.(\w+)", src)) <= {"get", "RequestException"}
    assert "create_client" not in src and "supabase import" not in src


def test_source_does_not_read_the_run_mode_variable_itself():
    with open(m.__file__, encoding="utf-8") as fh:
        assert "GARYU_RUN_MODE" not in fh.read()


def test_help_shows_both_modes_with_full_calls(capsys):
    with pytest.raises(SystemExit) as exc:
        m.main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "scripts/dry_run_counts.py take --out" in text
    assert "scripts/dry_run_counts.py compare" in text
