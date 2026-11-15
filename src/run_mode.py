"""run_mode.py：執行模式（spec 020），正式或不發布的第一級／第二級。
只有這裡讀 GARYU_RUN_MODE，其他模組問這裡。
"""

import os

ENV_VAR = "GARYU_RUN_MODE"

FORMAL = "formal"
DRY_INPUT = "dry-input"
DRY_FULL = "dry-full"

_START_LINES = {
    DRY_INPUT: "[不發布] 第一級：只到入選，不呼叫生成式 LLM",
    DRY_FULL: "[不發布] 第二級：呼叫 LLM，不寫入、不發布",
}


def current() -> str:
    """回傳 FORMAL、DRY_INPUT 或 DRY_FULL。沒設或空字串是正式；不認得的值直接丟錯，不退回正式。"""
    raw = os.environ.get(ENV_VAR)
    value = (raw or "").strip()
    if not value:
        return FORMAL
    if value in _START_LINES:
        return value
    raise ValueError(
        f"{ENV_VAR} 的值不認得：{raw!r}；認得的值：{DRY_INPUT}、{DRY_FULL}（沒設或空字串是正式模式）"
    )


def is_dry_run() -> bool:
    return current() != FORMAL


def start_line() -> str:
    """每支程式開頭那一行；正式模式回空字串。"""
    return _START_LINES.get(current(), "")


def skip_write_line(func_name: str, count: int | None = None) -> str:
    """被略過的寫入那一行；count 是 None 表示沒有查資料庫、筆數未知。正式模式回空字串。"""
    if not is_dry_run():
        return ""
    if count is None:
        return f"[不發布] 略過 {func_name}：沒有查資料庫，筆數未知"
    return f"[不發布] 略過 {func_name}：{count} 筆"
