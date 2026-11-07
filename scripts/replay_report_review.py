#!/usr/bin/env python3
"""重播一份已發布的週報（spec 018）：唯讀重建生成輸入，--regenerate 用新指令重生成，兩份都跑 check_report()。
結果只寫到 --out 的 JSON 與 .md，資料庫只讀、不發布；--regenerate 照 prod key 計費。
介面：specs/018-prepublish-review/contracts/replay-cli.md。"""
import argparse
import json
import os
import sys
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from src.report_review import SC001_CHECKS, check_report, is_title_only  # noqa: E402

BATCH = 10  # 長的 Google News 連結讓 in.(...) 過長，同 replay_digest_pool.py
REVIEWS_TABLE = "hot_topic_report_reviews"
# 缺表的錯誤碼：PostgREST 在 schema cache 找不到表（PGRST205）、Postgres 的 undefined_table（42P01）
MISSING_TABLE_CODES = ("PGRST205", "42P01")
DIGEST_MARK = "彙整"
ARTICLE_COLUMNS = "link,title,summary,published,initial_quality_score"
SUMMARY_CHARS = {"digest": 400, "hot": 600}  # analyzer 給模型的摘要長度，sources 照這個截
# 一份報告一次生成呼叫的實測費用（US$；現價、漲價後）
# 出處 experiments/model-quality-3p8flash-vs-argon/README.md「成本與延遲」，量的是三軸熱點
COST_PER_REPORT = {"gemini-3.8-flash": (0.0123, 0.0246), "gemini-4-argon": (0.0104, 0.0207)}
TOKENS_NOTE = "_call_gemini 只回傳文字、丟掉回應的 usageMetadata，T015 補上之前拿不到（spec Clarifications 2026-11-08）"


class ReplayError(Exception):
    pass


def template_of(topic: str) -> str:
    return "digest" if DIGEST_MARK in topic else "hot"


def _rows(what: str, query) -> list:
    try:
        return query.execute().data or []
    except Exception as e:
        raise ReplayError(f"讀 {what} 失敗：{e}") from e


def fetch_report(client, week: str, topic: str) -> dict:
    rows = _rows("hot_topic_reports", client.table("hot_topic_reports")
                 .select("id,week_start_date,topic_label,report_text,source_article_links")
                 .eq("week_start_date", week).eq("topic_label", topic))
    if not rows:
        raise ReplayError(f"找不到 {week}「{topic}」的已發布報告（hot_topic_reports 沒有這一列）")
    return rows[0]


def find_snapshot(client, week: str, topic: str):
    """回審核紀錄的 input_snapshot；沒有紀錄或缺表回 None 並印原因。
    其他查詢錯誤一律結束：改用重建會把可能存在的快照蓋掉。"""
    try:
        rows = (client.table(REVIEWS_TABLE).select("input_snapshot")
                .eq("week_start_date", week).eq("topic_label", topic).execute()).data or []
    except Exception as e:
        code = getattr(e, "code", None)
        if code not in MISSING_TABLE_CODES:
            raise ReplayError(f"查 {REVIEWS_TABLE} 失敗，不改用重建的輸入（以免蓋掉真的快照）：{e}") from e
        print(f"審核紀錄：{REVIEWS_TABLE} 表不存在（{code}；T032 之前 prod 沒有這張表），用 source_article_links 重建輸入")
        return None
    if not rows:
        print("審核紀錄：沒有這份報告的審核紀錄（018 上線前發布的都沒有），用 source_article_links 重建輸入")
        return None
    return rows[0]["input_snapshot"]


def source_links(report: dict) -> list:
    return [x["link"] if isinstance(x, dict) else x for x in report.get("source_article_links") or []]


def fetch_articles(client, links: list) -> list:
    found = {}
    for i in range(0, len(links), BATCH):
        rows = _rows("articles", client.table("articles").select(ARTICLE_COLUMNS).in_("link", links[i:i + BATCH]))
        found.update((r["link"], r) for r in rows)
    missing = [link for link in links if link not in found]
    if missing:
        raise ReplayError(f"重建失敗：{len(missing)} 篇在 articles 查不到（不拿殘缺的清單重播）：" + "、".join(missing))
    return [found[link] for link in links]


def old_input(template: str, articles: list) -> str:
    """018 之前 analyzer 組的清單（e611bd7 之前）：照 source_article_links 順序，
    彙整每篇都列（含只有標題的）、標「日期」、摘要截 400 字；三軸只有標題與摘要（截 600 字）。"""
    lines = []
    for i, a in enumerate(articles, 1):
        title = a.get("title", "（無標題）")
        body = (a.get("summary", "") or "")[:SUMMARY_CHARS[template]]
        head = f"[{i}] 日期：{(a.get('published') or '')[:10]}\n    " if template == "digest" else f"[{i}] "
        lines.append(f"{head}標題：{title}\n    摘要：{body}")
    return "\n\n".join(lines)


def as_sources(template: str, articles: list) -> list:
    return [{"link": a.get("link"), "title": a.get("title"), "published": (a.get("published") or "")[:10],
             "summary": (a.get("summary") or "")[:SUMMARY_CHARS[template]]} for a in articles]


def title_only_ids(articles: list) -> list:
    return [i for i, a in enumerate(articles, 1) if is_title_only(a.get("title") or "", a.get("summary") or "")]


def run_checks(text: str, template: str, articles: list) -> dict:
    hits = check_report(text, template=template, sources=as_sources(template, articles),
                        title_only_ids=title_only_ids(articles))
    counts = {name: len(found) for name, found in hits.items()}
    return {"sc001": {k: counts[k] for k in SC001_CHECKS if k in counts}, "counts": counts, "hits": hits}


def load_inputs(week: str, topic: str) -> dict:
    from src.storage import _get_client

    try:
        client = _get_client()
    except RuntimeError as e:
        raise ReplayError(str(e)) from e
    report = fetch_report(client, week, topic)
    snapshot = find_snapshot(client, week, topic)
    links = source_links(report)
    if not links:
        raise ReplayError(f"{week}「{topic}」的 source_article_links 是空的，沒有輸入可重建")
    template = template_of(report["topic_label"])
    articles = fetch_articles(client, links)
    return {"report": report, "template": template, "articles": articles,
            "input": "reconstructed" if snapshot is None else "snapshot",
            "input_text": old_input(template, articles) if snapshot is None else snapshot}


def regenerate(template: str, articles: list, topic: str, week: str) -> tuple:
    """走真的 analyze_*（它們呼叫 build_*_input）；彙整的 max_articles 設成篇數，同一批文章一篇都不丟。"""
    from src import analyzer

    started = time.monotonic()
    try:
        if template == "digest":
            text, links = analyzer.analyze_category_digest(articles, topic, week, max_articles=len(articles))
            input_text = analyzer.build_digest_input(articles, len(articles))[0]
        else:
            text, links = analyzer.analyze_hot_topic(articles, topic, week)
            input_text = analyzer.build_hot_topic_input(articles)[0]
    except Exception as e:
        raise ReplayError(f"重生成失敗：{e}") from e
    seconds = round(time.monotonic() - started, 1)
    if not text:
        raise ReplayError("重生成失敗：analyze 回空（呼叫失敗，或彙整全部只有標題；原因見上面的 log）")
    by_link = {a["link"]: a for a in articles}
    ordered = [by_link[item["link"]] for item in links]
    return {"model": analyzer.GEMINI_MODEL, "text": text, "input_text": input_text,
            "sources": as_sources(template, ordered), "title_only_ids": title_only_ids(ordered)}, ordered, seconds


def cost_line(regenerate_flag: bool, model: str) -> str:
    if not regenerate_flag:
        return "估算費用：US$0（沒有 --regenerate，不呼叫 Gemini，只讀資料庫）"
    if model not in COST_PER_REPORT:
        return f"估算費用：未知（{model} 沒有實測單價；會呼叫一次生成，照 prod key 計費）"
    now, later = COST_PER_REPORT[model]
    return (f"估算費用：一次 {model} 生成呼叫，約 US${now}（現價）～US${later}（漲價後）；"
            "這是三軸熱點的實測，彙整的輸入較多會再高一些")


def token_line(called: bool) -> str:
    return f"token 數：未取得（{TOKENS_NOTE}）" if called else "token 數：0（沒有呼叫 Gemini）"


def _cell(hits: list) -> str:
    return f"{len(hits)}" + (f"：{'、'.join(hits)}" if hits else "")


def render_md(r: dict) -> str:
    original, regen = r["checks"]["original"]["hits"], r["checks"]["regenerated"]
    lines = [f"# 重播：{r['week']}「{r['topic']}」", "",
             f"- 報告 id：{r['report_id']}；模板：{r['template']}；輸入：{r['input']}",
             f"- 重生成模型：{r['regenerated']['model']}" if r["regenerated"] else "- 沒有重生成（沒帶 --regenerate）",
             "", "| 檢查 | 原稿 | 重生成 |", "|---|---|---|"]
    for name, hits in original.items():
        lines.append(f"| {name} | {_cell(hits)} | {_cell(regen['hits'][name]) if regen else '—'} |")
    lines += ["", "## 原稿", "", r["original"]["text"]]
    if r["regenerated"]:
        lines += ["", "## 重生成", "", r["regenerated"]["text"]]
    return "\n".join(lines) + "\n"


def write_outputs(out_dir: str, stem: str, result: dict) -> tuple:
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, stem)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(render_md(result))
    return base + ".json", base + ".md"


def replay(args, state: dict) -> tuple:
    inputs = load_inputs(args.week, args.topic)
    template, articles, report = inputs["template"], inputs["articles"], inputs["report"]
    regen, ordered, seconds = None, None, 0.0
    if args.regenerate:
        state["called"] = True
        regen, ordered, seconds = regenerate(template, articles, args.topic, args.week)
    result = {
        "week": args.week, "topic": args.topic, "report_id": report["id"], "template": template,
        "input": inputs["input"],
        "original": {"text": report["report_text"], "input_text": inputs["input_text"],
                     "sources": as_sources(template, articles), "title_only_ids": title_only_ids(articles)},
        "regenerated": regen,
        "checks": {"original": run_checks(report["report_text"], template, articles),
                   "regenerated": run_checks(regen["text"], template, ordered) if regen else None},
        "usage": {"tokens": None if regen else 0, "tokens_note": TOKENS_NOTE if regen else "沒有呼叫 Gemini",
                  "seconds": seconds},
    }
    return write_outputs(args.out, f"{args.week}-{report['id']}", result)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--week", required=True, help="週次（week_start_date），例 2026-11-02")
    parser.add_argument("--topic", required=True, help="topic_label 全名，例「道安政策 · 彙整」")
    parser.add_argument("--out", required=True, help="輸出目錄：<週次>-<報告 id>.json 與同名 .md")
    parser.add_argument("--regenerate", action="store_true", help="用新的生成指令從同一批文章重生成（呼叫 Gemini、計費）")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv
    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    from src import analyzer

    print(cost_line(args.regenerate, analyzer.GEMINI_MODEL))
    state = {"called": False}
    try:
        json_path, md_path = replay(args, state)
        print(f"輸出：{json_path}、{md_path}")
        code = 0
    except ReplayError as e:
        print(f"[重播] {e}", file=sys.stderr)
        code = 1
    print(token_line(state["called"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
