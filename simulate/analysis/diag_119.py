#!/usr/bin/env python3
"""Діагностика решти 119 розбіжностей після META-фіксу."""

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import simulate as S

PROJECT = S.PROJECT
BANK = os.path.join(PROJECT, "banks", "mzs-2026.fixed2.json")
OUT = os.path.join(os.path.dirname(__file__), "remaining_119.json")

bank = json.load(open(BANK))

# Зібрати розбіжності з останнього прогону
mismatches = []
for line in open("/tmp/sim_fixed2_meta3.txt", encoding="utf-8"):
    line = line.rstrip("\n")
    m = re.match(r"\s*-\s+(\S+)\s+\[(.*?)\]\s+(\S.*)$", line)
    if m and ("лексичний збіг" in m.group(3) or "мета-відповідь" in m.group(3)):
        mismatches.append(
            {"id": m.group(1), "section": m.group(2), "detail": m.group(3)}
        )

# Додати відповідь/ref з банку
qmap = {}
for sec in bank["sections"]:
    for q in sec["questions"]:
        qmap[q["id"]] = q


def load_law_html(fname):
    p = os.path.join(PROJECT, "laws", fname)
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    return None


# Мапа: назва закону -> файл
law_files = {}
for f in os.listdir(os.path.join(PROJECT, "laws")):
    if f.endswith(".html"):
        law_files[f] = f


def find_law_file(ref):
    """Знайти файл закону за ref."""
    for f in law_files:
        base = f.replace(".html", "").replace("-", " ").lower()
        # спроба зіставити за ключовими словами
    # простіший підхід: шукаємо в банку файл, який вже використовувався
    return None


results = []
for mm in mismatches:
    q = qmap.get(mm["id"])
    if not q:
        continue
    correct = q.get("correct", "")
    ref = q.get("explain", {}).get("ref", "")
    words = S.significant_words(correct)
    nwords = len(words)
    cat = "SHORT" if nwords <= 4 else "OTHER"
    results.append(
        {
            "id": mm["id"],
            "section": mm["section"],
            "detail": mm["detail"],
            "correct": correct,
            "ref": ref,
            "nwords": nwords,
            "cat": cat,
        }
    )

json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)

from collections import Counter

print("Всього:", len(results))
print(Counter(r["cat"] for r in results))
print()
print("=== SHORT (<=4 слів) ===")
for r in results:
    if r["cat"] == "SHORT":
        print(f"  {r['id']} [{r['nwords']} сл] {r['correct'][:60]!r} | {r['ref']}")
