#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Класифікація кожної з 384 розбіжностей за першопричиною."""
import json, re, sys
from pathlib import Path
from collections import OrderedDict, defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

MIS = json.load(open(Path(__file__).resolve().parent / "mismatches_384.json", encoding="utf-8"))
law_html_cache = {}

def get_law_html(ref):
    if ref in law_html_cache:
        return law_html_cache[ref]
    fname = S.legislation_file(ref)
    if not fname:
        law_html_cache[ref] = None; return None
    p = S.LAWS_DIR / fname
    if not p.exists():
        law_html_cache[ref] = None; return None
    html = p.read_text(encoding="utf-8", errors="replace")
    law_html_cache[ref] = html
    return html

def is_english(html):
    txt = S.strip_tags(html)
    cyr = len(re.findall(r'[а-яА-ЯіїєґІЇЄҐ]', txt))
    lat = len(re.findall(r'[a-zA-Z]', txt))
    return lat > cyr

def all_articles(html):
    arts = S.extract_articles(html)
    if not arts:
        arts = S._extract_statut_articles(html)
    if not arts:
        arts = S._extract_vienna_articles(html)
    return arts

def best_article(correct, html):
    arts = all_articles(html)
    best = None; best_ratio = 0.0
    for title, body in arts:
        body_text = body or ""
        lex = S.answer_matches_article(correct, body_text)
        if isinstance(lex, tuple):
            matched, ratio, words = lex
        else:
            matched, ratio, words = False, 0.0, []
        stem = 0.0
        if len(words) >= S.MIN_SIGNIFICANT_WORDS:
            stem = S.stem_ratio(correct, body_text)
        score = max(ratio, stem)
        if score > best_ratio:
            best_ratio = score
            best = (title, matched, ratio, stem, words)
    return best, best_ratio

META_RE = re.compile(r"усі відповіді (правильні|вірні)|всі відповіді (правильні|вірні)|усі перелічені|всі перелічені", re.IGNORECASE)

def classify(m):
    correct = m.get("correct", "")
    ref = m.get("ref", "")
    qid = m.get("qid", "?")
    html = get_law_html(ref)
    # 1. Мета-відповідь
    if META_RE.search(correct):
        return "META_ANSWER", None
    # 2. Закон англійською
    if html is not None and is_english(html):
        return "ENGLISH_LAW", None
    # 3. Немає акта/файлу
    if html is None:
        return "NO_ACT", None
    # 4. Шукаємо правильну статтю
    best, best_ratio = best_article(correct, html)
    if best and best_ratio >= S.LEXICAL_THRESHOLD:
        return "REF_ERROR", best
    # 5. Коротка відповідь (без значущих слів)
    sig = S.significant_words(correct)
    if len(sig) < S.MIN_SIGNIFICANT_WORDS:
        return "SHORT_ANSWER", None
    # 6. Перефразування
    return "PARAPHRASE", None

buckets = defaultdict(list)
for m in MIS:
    cat, best = classify(m)
    buckets[cat].append((m, best))

order = ["REF_ERROR", "ENGLISH_LAW", "PARAPHRASE", "META_ANSWER", "SHORT_ANSWER", "NO_ACT"]
print("=" * 90)
print("КЛАСИФІКАЦІЯ 384 РОЗБІЖНОСТЕЙ ЗА ПЕРШОПРИЧИНОЮ")
print("=" * 90)
for cat in order:
    items = buckets.get(cat, [])
    print(f"\n### {cat}: {len(items)}")
    if cat == "REF_ERROR":
        # згрупувати за законом
        bylaw = defaultdict(int)
        for m, best in items:
            fname = S.legislation_file(m.get("ref","")) or "?"
            bylaw[fname] += 1
        for f, c in sorted(bylaw.items(), key=lambda x:-x[1]):
            print(f"   {f}: {c}")
    elif cat == "ENGLISH_LAW":
        bylaw = defaultdict(int)
        for m, best in items:
            fname = S.legislation_file(m.get("ref","")) or "?"
            bylaw[fname] += 1
        for f, c in sorted(bylaw.items(), key=lambda x:-x[1]):
            print(f"   {f}: {c}")
    else:
        for m, best in items:
            print(f"   [{m.get('qid')}] {m.get('correct','')[:80]}")

total = sum(len(v) for v in buckets.values())
print("\n" + "=" * 90)
print(f"РАЗОМ: {total}")
for cat in order:
    print(f"  {cat}: {len(buckets.get(cat,[]))}")
print("=" * 90)
