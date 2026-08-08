#!/usr/bin/env python3
"""Interactive labeller for the spec-012 relevance baseline (task T010).

One article per screen, `o`/`f` to label, optional note after the key. Writes back
after every answer, so Ctrl-C loses nothing and re-running resumes where you stopped.

It deliberately shows only the title — the same input the gate itself gets, and
nothing about what the gate decided. Seeing the gate's verdict while labelling would
anchor the labels to the system's own output, which is the circularity data-model.md
§4 forbids: the baseline is the only ground truth the SC ladder has.

No database, no network, no model. Pure file editing.

Usage:
    .venv/bin/python scripts/label_baseline.py            # label the unlabelled rows
    .venv/bin/python scripts/label_baseline.py --relabel   # walk every row, current label shown
"""
import argparse
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(_REPO_ROOT, "tests", "fixtures", "relevance_baseline_012.jsonl")

CRITERION = (
    "判準：這篇的主體，是不是一件機車事故（含傷亡、肇因、後續司法），\n"
    "      或一批機車事故的統計／風險？  是 → on，否 → off"
)
KEYS = {"o": "on", "on": "on", "f": "off", "off": "off"}


def load(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def save(path, rows):
    """Write via a temp file so an interrupt mid-write cannot truncate the baseline."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def commit_one(path, idx, expected_title, label, note):
    """Persist ONE row by re-reading the file first, then writing it back.

    Writing the startup snapshot after every answer is what an earlier version did,
    and it silently clobbered rows that had been edited elsewhere while the session
    was open (a lost-update race — it ate four labels on 2026-08-08). Re-reading
    means a concurrent edit to any other row survives. The title check guards the
    case where the file was re-ordered or regenerated underneath us.
    """
    disk = load(path)
    if idx >= len(disk) or disk[idx].get("title") != expected_title:
        raise SystemExit(f"檔案在標記期間被換成不同的內容（第 {idx + 1} 列對不上），"
                         f"未寫入任何東西。請重跑本工具。")
    disk[idx]["label"] = label
    if note:
        disk[idx]["note"] = note
    save(path, disk)


def wrap(text, width=64, indent=" " * 8):
    """Break a CJK title on width columns; str.wrap splits on spaces, which CJK lacks."""
    lines = [text[i:i + width] for i in range(0, len(text), width)] or [""]
    return ("\n" + indent).join(lines)


def counts(rows):
    on = sum(1 for r in rows if r.get("label") == "on")
    off = sum(1 for r in rows if r.get("label") == "off")
    return on, off, len(rows) - on - off


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=DEFAULT_PATH, help="baseline JSONL to edit")
    ap.add_argument("--relabel", action="store_true",
                    help="walk every row including already-labelled ones")
    args = ap.parse_args()

    rows = load(args.path)
    todo = [i for i, r in enumerate(rows)
            if args.relabel or (r.get("label") or "").strip() not in ("on", "off")]
    if not todo:
        on, off, un = counts(rows)
        print(f"全部 {len(rows)} 列都已標記（on={on} off={off}）。"
              f"跑 measure_relevance.py 看 SC 階梯，或用 --relabel 重走一遍。")
        return

    print(CRITERION)
    print("\n輸入：o＝on／f＝off／s＝跳過／q＝存檔離開。"
          "理由接在後面即可，例如「f 刑案，無碰撞」。\n")

    for n, idx in enumerate(todo, 1):
        row = rows[idx]
        current = f"（現為 {row['label']}）" if row.get("label") else ""
        print(f"[{n}/{len(todo)}] 第 {idx + 1} 列 · {row.get('week_id', '')} {current}")
        print(f"        {wrap(row.get('title', ''))}")
        while True:
            try:
                raw = input("  on/off? ").strip()
            except (EOFError, KeyboardInterrupt):
                on, off, un = counts(load(args.path))
                print(f"\n離開（每答一列都已即時寫入）。on={on} off={off} 未標={un}")
                return
            if not raw:
                continue
            key, _, note = raw.partition(" ")
            key = key.lower()
            if key in ("q", "quit"):
                on, off, un = counts(load(args.path))
                print(f"離開（每答一列都已即時寫入）。on={on} off={off} 未標={un}")
                return
            if key in ("s", "skip"):
                break
            if key in KEYS:
                commit_one(args.path, idx, row.get("title", ""), KEYS[key], note.strip())
                break
            print("  只認 o / f / s / q（理由接在空白後面）")
        print()

    on, off, un = counts(load(args.path))
    print(f"完成。on={on} off={off} 未標={un}／共 {len(rows)}")
    if un:
        print("（未標的是你按 s 跳過的，再跑一次會只問那些）")
    else:
        print("接著跑：.venv/bin/python scripts/measure_relevance.py")


if __name__ == "__main__":
    main()
