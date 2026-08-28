#!/usr/bin/env python3
"""Діагностика 86 LLM-відхилених: пошук відповіді по ВСІХ законах, щоб знайти правильний ref."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import simulate as S

PROJECT = S.PROJECT
BANK = os.path.join(PROJECT, "banks", "mzs-2026.fixed2.json")
OUT = os.path.join(os.path.dirname(__file__), "llm_rejected_86.json")

bank = json.load(open(BANK))
rejected_ids = set()
for line in open("/tmp/llm_rejected_ids.txt", encoding="utf-8"):
    line = line.strip().lstrip("-").strip()
    if line:
        rejected_ids.add(line)

qmap = {}
for sec in bank["sections"]:
    for q in sec["questions"]:
        qmap[q["id"]] = q

# Завантажити всі закони
laws = {}
for f in os.listdir(os.path.join(PROJECT, "laws")):
    if f.endswith(".html"):
        laws[f] = open(os.path.join(PROJECT, "laws", f), encoding="utf-8").read()

results = []
for qid in sorted(rejected_ids):
    q = qmap.get(qid)
    if not q:
        continue
    correct = q.get("correct", "")
    ref = q.get("explain", {}).get("ref", "")
    cur_fname = S.legislation_file(ref)
    # Шукаємо відповідь по всіх законах
    best = None
    for fname, html in laws.items():
        try:
            articles = S.extract_articles(html)
        except Exception:
            continue
        for title, body in articles:
            if not body:
                continue
            matched, ratio, words = S.answer_matches_article(correct, body)
            if matched and ratio >= S.LEXICAL_THRESHOLD:
                if best is None or ratio > best[2]:
                    best = (fname, title, ratio)
    results.append(
        {
            "id": qid,
            "correct": correct[:90],
            "ref": ref,
            "cur_fname": cur_fname,
            "found": best,
        }
    )

json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)

found = [r for r in results if r["found"]]
notfound = [r for r in results if not r["found"]]
print(f"Всього: {len(results)}")
print(f"Знайдено в іншому законі/статті (REF_ERROR): {len(found)}")
print(f"Не знайдено ніде (можливо, неправильна відповідь): {len(notfound)}")
print()
print("=== REF_ERROR (знайдено в іншому місці) ===")
for r in found:
    print(f"  {r['id']} [{r['cur_fname']}]")
    print(f"      відповідь: {r['correct']!r}")
    print(f"      ref: {r['ref']}")
    print(f"      знайдено: {r['found'][0]} / {r['found'][1]} (збіг {r['found'][2]})")
