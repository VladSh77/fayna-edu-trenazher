#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 24: Fix TEXT_MISMATCH questions in banks/mzs-2026.fixed2.json.

Applies verified corrections based on manual examination of laws/ files:
  - Genuine answer errors (fix `correct`)
  - Wrong article references (fix `explain.ref`)

Only high-confidence, law-verified fixes are applied. Verification limitations
(answers correct but source not in laws/, or LLM paraphrase rejection) are left
unchanged and reported separately.
"""

import json

BANK = "banks/mzs-2026.fixed2.json"

# (id, field, old_value_substring, new_value)
# field: 'correct' or 'ref'
FIXES = [
    # --- Genuine answer errors ---
    # Регламент КМУ §14 п.2: засідання проводяться "щосереди", час визначає Прем'єр-міністр
    ("dodatok-01-2-1601", "correct", "щосереди о 10-й годині", "щосереди"),
    # Регламент КМУ §38: якщо строк погодження не визначено розробником -> двадцятиденний строк
    ("dodatok-01-2-1610", "correct", "місяць", "двадцять днів"),
    # Віденська конвенція дипломатичні ст.34: звільнення від усіх податків і зборів
    (
        "dodatok-4-497",
        "correct",
        "від єдиного соціального внеску та пенсійного збору в країні перебування",
        "від усіх податків і зборів, особистих або майнових, державних, регіональних або муніципальних",
    ),
    # Віденська конвенція консульські ст.49: звільнення від усіх податків і зборів
    (
        "2019-11-26-dod2-1150",
        "correct",
        "від єдиного соціального внеску та пенсійного збору в країні перебування",
        "від усіх податків і зборів, особистих або майнових, державних, регіональних або муніципальних",
    ),
    # --- Wrong article references ---
    # Громадянство: рішення про оформлення набуття громадянства керівником ЗДУ -> ст.25 (повноваження МЗС)
    ("dodatok-4-031", "ref", "ст. 10", "ст. 25"),
    # Громадянство: вихід з громадянства -> ст.18
    ("dodatok-4-042", "ref", "ст. 9", "ст. 18"),
    # Громадянство: набуття громадянства за народженням -> ст.7
    ("dodatok-4-102", "ref", "ст. 3", "ст. 7"),
    # Регламент КМУ: експертиза закону на підпис Президентові -> §101
    ("dodatok-01-2-1619", "ref", "§ 12", "§ 101"),
    # Віденська конвенція дипломатичні: податки -> ст.34 (ст.33 - соціальне забезпечення)
    ("dodatok-4-497", "ref", "ст. 33", "ст. 34"),
    # Функції МЗС -> Положення про МЗС (не Віденська конвенція)
    (
        "bank_dodatok3-1780",
        "ref",
        "Віденська конвенція про консульські зносини, ст. 5",
        "Положення про МЗС",
    ),
    # Консульський збір за нотаріальні дії -> Закон про нотаріат ст.38
    (
        "bank_dodatok3-1814",
        "ref",
        "Інструкція про порядок справляння сум консульського збору, п. 5",
        "Закон України «Про нотаріат», ст. 38",
    ),
]


def main():
    with open(BANK) as f:
        bank = json.load(f)

    applied = []
    not_found = []
    for qid, field, old, new in FIXES:
        found = False
        for sec in bank["sections"]:
            for q in sec["questions"]:
                if q["id"] != qid:
                    continue
                found = True
                if field == "correct":
                    if old not in q["correct"]:
                        not_found.append((qid, field, "correct value mismatch", old))
                        break
                    q["correct"] = new
                    applied.append((qid, "correct", old, new))
                elif field == "ref":
                    ref = q.get("explain", {}).get("ref", "")
                    if old not in ref:
                        not_found.append((qid, field, "ref value mismatch", old))
                        break
                    q["explain"]["ref"] = new
                    applied.append((qid, "ref", old, new))
                break
            if found:
                break
        if not found:
            not_found.append((qid, field, "question id not found", old))

    with open(BANK, "w") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print("=== APPLIED FIXES ===")
    for a in applied:
        print(f"  [{a[0]}] {a[1]}: '{a[2]}' -> '{a[3]}'")
    print(f"\nTotal applied: {len(applied)}")
    if not_found:
        print("\n=== NOT FOUND / MISMATCH ===")
        for nf in not_found:
            print(f"  {nf}")


if __name__ == "__main__":
    main()
