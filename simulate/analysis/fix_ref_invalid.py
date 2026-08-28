#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 24: Fix REF_INVALID references in banks/mzs-2026.fixed2.json.

Applies verified ref corrections based on manual examination of laws/ files.
Each new ref was verified to resolve via legislation_file() + extract_article_by_ref()
as FOUND (see diag_best_article.py + manual verification of article text vs answer).
"""

import json

BANK = "banks/mzs-2026.fixed2.json"

# (id, old_ref_substring, new_ref)
FIXES = [
    # Угода про асоціацію: "на який строк укладена" -> на необмежений строк -> ст. 481 "Строк дії"
    (
        "2019-11-26-dod2-1283",
        "преамбула",
        "Угода про асоціацію між Україною та ЄС, ст. 481",
    ),
    # Угода про асоціацію: "яка міжнародна організація є стороною" -> Євратом -> ст. 482 "Визначення Сторін"
    (
        "2019-11-26-dod2-1299",
        "преамбула",
        "Угода про асоціацію між Україною та ЄС, ст. 482",
    ),
    # Вибори Президента: строк подання заяви -> ст. 46 (Виборчий кодекс)
    (
        "dodatok-4-361",
        "Закон України «Про вибори Президента України», ст. 36-1",
        "Виборчий кодекс України, ст. 46",
    ),
    # Вибори нардепів: строк подання заяви -> ст. 7 (Державний реєстр виборців)
    (
        "dodatok-4-397",
        "ст. 39",
        "Закон України «Про Державний реєстр виборців», ст. 7",
    ),
    # Вибори нардепів: скриньки великої дільниці -> ст. 62 (Виборчий кодекс)
    (
        "dodatok-4-410",
        'Закон України "Про вибори народних депутатів України"',
        "Виборчий кодекс України, ст. 62",
    ),
    # Казначейство: меню-вимога -> форма N З-4
    (
        "dodatok-4-584",
        "п. про меню-вимогу",
        "Наказ Державного казначейства України від 18.12.2000 № 130, форма N З-4",
    ),
    # Казначейство: періодичність перевірки книги -> форма N З-9
    (
        "dodatok-4-587",
        "п. 5",
        "Наказ Державного казначейства України від 18.12.2000 № 130, форма N З-9",
    ),
    # Казначейство: хто перевіряє книгу -> форма N З-9
    (
        "dodatok-4-588",
        "п. про книгу складського обліку запасів",
        "Наказ Державного казначейства України від 18.12.2000 № 130, форма N З-9",
    ),
    # Казначейство: спосіб фіксації перевірки -> форма N З-9
    (
        "dodatok-4-589",
        "п. 5",
        "Наказ Державного казначейства України від 18.12.2000 № 130, форма N З-9",
    ),
]


def main():
    with open(BANK) as f:
        bank = json.load(f)

    applied = []
    not_found = []
    for qid, old, new in FIXES:
        found = False
        for sec in bank["sections"]:
            for q in sec["questions"]:
                if q["id"] != qid:
                    continue
                found = True
                ref = q.get("explain", {}).get("ref", "")
                if old not in ref:
                    not_found.append((qid, "ref value mismatch", old, ref))
                    break
                q["explain"]["ref"] = new
                applied.append((qid, old, new))
                break
            if found:
                break
        if not found:
            not_found.append((qid, "question id not found", old, ""))

    with open(BANK, "w") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print("=== APPLIED REF FIXES ===")
    for a in applied:
        print(f"  [{a[0]}] '{a[1]}' -> '{a[2]}'")
    print(f"\nTotal applied: {len(applied)}")
    if not_found:
        print("\n=== NOT FOUND / MISMATCH ===")
        for nf in not_found:
            print(f"  {nf}")


if __name__ == "__main__":
    main()
