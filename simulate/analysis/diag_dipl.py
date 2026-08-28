#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Діагностика розбіжностей «Про дипломатичну службу»."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

PROJECT = Path(__file__).resolve().parent.parent.parent
BANK = PROJECT / "banks" / "mzs-2026.json"
LAWS = PROJECT / "laws" / "zakon-pro-dyplomatychnu-sluzhbu.html"

html_text = LAWS.read_text(encoding="utf-8", errors="replace")

bank = json.load(open(BANK, encoding="utf-8"))
for sec in bank["sections"]:
    if "дипломатичну службу" in sec["title"].lower():
        qs = sec["questions"]
        break

print(f"Питань у розділі: {len(qs)}\n")
print("=" * 100)

mismatch = 0
for q in qs:
    ref = (q.get("explain") or {}).get("ref", "")
    correct = q.get("correct", "")
    title, art = S.extract_article_by_ref(html_text, ref)
    if not art:
        print(f"[NO_ARTICLE] {q['id']} ref={ref}")
        continue
    matched, ratio, words = S.answer_matches_article(correct, art)
    status = "OK" if matched else "MISMATCH"
    if not matched:
        mismatch += 1
        print(f"[{status}] {q['id']} ref={ref} ratio={ratio:.0%}")
        print(f"    стаття: {title}")
        print(f"    відповідь: {correct[:150]}")
        print(f"    значущі слова: {words[:15]}")
        print("-" * 100)

print(f"\nВсього MISMATCH: {mismatch} / {len(qs)}")
