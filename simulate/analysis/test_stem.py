#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оцінка ефективності стемінгу для лексичного збігу."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

bank = json.load(open(S.PROJECT / "banks" / "mzs-2026.json", encoding="utf-8"))
law_cache = {}

# Стемінг: префіксна відповідність. Слово w з відповіді "збігається" зі словом
# у статті, якщо їхні перші MIN_STEM літер однакові, або одне є префіксом іншого.
MIN_STEM = 5


def stem_match(word, article_words):
    """Чи слово word має спільний корінь (>=MIN_STEM літер) з якимось словом статті."""
    if len(word) < MIN_STEM:
        return False
    prefix = word[:MIN_STEM]
    for aw in article_words:
        if len(aw) < MIN_STEM:
            continue
        if aw[:MIN_STEM] == prefix:
            return True
        # одне є префіксом іншого (довше слово)
        if aw.startswith(word) or word.startswith(aw):
            return True
    return False


def answer_matches_stem(correct, article_text):
    """Лексичний збіг зі стемінгом."""
    c = S.normalize(correct)
    a = S.normalize(article_text)
    if not c or not a:
        return False, 0.0, []
    words = S.significant_words(correct)
    if not words:
        return False, 0.0, []
    article_words = set(S.significant_words(article_text))
    found = sum(1 for w in words if stem_match(w, article_words))
    ratio = found / len(words)
    return ratio >= S.LEXICAL_THRESHOLD, ratio, words


# Поточний стан
cur_mismatch = 0
stem_fixed = 0
stem_still_mismatch = 0
total_checked = 0

for sec in bank["sections"]:
    for q in sec.get("questions", []):
        ref = (q.get("explain") or {}).get("ref", "")
        correct = q.get("correct", "")
        sid = q.get("_section_id", "")
        if sid == "krainoznavstvo-polsha":
            continue
        fname = S.legislation_file(ref)
        if not fname:
            continue
        if fname not in law_cache:
            p = S.LAWS_DIR / fname
            law_cache[fname] = (
                p.read_text(encoding="utf-8", errors="replace") if p.exists() else None
            )
        html = law_cache[fname]
        if not html:
            continue
        title, art = S.extract_article_by_ref(html, ref)
        if not art:
            continue
        total_checked += 1
        matched, ratio, words = S.answer_matches_article(correct, art)
        if not matched:
            cur_mismatch += 1
            # чи виправляє стемінг?
            sm, sratio, _ = answer_matches_stem(correct, art)
            if sm:
                stem_fixed += 1
            else:
                stem_still_mismatch += 1

print(f"Перевірено питань (з актом): {total_checked}")
print(f"Поточні розбіжності: {cur_mismatch}")
print(f"Стемінг виправляє: {stem_fixed}")
print(f"Стемінг НЕ виправляє: {stem_still_mismatch}")
