#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Додає згенерований банк країнознавства Польщі в банк МЗС (mzs-2026.json).

Джерело: bank_krajoznawstwo.json (згенерований gen_krajoznawstwo_bank.py з конспекту).
Конвертує схему {text, options, correct, quote} -> {question, correct, wrong}.
Оновлює total у mzs-2026.json та manifest.json.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(ROOT, "banks", "mzs-2026.json")
MANIFEST_PATH = os.path.join(ROOT, "banks", "manifest.json")
SRC_PATH = os.path.join(
    ROOT,
    "..",
    "..",
    "experimental",
    "DevJournal",
    "projects",
    "iryna-mzs-wicekonsul-2026",
    "bank_krajoznawstwo.json",
)

SECTION_ID = "krainoznavstvo-polsha"
SECTION_TITLE = "Країнознавство (Польща)"


def slugify(text):
    """Транслітерація заголовка розділу в id питання."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def convert(src_path, bank_path, manifest_path):
    with open(src_path, "r", encoding="utf-8") as f:
        src = json.load(f)

    questions = []
    for sec_key in sorted(src.keys(), key=lambda k: int(k)):
        sec = src[sec_key]
        for q in sec.get("questions", []):
            options = q.get("options", [])
            if len(options) != 4:
                continue
            correct_idx = q.get("correct")
            if not isinstance(correct_idx, int) or not (0 <= correct_idx <= 3):
                continue
            correct = options[correct_idx]
            wrong = [o for i, o in enumerate(options) if i != correct_idx]
            qid = f"kraj-{slugify(sec.get('title', sec_key))}-{len(questions) + 1:03d}"
            questions.append(
                {
                    "id": qid,
                    "question": q.get("text", "").strip(),
                    "correct": correct,
                    "wrong": wrong,
                }
            )

    if not questions:
        print("Помилка: немає питань для додавання")
        return 1

    with open(bank_path, "r", encoding="utf-8") as f:
        bank = json.load(f)

    # видалити старий розділ, якщо є
    bank["sections"] = [s for s in bank["sections"] if s["id"] != SECTION_ID]

    new_section = {
        "id": SECTION_ID,
        "title": SECTION_TITLE,
        "count": len(questions),
        "questions": questions,
    }
    bank["sections"].append(new_section)
    bank["total"] = sum(s["count"] for s in bank["sections"])

    with open(bank_path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"Додано розділ «{SECTION_TITLE}»: {len(questions)} питань")
    print(f"Новий total у mzs-2026.json: {bank['total']}")

    # оновити manifest.json
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    for entry in manifest.get("banks", []):
        if entry.get("file") == "mzs-2026.json":
            entry["total"] = bank["total"]
            entry["sections"] = len(bank["sections"])
            break

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(
        f"Оновлено manifest.json: total={bank['total']}, sections={len(bank['sections'])}"
    )
    return 0


if __name__ == "__main__":
    src = SRC_PATH
    if not os.path.exists(src):
        # спроба знайти відносно робочої директорії
        alt = os.path.join(os.getcwd(), "bank_krajoznawstwo.json")
        if os.path.exists(alt):
            src = alt
        else:
            print(f"Не знайдено джерело: {src}")
            print(f"Альтернатива: {alt}")
            raise SystemExit(1)
    raise SystemExit(convert(src, BANK_PATH, MANIFEST_PATH))
