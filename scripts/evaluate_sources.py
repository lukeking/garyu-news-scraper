#!/usr/bin/env python3
"""上線前評估提案來源清單（014 C3）：跑真的 collect() → filter()，印逐來源漏斗、匯流四類標題、embedding 篇數、收集耗時。
Supabase client 換成只放行 table().select() 的代理，任何寫入嘗試都以非零結束。會呼叫 Gemini embedding（計費）。
提案檔：sources（同 sources_traffic.yml 格式）＋選用 source_defaults {來源名稱片段: 類別}。"""
import argparse
import contextlib
import os
import sys
import tempfile
import time
from types import SimpleNamespace

import yaml

_REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _REPO)

import src.analyzer as analyzer  # noqa: E402
import src.collector as collector  # noqa: E402
import src.pipeline_config as pipeline_config  # noqa: E402
import src.storage as storage  # noqa: E402
from src.pipeline.traffic import TrafficCategory, confluence_categories, funnel_line  # noqa: E402

DEFAULT_CATEGORIES = "config/categories_traffic.yml"


class ProposalError(ValueError):
    pass


class WriteAttempt(RuntimeError):
    pass


def _refuse(attempts: list, table: str, attr: str):
    attempts.append((table, attr))
    raise WriteAttempt(f"評估工具是唯讀的，拒絕 {table}.{attr}")


class ReadOnlyClient:
    """只放行 table(name).select(...)；其餘一律記進 attempts 再 raise。
    filter() 會吞例外，所以呼叫端結束後要查 attempts，不能只靠 raise。"""

    def __init__(self, client, attempts: list):
        self._client, self._attempts = client, attempts

    def table(self, name):
        return _ReadOnlyTable(self._client, name, self._attempts)

    def __getattr__(self, attr):
        _refuse(self._attempts, "<client>", attr)


class _ReadOnlyTable:
    def __init__(self, client, name, attempts: list):
        self._client, self._name, self._attempts = client, name, attempts

    def select(self, *args, **kwargs):
        return self._client.table(self._name).select(*args, **kwargs)

    def __getattr__(self, attr):
        _refuse(self._attempts, self._name, attr)


def _kind(value) -> str:
    return "缺少" if value is None else f"讀到 {type(value).__name__}"


def validate_proposal(data) -> None:
    if not isinstance(data, dict):
        raise ProposalError(f"最上層要是 mapping（sources: list，選用 source_defaults:），{_kind(data)}")
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ProposalError(f"`sources` 要是 list，{_kind(sources)}")
    for i, s in enumerate(sources):
        if not isinstance(s, dict):
            raise ProposalError(f"sources[{i}] 要是 mapping（name、type…），{_kind(s)}")
        for key in ("name", "type"):
            if not str(s.get(key) or "").strip():
                raise ProposalError(f"sources[{i}]（name={s.get('name')!r}）缺 `{key}`")
    if "source_defaults" in data and not isinstance(data["source_defaults"], dict):
        raise ProposalError(f"`source_defaults` 要是 mapping {{來源名稱片段: 類別}}，{_kind(data['source_defaults'])}")


def load_proposal(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise ProposalError(f"無法讀取或無法解析：{e}") from e
    validate_proposal(data)
    return data


def categories_copy(path: str, overrides: dict) -> str:
    """把提案的 source_defaults 合併進 categories 檔的暫存副本（同鍵提案優先，其他鍵照抄），回傳路徑。"""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    data["source_defaults"] = {**(data.get("source_defaults") or {}), **overrides}
    fd, tmp = tempfile.mkstemp(prefix="categories_eval_", suffix=".yml")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return tmp


def _timed(fetch, seconds: dict):
    def run(source):
        t0 = time.monotonic()
        try:
            return fetch(source)
        finally:
            name = source.get("name")
            seconds[name] = seconds.get(name, 0.0) + time.monotonic() - t0
    return run


@contextlib.contextmanager
def boundaries():
    """換上評估用的邊界：唯讀 client、embedding 計數、逐來源 fetch 計時；離開時還原。"""
    probe = SimpleNamespace(attempts=[], embedded=0, seconds={})
    get_client, attach, fetchers = storage._get_client, analyzer.attach_embeddings, dict(collector.FETCHERS)

    def read_only_client():
        return ReadOnlyClient(get_client(), probe.attempts)

    def counted_attach(candidates):
        probe.embedded += sum(1 for a in candidates if "embedding" not in a)
        return attach(candidates)

    storage._get_client, analyzer.attach_embeddings = read_only_client, counted_attach
    collector.FETCHERS.update({k: _timed(fn, probe.seconds) for k, fn in fetchers.items()})
    try:
        yield probe
    finally:
        storage._get_client, analyzer.attach_embeddings = get_client, attach
        collector.FETCHERS.update(fetchers)


def confluence_titles(kept: list, confluence: set) -> dict:
    out: dict = {}
    for a in kept:
        if a.get("major_category") in confluence:
            out.setdefault(a.get("source"), []).append((a["major_category"], a.get("title") or ""))
    return out


def report(funnel: dict, kept: list, confluence: set, probe) -> None:
    print("── 逐來源漏斗 ──")
    for source, counts in funnel.items():
        print(funnel_line(source, counts))
    titles = confluence_titles(kept, confluence)
    print("── 匯流四類標題（寫入上限之後，給人工判讀是不是正題）──")
    for source in funnel:
        if source in titles:
            print(f"{source}（{len(titles[source])} 篇）")
            for cat, title in titles[source]:
                print(f"  [{cat}] {title}")
    print(f"（另有 {sum(1 for s in funnel if s not in titles)} 個來源沒有任何一篇進匯流四類）")
    print("── embedding ──")
    print(f"本次呼叫 Gemini embedding：{probe.embedded} 篇")
    print("── 逐來源收集耗時（只計 fetch，不含 collect_sources 每個來源固定 sleep 的 1 秒）──")
    for source, sec in probe.seconds.items():
        print(f"{source}：{sec:.2f} 秒")
    print(f"合計 {sum(probe.seconds.values()):.2f} 秒")


def evaluate(sources: list) -> int:
    with boundaries() as probe:
        cat = TrafficCategory()
        kept = cat.filter(cat.collect(sources))
    if cat.last_funnel:
        report(cat.last_funnel, kept, confluence_categories(pipeline_config.load_pipeline_config()), probe)
    else:
        print("[評估] 無法評估：filter() 的分類設定載入失敗（見上方 warning），沒有逐來源漏斗", file=sys.stderr)
    if probe.attempts:
        tried = "、".join(f"{table}.{attr}" for table, attr in probe.attempts)
        print(f"[評估] 偵測到寫入嘗試，評估失敗：{tried}", file=sys.stderr)
    return 0 if cat.last_funnel and not probe.attempts else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("proposal", help="提案設定檔（YAML）")
    args = ap.parse_args()

    try:
        proposal = load_proposal(args.proposal)
    except ProposalError as e:
        print(f"[評估] 提案設定檔格式錯誤（{args.proposal}）：{e}", file=sys.stderr)
        return 2
    sources = [s for s in proposal["sources"] if s.get("enabled", True)]
    if not sources:
        print(f"[評估] 提案設定檔（{args.proposal}）裡沒有啟用的來源，沒有東西可評估", file=sys.stderr)
        return 2

    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO, ".env"))

    tmp = None
    if "source_defaults" in proposal:
        current = os.environ.get("CATEGORIES_TRAFFIC_YML_PATH", DEFAULT_CATEGORIES)
        tmp = categories_copy(current, proposal["source_defaults"])
        os.environ["CATEGORIES_TRAFFIC_YML_PATH"] = tmp
    try:
        return evaluate(sources)
    finally:
        if tmp:
            os.remove(tmp)


if __name__ == "__main__":
    sys.exit(main())
