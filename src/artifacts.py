"""artifacts.py：產物與 FFXIV 候選池共用的寫檔，以及讀回產物裡的 articles（spec 020 FR-008）。
write_json 的路徑從環境變數讀；沒設、寫不進去都各印一行，不丟例外。"""
import json
import os


def read_articles(path: str) -> list:
    """讀回產物檔的 articles。找不到檔丟 FileNotFoundError；讀不了、不是 JSON、articles 不是物件的清單丟 OSError 或 ValueError，
    由呼叫端印一行原因。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    articles = data.get("articles") if isinstance(data, dict) else None
    if not isinstance(articles, list) or not all(isinstance(a, dict) for a in articles):
        raise ValueError("articles 不是物件的清單")
    return articles


def write_json(logger, label: str, env_var: str, build, filename: str | None = None) -> None:
    """env_var 沒設只印一行、不呼叫 build；有 filename 時 env_var 是目錄（不存在就建），沒有時是檔案路徑（不建上層）。
    build() 回傳 (資料, 成功那一行括號裡的摘要)；訊息掛在呼叫端的 logger 下。"""
    target = os.environ.get(env_var, "").strip()
    if not target:
        logger.info("%s：未設 %s，不寫檔", label, env_var)
        return
    data, summary = build()
    text = json.dumps(data, ensure_ascii=False, indent=1, default=str)
    path = target if filename is None else os.path.join(target, filename)
    try:
        if filename is not None:
            os.makedirs(target, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        logger.warning("%s：寫入 %s 失敗（%s）", label, path, e)
        return
    logger.info("%s：寫入 %s（%s）", label, path, summary)
