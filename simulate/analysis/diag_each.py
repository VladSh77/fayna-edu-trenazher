#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Детальний розбір КОЖНОЇ розбіжності окремо (після зменшення стоп-листа)."""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

bank = json.load(open(S.PROJECT / "banks" / "mzs-2026.json", encoding="utf-8"))
law_cache = {}

def get_article(q):
    ref = (q.get("explain") or {}).get("ref", "")
    if not ref:
        return None, ref
    if ref in law_cache:
        return law_cache[ref], ref
    try:
        fname = S.legislation_file(ref)
        if not fname:
            law_cache[ref] = (None, "no_act"); return law_cache[ref], ref
        p = S.LAWS_DIR / fname
        if not p.exists():
            law_cache[ref] = (None, "no_file"); return law_cache[ref], ref
        html = p.read_text(encoding="utf-8", errors="replace")
        art = S.extract_article_by_ref(html, ref)
        law_cache[ref] = art
        return art, ref
    except Exception as e:
        law_cache[ref] = (None, f"err:{e}")
        return law_cache[ref], ref

def sig_words(correct):
    return S.significant_words(correct)

mismatches = []
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
            matched, ratio, words = lex
        else:
            matched, ratio, words = False, 0.0, []
        stem = 0.0
        if len(words) >= S.MIN_SIGNIFICANT_WORDS and not S.is_neg_question(q.get("question","")):
            stem = S.stem_ratio(correct, art_text)
        if matched or stem >= S.LEXICAL_THRESHOLD:
            continue
        mismatches.append({
            "qid": q.get("id"), "section": q.get("_section",""),
            "question": q.get("question",""), "correct": correct, "ref": ref,
            "ratio": ratio, "words": words, "stem": stem,
            "is_neg": S.is_neg_question(q.get("question","")),
            "is_meta": bool(re.search(r"усі відповіді в
