#!/usr/bin/env python3
"""Діагностика решти 112 розбіжностей: пошук REF_ERROR (відповідь знайдена в іншій статті того ж закону)."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import simulate as S

PROJECT = S.PROJECT
BANK = os.path.join(PROJECT, "banks", "mzs-2026.fixed2.json")
OUT = os.path.join(os.path.dirname(__file__), "remaining_112.json")

bank = json.load(open(BANK))

# Зібрати розбіжності з останнього прогону
mismatch_ids = set()
for line in open("/tmp/sim_fixed2_meta4.txt", encoding="utf-8"):
    m = re.match(r"\s*-\s+(\S+)\s+\[(.*?)\]\s+(\S.*)$", line)
    if m and ("лексичний збіг" in m.group(3) or "мета-відповідь" in m.group(3)):
        mismatch_ids.add(m.group(1))

qmap = {}
for sec in bank["sections"]:
    for q in sec["questions"]:
        qmap[q["id"]] = q


def law_html_for_ref(ref):
    fname = S.legislation_file(ref)
    if not fname:
        return None, None
    p = os.path.join(PROJECT, "laws", fname)
    if os.path.exists(p):
        return open(p, encoding="utf-8").read(), fname
    return None, fname


results = []
for qid in sorted(mismatch_ids):
    q = qmap.get(qid)
    if not q:
        continue
    correct = q.get("correct", "")
    ref = q.get("explain", {}).get("ref", "")
    html, fname = law_html_for_ref(ref)
    if not html:
        results.append(
            {"id": qid, "ref": ref, "fname": fname, "cat": "NO_LAW", "correct": correct}
        )
        continue
    # Поточний ref
    cur_title, cur_art = S.extract_article_by_ref(html, ref)
    cur_ratio = None
    if cur_art:
        matched, ratio, words = S.answer_matches_article(correct, cur_art)
        cur_ratio = ratio
    # Шукаємо по всіх статтях
    best = None
    try:
        articles = S.extract_articles(html)
    except Exception:
        articles = []
    for title, body in articles:
        if not body:
            continue
        matched, ratio, words = S.answer_matches_article(correct, body)
        if matched and ratio >= S.LEXICAL_THRESHOLD:
            if best is None or ratio > best[1]:
                best = (title, ratio)
    if best and (cur_ratio is None or best[1] > (cur_ratio or 0) + 0.05):
        results.append(
            {
                "id": qid,
                "ref": ref,
                "fname": fname,
                "cat": "REF_ERROR",
                "correct": correct[:80],
                "cur_ratio": cur_ratio,
                "best_article": best[0],
                "best_ratio": best[1],
            }
        )
    else:
        results.append(
            {
                "id": qid,
                "ref": ref,
                "fname": fname,
                "cat": "GENUINE",
                "correct": correct[:80],
                "cur_ratio": cur_ratio,
            }
        )

json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)

from collections import Counter

print("Всього:", len(results))
print(Counter(r["cat"] for r in results))
print()
print("=== REF_ERROR кандидати ===")
for r in results:
    if r["cat"] == "REF_ERROR":
        print(f"  {r['id']} [{r['fname']}]")
        print(f"      відповідь: {r['correct']!r}")
        print(f"      ref: {r['ref']} (поточний збіг {r['cur_ratio']})")
        print(f"      знайдено в: {r['best_article']} (збіг {r['best_ratio']})")
