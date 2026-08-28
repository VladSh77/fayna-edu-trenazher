#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Консервативне авто-виправлення ref для 192 REF_ERROR розбіжностей.
Виправляємо ТІЛЬКИ питання з 384 розбіжностей, і ТІЛЬКИ коли відповідь
знайдена ДОСЛІВНО (matched=True) з ratio>=0.6. Стемінг-збіги НЕ використовуємо
для виправлення ref (ризик хибних).
Створює виправлену копію банку + звіт змін.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

BANK_PATH = S.PROJECT / "banks" / "mzs-2026.json"
OUT_PATH = S.PROJECT / "banks" / "mzs-2026.fixed.json"
REPORT = Path(__file__).resolve().parent / "fix_refs_report.json"

# Тільки ці qid (з 384 розбіжностей) можна виправляти
MIS = json.load(open(Path(__file__).resolve().parent / "mismatches_384.json", encoding="utf-8"))
FIXABLE_IDS = set(m["qid"] for m in MIS)

bank = json.load(open(BANK_PATH, encoding="utf-8"))
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
        if matched and ratio > best_ratio:
            best_ratio = ratio
            best = (title, matched, ratio)
    return best, best_ratio

def article_num_from_title(title):
    m = re.search(r"(?:Стаття|Article|С т а т т я)\s+([0-9]+(?:\s*-\s*[0-9]+)?)", title, re.IGNORECASE)
    if m:
        return re.sub(r"\s*-\s*", "-", m.group(1))
    return None

def rewrite_ref(ref, new_num):
    new_ref = re.sub(r"ст(?:атя)?\.?\s*[0-9]+(?:\s*-\s*[0-9]+)?", f"ст. {new_num}", ref, count=1, flags=re.IGNORECASE)
    if new_ref == ref:
        new_ref = re.sub(r"Article\s+[0-9]+(?:\s*-\s*[0-9]+)?", f"Article {new_num}", ref, count=1, flags=re.IGNORECASE)
    return new_ref

changes = []
skipped = []
for sec in bank.get("sections", []):
    for q in sec.get("questions", []):
        qid = q.get("id")
        if qid not in FIXABLE_IDS:
            continue  # ТІЛЬКИ питання з 384 розбіжностей
        expl = q.get("explain") or {}
        ref = expl.get("ref", "")
        if not ref:
            continue
        correct = q.get("correct") or ""
        if not correct:
            continue
        html = get_law_html(ref)
        if html is None:
            skipped.append({"qid": qid, "reason": "no_law"}); continue
        best, best_ratio = best_article(correct, html)
        if not best or best_ratio < S.LEXICAL_THRESHOLD:
            skipped.append({"qid": qid, "reason": f"no_verbatim_match ratio={best_ratio:.2f}"}); continue
        title, matched, ratio = best
        new_num = article_num_from_title(title)
        if new_num is None:
            skipped.append({"qid": qid, "reason": "no_num_in_title", "title": title}); continue
        cur_m = re.search(r"ст(?:атя)?\.?\s*([0-9]+(?:\s*-\s*[0-9]+)?)", ref, re.IGNORECASE)
        cur_num = re.sub(r"\s*-\s*", "-", cur_m.group(1)) if cur_m else None
        if cur_num == new_num:
            skipped.append({"qid": qid, "reason": "already_correct"}); continue
        new_ref = rewrite_ref(ref, new_num)
        changes.append({
            "qid": qid, "old_ref": ref, "new_ref": new_ref,
            "correct_article": title, "ratio": round(ratio, 3), "matched": matched,
        })
        expl["ref"] = new_ref

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(bank, f, ensure_ascii=False, indent=2)
with open(REPORT, "w", encoding="utf-8") as f:
    json.dump({"total_changes": len(changes), "skipped": skipped, "changes": changes}, f, ensure_ascii=False, indent=2)

print(f"Виправлено ref (консервативно, лише 384, лише дослівно): {len(changes)}")
print(f"Пропущено: {len(skipped)}")
from collections import Counter
c = Counter(s['reason'] for s in skipped)
print('Причини пропуску:', dict(c))
print(f"Виправлений банк: {OUT_PATH}")
