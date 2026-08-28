#!/usr/bin/env python3
"""Для кожного REF_INVALID питання з ACT_OK|NO_ARTICLE: знайти статтю в
відповідному файлі закону, яка найкраще збігається з відповіддю (лексично).
Показує, чи можна виправити ref."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulate import (  # noqa: E402
    LAWS_DIR,
    extract_articles,
    legislation_file,
    significant_words,
)

with open(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "simulation_results.json"
    )
) as f:
    data = json.load(f)

items = data["results"]
ref_inv = [i for i in items if i.get("status") == "REF_INVALID"]

# Load bank for correct answers
with open(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "banks",
        "mzs-2026.fixed2.json",
    )
) as f:
    bank = json.load(f)
qmap = {}
for sec in bank["sections"]:
    for q in sec["questions"]:
        qmap[q["id"]] = q


def lex_ratio(correct, article_text):
    cw = significant_words(correct)
    if not cw:
        return 0.0
    aw = significant_words(article_text or "")
    if not aw:
        return 0.0
    hit = sum(1 for w in cw if w in aw)
    return hit / len(cw)


for i in ref_inv:
    qid = i["id"]
    ref = i.get("ref") or ""
    fname = legislation_file(ref)
    if not fname:
        continue
    path = LAWS_DIR / fname
    if not path.exists():
        continue
    html = path.read_text(encoding="utf-8", errors="replace")
    q = qmap.get(qid, {})
    correct = q.get("correct", "")
    # find best matching article
    best = (0.0, None)
    for title, body in extract_articles(html):
        r = lex_ratio(correct, body)
        if r > best[0]:
            best = (r, title)
    print(f"{qid} | best={best[0]:.0%} | {best[1]} | ref={ref[:60]}")
