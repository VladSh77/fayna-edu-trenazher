#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Діагностика 0% лексичних збігів: для кожного питання з 0% збігом
друкує питання, правильну відповідь, ref і витягнутий текст статті,
щоб зрозуміти, чому немає збігу (неправильна стаття / перефразування /
відсутній акт)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

bank = json.load(open(S.PROJECT / "banks" / "mzs-2026.json", encoding="utf-8"))
law_cache = {}

# Фільтр за законом (підрядок у назві розділу), порожньо = всі
LAW_FILTER = sys.argv[1] if len(sys.argv) > 1 else ""
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0


def get_article(q):
    ref = (q.get("explain") or {}).get("ref", "")
    if not ref:
        return None, ref
    if ref in law_cache:
        return law_cache[ref], ref
    try:
        fname = S.legislation_file(ref)
        if not fname:
            law_cache[ref] = (None, "no_act")
            return law_cache[ref], ref
        p = S.LAWS_DIR / fname
        if not p.exists():
            law_cache[ref] = (None, "no_file")
            return law_cache[ref], ref
        html = p.read_text(encoding="utf-8", errors="replace")
        art = S.extract_article_by_ref(html, ref)
        law_cache[ref] = art
        return art, ref
    except Exception as e:
        law_cache[ref] = (None, f"err:{e}")
        return law_cache[ref], ref


count = 0
for sec in bank.get("sections", []):
    for q in sec.get("questions", []):
        sid = q.get("_section_id", "")
        if sid == "krainoznavstvo-polsha":
            continue
        correct = q.get("correct") or ""
        if not correct:
            continue
        art, ref = get_article(q)
        if not art:
            continue
        art_text = art[1] if isinstance(art, tuple) else str(art)
        lex = S.answer_matches_article(correct, art_text)
        if isinstance(lex, tuple):
            lex = lex[1]
        if lex != 0.0:
            continue
        section = q.get("_section", "")
        if LAW_FILTER and LAW_FILTER.lower() not in section.lower():
            continue
        count += 1
        if LIMIT and count > LIMIT:
            break
        print("=" * 80)
        print(f"[{q.get('id')}] ({section})")
        print(f"Q: {q.get('question')}")
        print(f"A: {correct}")
        print(f"REF: {ref}")
        # Показуємо перші 400 символів статті
        art_clean = S.normalize(art_text)
        print(f"ART({len(art_clean)} chars): {art_clean[:400]}")
    if LIMIT and count > LIMIT:
        break

print("=" * 80)
print(f"Всього показано 0% збігів: {count}")
