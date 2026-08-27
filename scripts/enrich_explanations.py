#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Заповнює поле explain: {text, ref} для ВСІХ питань банку mzs-2026.json.

Джерела:
  - Для розділу krainoznavstvo-polsha: використовує вже наявне поле quote
    (дослівна цитата з конспекту) як text, ref = "Конспект країнознавства Польщі".
  - Для решти розділів: генерація через LLM (team_llm.chat_fallback) з посиланням
    на статтю нормативного акта (назва розділу = закон/акт).

Механічний захист від порожніх/дублюючих:
  - text не порожній, довжина >= 20 символів
  - text не дублює питання або правильну відповідь (нормалізоване порівняння)
  - ref не порожній
  - text не дублює text іншого питання в тому ж розділі

Резюмабельність: прогрес зберігається у файлі стану; вже готові питання пропускаються.
"""

import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(ROOT, "banks", "mzs-2026.json")
STATE_PATH = os.path.join(ROOT, "scripts", ".explain_state.json")
KRAJOZNAWSTWO_REF = "Конспект країнознавства Польщі"

# Підключення team_llm (docs-sorter)
sys.path.insert(0, "/Users/kobzar/projects/firm/platforms/docs-sorter")
from team_llm import chat_fallback  # noqa: E402

CHAIN = ["deepseek", "glm", "openai"]

SYSTEM_PROMPT = (
    "Ти — експерт з українського законодавства та міжнародного права для підготовки "
    "до тестування на посаду віцеконсула МЗС України. Твоє завдання — написати коротке "
    "пояснення до тестового питання, чому правильна відповідь є правильною, з посиланням "
    "на конкретну статтю (або пункт/частину) відповідного нормативного акта.\n\n"
    "Вимоги до відповіді:\n"
    "1. Поверни ТІЛЬКИ валідний JSON об'єкт без зайвого тексту, у форматі:\n"
    '   {"text": "пояснення українською, 1-3 речення", "ref": "Назва акта, стаття N"}\n'
    "2. text — стисле пояснення, чому правильна відповідь правильна. Не повторюй дослівно "
    "питання чи відповідь.\n"
    "3. ref — назва нормативного акта та конкретна стаття/пункт, на якій ґрунтується відповідь. "
    "Якщо не впевнений у точному номері статті — вкажи назву акта без номера статті, але "
    "НЕ вигадуй номер. Формат: «Закон України «Про громадянство України», ст. 3» або "
    "«Віденська конвенція про консульські зносини, ст. 5».\n"
    "4. Відповідь має бути українською мовою."
)


def normalize_text(text):
    """Нормалізація для порівняння: нижній регістр, прибрати розділові знаки, зайві пробіли."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[«»\"'`.,;:!?()\-–—]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def validate_explain(explain, question, correct, section_existing_texts):
    """Механічний захист: повертає (ok, reason)."""
    if not isinstance(explain, dict):
        return False, "not_dict"
    text = explain.get("text", "")
    ref = explain.get("ref", "")
    if not isinstance(text, str) or not text.strip():
        return False, "empty_text"
    if len(text.strip()) < 20:
        return False, "text_too_short"
    if not isinstance(ref, str) or not ref.strip():
        return False, "empty_ref"
    # text не дублює питання або відповідь
    nt = normalize_text(text)
    if nt == normalize_text(question) or nt == normalize_text(correct):
        return False, "text_duplicates_q_or_a"
    # text не дублює інші пояснення в розділі
    if nt in section_existing_texts:
        return False, "text_duplicates_section"
    return True, None


def parse_llm_json(raw):
    """Витягує JSON з відповіді LLM (стійкий до markdown-обгорток)."""
    if not raw:
        return None
    raw = raw.strip()
    # прибрати ```json ... ``` обгортку
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    # знайти перший { ... } збалансований
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start : i + 1])
                except Exception:
                    return None
    return None


def load_bank():
    with open(BANK_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_bank(data):
    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"done": {}}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def gen_for_question(question, correct, section_title):
    """Генерує пояснення через LLM. Повертає explain dict або None."""
    user = (
        f"Розділ (нормативний акт): {section_title}\n\n"
        f"Питання: {question}\n\n"
        f"Правильна відповідь: {correct}\n\n"
        "Напиши пояснення та посилання на джерело у форматі JSON."
    )
    for attempt in range(3):
        provider, out = chat_fallback(
            SYSTEM_PROMPT, user, chain=CHAIN, temperature=0.2, max_tokens=400
        )
        if out and not out.startswith("[ERROR"):
            parsed = parse_llm_json(out)
            if parsed:
                return parsed
        time.sleep(2)
    return None


def main():
    data = load_bank()
    state = load_state()
    done = state.get("done", {})

    total = 0
    generated = 0
    skipped = 0
    failed = []

    for sec in data["sections"]:
        sec_id = sec["id"]
        sec_title = sec["title"]
        # вже наявні тексти пояснень у розділі (для захисту від дублювання)
        section_existing_texts = set()
        for q in sec["questions"]:
            if q.get("explain") and q["explain"].get("text"):
                section_existing_texts.add(normalize_text(q["explain"]["text"]))

        for q in sec["questions"]:
            qid = q["id"]
            total += 1
            # резюмабельність: пропустити вже готові
            if q.get("explain") and q["explain"].get("text"):
                skipped += 1
                section_existing_texts.add(normalize_text(q["explain"]["text"]))
                continue
            if done.get(qid):
                skipped += 1
                continue

            correct = q.get("correct", "")
            explain = None

            # Для країнознавства використовуємо наявну цитату з конспекту
            if sec_id == "krainoznavstvo-polsha" and q.get("quote"):
                quote = q["quote"].strip()
                if quote:
                    explain = {"text": quote, "ref": KRAJOZNAWSTWO_REF}

            # Інакше — генерація через LLM
            if explain is None:
                explain = gen_for_question(q["question"], correct, sec_title)

            ok, reason = validate_explain(
                explain, q["question"], correct, section_existing_texts
            )
            if ok:
                q["explain"] = explain
                section_existing_texts.add(normalize_text(explain["text"]))
                generated += 1
                done[qid] = True
            else:
                failed.append((qid, reason))
                done[qid] = False

            # періодичне збереження
            if generated % 5 == 0:
                save_bank(data)
                save_state(state)

    save_bank(data)
    save_state(state)

    print(f"TOTAL: {total}")
    print(f"GENERATED: {generated}")
    print(f"SKIPPED: {skipped}")
    print(f"FAILED: {len(failed)}")
    if failed:
        print("Failed sample:", failed[:20])


if __name__ == "__main__":
    main()
