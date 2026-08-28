#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Дуже ретельний розбір КОЖНОЇ з 384 розбіжностей окремо.
Для кожної розбіжності:
  - показує питання, правильну відповідь, ref (який вказує на НЕПРАВИЛЬНУ статтю)
  - шукає по ВСЬОМУ закону статтю, де відповідь реально міститься (auto-find)
  - класифікує результат
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

MIS = json.load(open(Path(__file__).resolve().parent / "mismatches_384.json", encoding="utf-8"))

# Кеш: ref -> (fname, html)
law_html_cache = {}

def get_law_html(ref):
    if ref in law_html_cache:
        return law_html_cache[ref]
    fname = S.legislation_file(ref)
    if not fname:
        law_html_cache[ref] = None
        return None
    p = S.LAWS_DIR / fname
    if not p.exists():
        law_html_cache[ref] = None
        return None
    html = p.read_text(encoding="utf-8", errors="replace")
    law_html_cache[ref] = html
    return html

def all_articles(html):
    """Всі статті закону через всі відомі екстрактори."""
    arts = S.extract_articles(html)
    if not arts:
        arts = S._extract_statut_articles(html)
    if not arts:
        arts = S._extract_vienna_articles(html)
    return arts

def best_article(correct, html):
    """Шукає по всьому закону статтю з найкращим збігом відповіді."""
    arts = all_articles(html)
    best = None
    best_ratio = 0.0
    best_matched = False
    for title, body in arts:
        body_text = body or ""
        lex = S.answer_matches_article(correct, body_text)
        if isinstance(lex, tuple):
            matched, ratio, words = lex
        else:
            matched, ratio, words = False, 0.0, []
        # враховуємо і стемінг
        stem = 0.0
        if len(words) >= S.MIN_SIGNIFICANT_WORDS and not S.is_neg_question(""):
            stem = S.stem_ratio(correct, body_text)
        score = max(ratio, stem)
        if score > best_ratio:
            best_ratio = score
            best = (title, matched, ratio, stem, words)
    return best, best_ratio

# Групуємо за законом
from collections import OrderedDict, defaultdict
by_law = OrderedDict()
for m in MIS:
    ref = m.get("ref", "")
    html = get_law_html(ref)
    fname = S.legislation_file(ref) or "?"
    by_law.setdefault(fname, []).append(m)

print("=" * 100)
print(f"ПОВНИЙ РОЗБІР {len(MIS)} РОЗБІЖНОСТЕЙ, згруповано за законами")
print("=" * 100)

total_found = 0
total_notfound = 0
for fname, items in by_law.items():
    print("\n" + "#" * 100)
    print(f"ЗАКОН: {fname}  ({len(items)} розбіжностей)")
    print("#" * 100)
    found = 0
    for m in items:
        correct = m.get("correct", "")
        ref = m.get("ref", "")
        html = get_law_html(ref)
        best, best_ratio = best_article(correct, html) if html else (None, 0.0)
        qid = m.get("qid", "?")
        section = m.get("section", "")
        question = m.get("question", "")
        is_meta = m.get("is_meta", False)
        is_neg = m.get("is_neg", False)
        if best and best_ratio >= S.LEXICAL_THRESHOLD:
            status = "ЗНАЙДЕНО"
            found += 1
            total_found += 1
        else:
            status = "НЕ ЗНАЙДЕНО"
            total_notfound += 1
        print("\n" + "-" * 90)
        print(f"[{qid}] {status} | розділ: {section}")
        print(f"  Питання: {question}")
        print(f"  Відповідь: {correct[:200]}")
        print(f"  ref (НЕПРАВИЛЬНИЙ): {ref}")
        if best:
            title, matched, ratio, stem, words = best
            print(f"  -> Правильна стаття: {title} | ratio={ratio:.2f} stem={stem:.2f} | matched={matched}")
        else:
            print(f"  -> Статтю з відповіддю НЕ знайдено (перефразування/інший закон/мета-відповідь)")
    print(f"\n  ПІДСУМОК по {fname}: знайдено правильну статтю {found}/{len(items)}")

print("\n" + "=" * 100)
print(f"ЗАГАЛЬНИЙ ПІДСУМОК: знайдено правильну статтю {total_found}/{len(MIS)}, не знайдено {total_notfound}/{len(MIS)}")
print("=" * 100)
