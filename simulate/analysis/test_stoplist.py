#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Порівнює поточний STOP-лист із зменшеним (лише функційні слова).
Показує, скільки питань відновлюється і чи немає регресій серед
вже підтверджених лексикою."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import simulate as S

bank = json.load(open(S.PROJECT / "banks" / "mzs-2026.json", encoding="utf-8"))

# Зменшений стоп-лист: лише справжні функційні слова (прийменники,
# сполучники, займенники, допоміжні дієслова) + мета-слова відповідей.
REDUCED_STOP = {
    # займенники / сполучники / прийменники
    "який",
    "яка",
    "яке",
    "які",
    "що",
    "це",
    "для",
    "при",
    "про",
    "до",
    "від",
    "на",
    "за",
    "з",
    "у",
    "в",
    "і",
    "та",
    "а",
    "не",
    "ні",
    "чи",
    "як",
    "так",
    "то",
    "по",
    "під",
    "над",
    "без",
    "або",
    "й",
    "згідно",
    "відповідно",
    "зокрема",
    "також",
    "всі",
    "усі",
    "разі",
    "раз",
    "пізніш",
    "пізніше",
    "нижченаведених",
    "нижченаведені",
    "перелічених",
    "перелічені",
    "перерахованих",
    "перераховані",
    "наведених",
    "наведені",
    # допоміжні дієслова
    "може",
    "можуть",
    "бути",
    "є",
    "можна",
    "можливо",
    "повинен",
    "повинна",
    "повинні",
    "має",
    "мають",
    "мати",
    "треба",
    "потрібно",
    # мета-слова відповідей
    "вірні",
    "правильні",
    "відповіді",
    "відповідь",
    "варіанти",
    "варіант",
}


def sig_words(text, stop):
    words = re.findall(r"[а-яіїєґ'’\-]+", S.normalize(text))
    return [w for w in words if len(w) >= 4 and w not in stop]


def ratio(correct, art, stop):
    cw = sig_words(correct, stop)
    if not cw:
        return None
    aw = set(sig_words(art, stop))
    if not aw:
        return None
    found = sum(1 for w in cw if w in aw)
    return found / len(cw)


law_cache = {}


def get_art(q):
    ref = (q.get("explain") or {}).get("ref", "")
    if not ref:
        return None
    if ref in law_cache:
        return law_cache[ref]
    fname = S.legislation_file(ref)
    if not fname:
        law_cache[ref] = None
        return None
    p = S.LAWS_DIR / fname
    if not p.exists():
        law_cache[ref] = None
        return None
    html = p.read_text(encoding="utf-8", errors="replace")
    art = S.extract_article_by_ref(html, ref)
    law_cache[ref] = art
    return art


old_verified = 0
new_verified = 0
regressions = []  # було verified, стало ні
recovered = []  # було 0%, стало >=60%
still_zero = 0
meta_answers = 0

for sec in bank.get("sections", []):
    for q in sec.get("questions", []):
        if q.get("_section_id") == "krainoznavstvo-polsha":
            continue
        correct = q.get("correct") or ""
        if not correct:
            continue
        art = get_art(q)
        if not art:
            continue
        art_text = art[1] if isinstance(art, tuple) else str(art)

        old = S.answer_matches_article(correct, art_text)
        old_ratio = old[1] if isinstance(old, tuple) else old
        old_ok = old_ratio >= 0.6 and len(S.significant_words(correct)) >= 3

        new = ratio(correct, art_text, REDUCED_STOP)
        new_ok = new is not None and new >= 0.6

        if old_ok:
            old_verified += 1
            if not new_ok:
                regressions.append((q.get("id"), correct, old_ratio, new))
        if new_ok:
            new_verified += 1
            if not old_ok:
                recovered.append(
                    (q.get("id"), q.get("_section"), correct, old_ratio, new)
                )
        if old_ratio == 0.0 and not new_ok:
            still_zero += 1
            if "усі відповіді" in correct.lower() or "всі відповіді" in correct.lower():
                meta_answers += 1

print(f"Підтверджено старим стоп-листом: {old_verified}")
print(f"Підтверджено зменшеним стоп-листом: {new_verified}")
print(f"  Регресій (було OK, стало ні): {len(regressions)}")
for r in regressions[:10]:
    print(f"    REGRESS [{r[0]}] {r[1][:60]} old={r[2]:.2f} new={r[3]}")
print(f"  Відновлено (було 0%, стало >=60%): {len(recovered)}")
for r in recovered[:10]:
    print(f"    RECOVER [{r[0]}] ({r[1]}) {r[2][:50]} old={r[3]:.2f} new={r[4]:.2f}")
print(f"Все ще 0%: {still_zero} (з них мета-відповіді 'усі відповіді': {meta_answers})")
