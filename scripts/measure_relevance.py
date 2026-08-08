#!/usr/bin/env python3
"""Replay the spec-012 relevance gate over the historical published hot-topic slates.

The gate's unit tests prove it does what it says on hand-written inputs. They cannot
say whether the *token table* is any good — that needs real slates and a human's
verdict on each article. This script supplies the replay half: it reconstructs the
"before gate" slate that readers actually saw, computes the "after gate" slate the
same pipeline would have produced, and scores the SC ladder from spec.md §Success
Criteria against a human-labeled baseline.

What makes the replay exact rather than a guess: the published article list is NOT
chosen by the LLM. `analyze_hot_topic()` takes `sorted(bucket, by initial_quality_score
desc)[:10]` and the LLM only writes the prose, so the slate is a pure function of the
bucket. Re-deriving it needs no model call.

Two honesty limits, both reported in the output rather than hidden:

1. **Promotion is unknown for buckets larger than 10 articles.** Only the top 10 are
   recorded per report, so when the gate frees a slot we cannot say which article rose
   into it. Recovering the historical bucket was attempted and FALSIFIED: clustering the
   candidate pool at report time gave 107 articles for the 08-03「機車事故 · 中時」bucket
   against a recorded 28, and a cumulative_score of 187.5 against 24.69. The pool is not
   reconstructible because `articles` records only a `hot_topic_analyzed` boolean, never
   *when* a row was consumed, so every article eaten in an earlier week counts back in.
   Those buckets are therefore measured on their published slate alone and marked `~`.

2. **Cross-bucket effects are out of scope.** The gate shrinks buckets, so scores only
   fall; a bucket that dips under `min_threshold` is reported as dying (its on-topic
   articles are lost, which counts against SC-004), but the novelty gate and the ≤3 seat
   cap could hand that seat to a different bucket. Modelling that needs every category's
   buckets replayed per week against counterfactual prior reports — not attempted.

3. **Recorded scores are not frozen** (see SCORE_DRIFT), so a publish/不發布 verdict
   sitting within a few percent of `min_threshold` is printed as undecided rather than
   given a false crispness. `replay 保真度` in the output is the check that earns the
   right to read anything else: it recomputes each exact slate's `cumulative_score`
   from today's rows and counts how many still match what was published.

Read-only. Never writes to the database and never calls a model.

Usage:
    python scripts/measure_relevance.py --emit-labels tests/fixtures/relevance_baseline_012.jsonl
    #   → writes the label skeleton for T010 (human fills in `label`), then:
    python scripts/measure_relevance.py               # SC ladder table
    python scripts/measure_relevance.py --json        # same numbers, machine-readable
"""
import argparse
import json
import logging
import os
import sys

from dotenv import load_dotenv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Match measure_source_uptake.py: bare load_dotenv() searches from the caller's
# directory and misses the project .env when invoked from elsewhere.
load_dotenv(os.path.join(_REPO_ROOT, ".env"))
sys.path.insert(0, _REPO_ROOT)

logger = logging.getLogger("measure_relevance")

DEFAULT_BASELINE = os.path.join(_REPO_ROOT, "tests", "fixtures", "relevance_baseline_012.jsonl")
PAGE_SIZE = 1000
SLATE_CAP = 10  # analyzer.analyze_hot_topic() prompts with the top 10 by quality

# `initial_quality_score` is not frozen at publication: og enrichment rewrites an
# article's summary later, and the score's normalised_word_count term moves with it.
# Measured drift on the one slate where every row still resolves and both multipliers
# agree (2026-06-15「機車事故 · 新聞網」): recomputed 5.537 vs recorded 5.824 = 4.9%.
# A publish/不發布 verdict inside this band is therefore reported as borderline.
SCORE_DRIFT = 0.05


def fetch_articles():
    """Return {link: article} for every traffic article still in the table.

    Needed for two reasons: the older report rows store `source_article_links` as
    bare link strings with no title, and the replay needs `initial_quality_score`
    to re-derive the slate ordering.
    """
    from src.storage import _get_client

    client = _get_client()
    rows, page = [], 0
    while True:
        resp = (
            client.table("articles")
            .select("week_id,title,link,source,published,major_category,initial_quality_score")
            .eq("content_type", "traffic")
            .range(page * PAGE_SIZE, (page + 1) * PAGE_SIZE - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return {a["link"]: a for a in rows if a.get("link")}


def fetch_reports():
    """Return every published hot-topic report, newest week first."""
    from src.storage import _get_client

    client = _get_client()
    resp = (
        client.table("hot_topic_reports")
        .select("week_start_date,topic_label,source_article_count,source_article_links,"
                "cumulative_score,distinct_sources,distinct_days")
        .order("week_start_date", desc=True)
        .execute()
    )
    return resp.data or []


def _links_of(report):
    """Normalise both `source_article_links` shapes to a list of link strings.

    Reports written before the ordered-links change store plain strings; later ones
    store {link,title,summary} dicts.
    """
    out = []
    for item in report.get("source_article_links") or []:
        link = item.get("link") if isinstance(item, dict) else item
        if link:
            out.append(link)
    return out


def _category_of(report):
    """The major_category half of a `<category> · <token>` topic label."""
    return report["topic_label"].split(" · ", 1)[0]


def gated_slates(reports, articles_by_link, rules):
    """Return one replay-ready record per published slate the gate can touch.

    A category with no rule is not gated at all (fail-open), so its reports are
    skipped — including the `· 彙整` digests, which never pass through the gate.
    """
    out = []
    for rep in reports:
        cat = _category_of(rep)
        if cat not in rules:
            continue
        links = _links_of(rep)
        resolved = [articles_by_link[l] for l in links if l in articles_by_link]
        out.append({
            "week": rep["week_start_date"],
            "label": rep["topic_label"],
            "category": cat,
            "bucket_size": rep["source_article_count"],
            "recorded_score": rep["cumulative_score"],
            "published": resolved,
            "unresolved": len(links) - len(resolved),
            # Exact means the whole bucket is in front of us: the slate was not
            # capped (count > slate ⇒ unseen articles would have been promoted into
            # the freed slots) AND every published row is still in `articles` (a
            # pruned row leaves a hole we would silently score as a smaller bucket).
            "exact": rep["source_article_count"] <= len(links) and len(resolved) == len(links),
        })
    return out


def replay(slates, rules, config):
    """Apply the gate to each slate and re-derive what would have been published.

    `min_threshold` is re-checked because the gate only removes articles: a bucket
    that was barely over the line can fall under it and publish nothing at all,
    which loses its on-topic articles too. That is a real cost of the gate, not a
    rounding error, so it is measured rather than assumed away.

    The threshold check is only meaningful when the slate IS the bucket. For a
    28-article bucket that published 10, scoring the gated 10 understates the real
    bucket score several-fold and would invent a "不發布" verdict out of missing
    data — so those slates carry `survives=None` and are left unjudged.

    `before_score` re-derives the recorded `cumulative_score` from the same rows.
    Matching it is the replay's own fidelity test: it proves this script rebuilds
    what the pipeline actually did before any conclusion is drawn from the delta.
    """
    from src.analyzer import score_topic_buckets
    from src.filter import partition_by_relevance

    scoring = config.get("topic_scoring", {})
    per_cat = scoring.get("category_min_threshold") or {}

    for s in slates:
        on_topic, off_topic = partition_by_relevance(s["published"], rules)
        threshold = float(per_cat.get(s["category"], scoring.get("min_threshold", 1.5)))
        s["gate_kept"] = on_topic
        s["gate_dropped"] = off_topic
        s["threshold"] = threshold
        s["before_score"] = (
            score_topic_buckets({"b": s["published"]}, config)["b"] if s["published"] else 0.0
        )
        if s["exact"]:
            score = score_topic_buckets({"b": on_topic}, config)["b"] if on_topic else 0.0
            s["after_score"] = score
            s["survives"] = bool(on_topic) and score >= threshold
            # A verdict this close to the line is inside the replay's own error bar
            # (see SCORE_DRIFT) and must not be reported as decided.
            s["borderline"] = bool(on_topic) and abs(score - threshold) / threshold <= SCORE_DRIFT
        else:
            s["after_score"] = None
            s["survives"] = None      # bucket > slate: not judgeable, not "dead"
            s["borderline"] = False
        s["after"] = list(on_topic) if s["survives"] is not False else []
        s["after"] = sorted(
            s["after"],
            key=lambda a: float(a.get("initial_quality_score") or 0),
            reverse=True,
        )[:SLATE_CAP]
    return slates


def label_rows(slates):
    """Every article a human must judge, in data-model.md §4's shape.

    The union of the before- and after-slates, which here is just the before-slates:
    the gate only removes, and promotion into freed slots is unknowable (see the
    module docstring). Ordered newest week first so the 08-03 anchors label first.
    """
    seen, rows = set(), []
    for s in slates:
        for a in s["published"]:
            key = (a.get("week_id"), a.get("title"), a.get("source"))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "week_id": a.get("week_id") or "",
                "major_category": a.get("major_category") or "",
                "title": a.get("title") or "",
                "source": a.get("source") or "",
                "label": "",
                "note": "",
            })
    return rows


def load_baseline(path):
    """Return {title: label}, conflicting titles, and how many rows are still untouched.

    Keyed on title because §4 deliberately keeps no link (de-identification) and
    the title is what the gate reads anyway.

    `unclear` is carried through as a real verdict — "the title does not say" — not
    dropped like a blank. Blank means nobody has looked yet; the two must not be
    reported as the same thing (data-model §4).
    """
    labels, conflicts, untouched = {}, set(), 0
    if not os.path.exists(path):
        return labels, conflicts, untouched
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            title, label = row.get("title", ""), (row.get("label") or "").strip()
            if not title:
                continue
            if label not in ("on", "off", "unclear"):
                untouched += 1
                continue
            if title in labels and labels[title] != label:
                conflicts.add(title)
            labels[title] = label
    return labels, conflicts, untouched


def measure(slates, labels):
    """Score the SC ladder. Returns (per-slate rows, summary dict).

    Off-topic ratios are computed only over articles labeled `on`/`off`. An
    unlabeled slate would otherwise read as clean, which is the exact failure the
    baseline exists to prevent (spec 011's lesson).

    `unclear` rows — the title genuinely does not say whether an accident happened —
    are excluded from both numerator and denominator, and counted out loud instead.
    ⚠️ That exclusion flatters the gate: unclear rows are the hardest cases, exactly
    where a token table is most likely to be wrong. The count is printed with every
    ratio so the coverage limit travels with the number (data-model §4).
    """
    rows, unclear_total = [], 0
    before_on = after_on = 0
    strict_ratios, all_ratios = [], []
    fidelity_ok = fidelity_checked = 0
    for s in slates:
        def split(arts):
            on = sum(1 for a in arts if labels.get(a.get("title")) == "on")
            off = sum(1 for a in arts if labels.get(a.get("title")) == "off")
            return on, off, len(arts) - on - off

        b_on, b_off, b_un = split(s["published"])
        a_on, a_off, _ = split(s["after"])
        unclear_total += b_un
        b_total, a_total = b_on + b_off, a_on + a_off
        # Only exact slates can be summed into a regression figure: a `~` slate's
        # after-list is missing the articles that would have been promoted into it.
        if s["exact"]:
            before_on += b_on
            after_on += a_on
            fidelity_checked += 1
            if abs(s["before_score"] - s["recorded_score"]) < 1e-3:
                fidelity_ok += 1
        row = {
            "week": s["week"],
            "label": s["label"],
            "exact": s["exact"],
            "bucket_size": s["bucket_size"],
            "before_n": len(s["published"]),
            "dropped": len(s["gate_dropped"]),
            "kept": len(s["gate_kept"]),
            "before_off": b_off,
            "before_ratio": (b_off / b_total) if b_total else None,
            "after_n": len(s["after"]),
            "after_off": a_off,
            "after_ratio": (a_off / a_total) if a_total else None,
            "survives": s["survives"],
            "borderline": s["borderline"],
            "after_score": s["after_score"],
            "threshold": s["threshold"],
            "unclear": b_un,
            "on_lost": (b_on - a_on) if s["exact"] else None,
        }
        rows.append(row)
        if s["survives"] is not False and a_total:
            all_ratios.append(row["after_ratio"])
            if s["exact"]:
                strict_ratios.append(row["after_ratio"])

    def rung_of(worst):
        if worst is None:
            return "n/a（無存活且已標記的名單可量）"
        if worst == 0:
            return "SC-003（L2 理想）"
        if worst <= 0.20:
            return "SC-002（L1）"
        if worst <= 0.50:
            return "SC-001（L0 Gate）"
        return "未達 SC-001 Gate"

    strict_worst = max(strict_ratios) if strict_ratios else None
    all_worst = max(all_ratios) if all_ratios else None
    return rows, {
        "rung": rung_of(strict_worst),
        "rung_including_estimated": rung_of(all_worst),
        "worst_after_ratio": strict_worst,
        "worst_after_ratio_including_estimated": all_worst,
        "before_on_total": before_on,
        "after_on_total": after_on,
        "sc004_pass": (after_on >= before_on) if labels else None,
        "unclear": unclear_total,
        "slates": len(rows),
        "exact_slates": sum(1 for r in rows if r["exact"]),
        "replay_fidelity": f"{fidelity_ok}/{fidelity_checked}",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", default=DEFAULT_BASELINE,
                    help=f"labeled baseline JSONL (default {os.path.relpath(DEFAULT_BASELINE, _REPO_ROOT)})")
    ap.add_argument("--emit-labels", metavar="PATH",
                    help="write the unlabelled skeleton for T010 and exit; refuses to overwrite")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING)

    from src.pipeline_config import load_pipeline_config, load_relevance_rules

    rules = load_relevance_rules()
    if not rules:
        print("no relevance_rules configured — nothing is gated, nothing to measure")
        return
    config = load_pipeline_config()

    slates = gated_slates(fetch_reports(), fetch_articles(), rules)
    if not slates:
        print(f"no published slates in gated categories {sorted(rules)}")
        return
    replay(slates, rules, config)

    if args.emit_labels:
        rows = label_rows(slates)
        if os.path.exists(args.emit_labels):
            print(f"refusing to overwrite {args.emit_labels} — labels are hand-made; "
                  f"move it aside first")
            return
        os.makedirs(os.path.dirname(os.path.abspath(args.emit_labels)), exist_ok=True)
        with open(args.emit_labels, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {len(rows)} unlabeled rows → {args.emit_labels}")
        print('fill each row\'s "label" with "on" or "off" by hand '
              '(the gate\'s own output must never backfill it), then re-run without --emit-labels')
        return

    labels, conflicts, untouched = load_baseline(args.baseline)
    rows, summary = measure(slates, labels)

    if args.json:
        print(json.dumps({"summary": summary, "slates": rows}, ensure_ascii=False, indent=2))
        return

    if not labels:
        print(f"baseline not found or empty: {args.baseline}")
        print("run with --emit-labels <path> to generate the skeleton (T010), then label it by hand.\n")

    print(f"gated categories: {sorted(rules)}")
    print(f"slates: {summary['slates']}（精確 {summary['exact_slates']}，"
          f"`~`＝桶>名單（補位者不可知）或有列已被清除：{summary['slates'] - summary['exact_slates']}）")
    print(f"replay 保真度：{summary['replay_fidelity']} 個精確名單重算出報告紀錄的 cumulative_score\n")
    header = (f"{'week':<11}{'':<2}{'桶':>4}{'名單':>5}{'閘丟':>5}{'留':>4}"
              f"{'離題前':>8}{'離題後':>8}  閘後判定")
    print(header)
    print("-" * 82)
    for r in rows:
        mark = " " if r["exact"] else "~"
        b = f"{r['before_off']}/{r['before_ratio']:.0%}" if r["before_ratio"] is not None else "--"
        a = f"{r['after_off']}/{r['after_ratio']:.0%}" if r["after_ratio"] is not None else "--"
        if r["survives"] is None:
            verdict = "名單不完整，分數不可算"
        elif r["survives"]:
            verdict = f"發布（{r['after_score']:.2f} ≥ {r['threshold']:.1f}）"
        else:
            verdict = f"不發布（{r['after_score']:.2f} < {r['threshold']:.1f}）"
        if r["borderline"]:
            verdict += f" ※在 ±{SCORE_DRIFT:.0%} 誤差帶內，未定"
        if r["on_lost"]:
            verdict += f"  ⚠on-topic 流失 {r['on_lost']}"
        print(f"{r['week']:<11}{mark:<2}{r['bucket_size']:>4}{r['before_n']:>5}"
              f"{-r['dropped']:>5}{r['kept']:>4}{b:>8}{a:>8}  {r['label']}｜{verdict}")

    print("\n（離題前/後＝離題篇數／占已標記篇數的比例；未標記者不計入比例）")
    worst = summary["worst_after_ratio"]
    print(f"最差存活名單離題比例（僅精確名單）："
          f"{worst:.0%}" if worst is not None else "最差存活名單離題比例（僅精確名單）：n/a")
    print(f"達到階數：{summary['rung']}")
    if summary["rung_including_estimated"] != summary["rung"]:
        print(f"（含 `~` 估計名單則為：{summary['rung_including_estimated']}）")
    if summary["sc004_pass"] is None:
        print("SC-004（on-topic 不回歸）：n/a — 無標記無法判定")
    else:
        print(f"SC-004（on-topic 不回歸）：{'PASS' if summary['sc004_pass'] else 'FAIL'} "
              f"— 精確名單的 on-topic 篇數 {summary['before_on_total']} → {summary['after_on_total']}")
    if untouched:
        print(f"⚠ 基準集還有 {untouched} 列沒人看過（label 空白）——比例只算已判定者，"
              f"證據等級 E3 直到 T010 走完每一列")
    elif summary["unclear"]:
        # Completeness is all this can check; whether the labels are a human's is a
        # property of how the file was made, not something the script can attest to.
        print(f"名單裡有 {summary['unclear']} 篇為 unclear（標題判不出來），"
              f"已排除於分母之外——⚠️ 那是最難的案例，排除會讓分數偏好看。")
        print("其餘皆已判定；若 label 為人工所標，上面的比例即 E1 實測（涵蓋範圍＝可判定者）")
    else:
        print("全部名單皆已判定為 on/off——若 label 為人工所標，上面的比例即 E1 實測")
    if conflicts:
        print(f"⚠ {len(conflicts)} 個標題在基準集裡有衝突的 label：{sorted(conflicts)[:3]}")
    unresolved = sum(s["unresolved"] for s in slates)
    if unresolved:
        print(f"⚠ {unresolved} 個發布連結已不在 articles 表中，未納入")


if __name__ == "__main__":
    main()
