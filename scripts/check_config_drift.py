#!/usr/bin/env python3
"""比對執行期設定與 repo 裡的 `.example.yml`，值不同就失敗。

**為什麼需要這支**：`config/*.yml` 的真身是 GitHub production environment variable，
repo 裡的 `*.example.yml` 是那些值**唯一會進 git 的副本**。兩邊漂掉的時候不會有任何
錯誤——管線照跑，只是 repo 裡記的決策從某一刻起是假的。2026-08-31 曾人工比對過一次，
那是一次性動作，沒有執行者；本檔就是那個執行者。

**判準是「解析後的值相同」，不是「逐字相同」。** 理由是量出來的（2026-09-05）：
prod 的 `PIPELINE_CONFIG_YML` 有 104/105 行是 CRLF 而 example 是 LF，且 example
刻意比 prod 多 14 行註解。逐字比對會天天誤報，而天天誤報的檢查最後一定會被關掉。

**`sources_traffic` / `sources_ffxiv` 在 2026-10-13 之前刻意不在清單裡**：當時它們的
example 是格式範本、與 prod 不同步（2026-09-05 實測 traffic 33 對 24、ffxiv 9 對 4）。
spec 014（`crb`）先把兩份同步成鏡像、本機比對相符，才加進清單——是前提換了，不是順手補完。

用法（無參數，從 repo 根目錄跑）：

    .venv/bin/python scripts/check_config_drift.py
"""
import io
import os
import sys

import yaml

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 只放**檔頭自稱是 prod 鏡像**的 example。categories／pipeline 兩份寫「Stored as GitHub
# Environment Variable … Copy to config/X.yml」，sources 兩份寫「這是 prod … 來源設定的
# 鏡像」（2026-10-13 起，`crb`）。改清單前先看那份 example 的檔頭。
MIRRORED = [
    ("config/categories_traffic.yml", "config/categories_traffic.example.yml"),
    ("config/pipeline_config.yml", "config/pipeline_config.example.yml"),
    ("config/sources_traffic.yml", "config/sources_traffic.example.yml"),
    ("config/sources_ffxiv.yml", "config/sources_ffxiv.example.yml"),
]


def _flatten(obj, prefix=""):
    """把巢狀結構攤平成 (路徑, 純量) — 讓報告能指出**哪一個鍵**漂了，而不只是說「不同」。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _flatten(v, f"{prefix}[{i}]")
    else:
        yield (prefix or "<root>"), obj


def compare(runtime_path: str, example_path: str) -> list[str]:
    """回傳不一致的描述清單。空 list ＝ 沒有漂移。

    讀不到任何一邊就回報為不一致——**讀不到不等於沒問題**，不可以靜靜跳過。
    """
    problems = []
    for p in (runtime_path, example_path):
        if not os.path.exists(p):
            problems.append(f"讀不到 {p}（無法比對，視為失敗）")
    if problems:
        return problems

    loaded = {}
    for label, p in (("runtime", runtime_path), ("example", example_path)):
        try:
            loaded[label] = yaml.safe_load(io.open(p, encoding="utf-8").read())
        except yaml.YAMLError as exc:
            problems.append(f"{p} 不是合法 YAML：{exc}")
    if problems:
        return problems

    a = dict(_flatten(loaded["runtime"]))
    b = dict(_flatten(loaded["example"]))
    for key in sorted(set(a) | set(b)):
        if key not in b:
            problems.append(f"只在執行期設定裡：{key} = {a[key]!r}")
        elif key not in a:
            problems.append(f"只在 example 裡：{key} = {b[key]!r}")
        elif a[key] != b[key]:
            problems.append(f"值不同：{key}\n      執行期 = {a[key]!r}\n      example = {b[key]!r}")
    return problems


def main() -> int:
    drifted = False
    for runtime_path, example_path in MIRRORED:
        rp = os.path.join(_REPO, runtime_path)
        ep = os.path.join(_REPO, example_path)
        problems = compare(rp, ep)
        if problems:
            drifted = True
            print(f"::error::設定漂移：{runtime_path} 與 {example_path} 的值不一致")
            print(f"[漂移] {runtime_path} ↔ {example_path}")
            for p in problems:
                print(f"    - {p}")
        else:
            print(f"[相符] {runtime_path} ↔ {example_path}")
            # 行尾只是提示，不是失敗：判準是值，不是位元組。prod 的
            # PIPELINE_CONFIG_YML 目前就是 CRLF（2026-09-05 實測），而它無害。
            if os.path.exists(rp) and io.open(rp, "rb").read().count(b"\r\n"):
                print(f"         （提示：{runtime_path} 是 CRLF 行尾，不影響本檢查）")

    if drifted:
        print("\n設定漂移代表 repo 裡記的決策已經不是 prod 在跑的東西。")
        print("同步方式見 CLAUDE.local.md：改本機檔 → gh variable set <NAME> --env production < <檔案>")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
