#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Виправляє пояснення з ref == "не перевірено" (або без конкретної статті).
Для цих питань LLM не знайшов норму в наданому тексті акта, тому:
  - для розділів з MD-файлом — повторюємо генерацію з більшим фрагментом тексту;
  - для тематичних розділів (без MD) — LLM має вказати реальний акт/джерело
    зі своїх знань, а не "не перевірено".

Механічний захист: text не порожній (>=20), ref не порожній і НЕ містить
"не перевірено". Резюмабельність через стан.
"""

import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(ROOT, "banks", "mzs-2026.json")
STATE_PATH = os.path.join(ROOT, "scripts", ".fix_unverified_state.json")
MD_OUT = "/Users/kobzar/Library/Mobile Documents/com~apple~CloudDocs/📚 База знань/_MD"

sys.path.insert(0, "/Users/kobzar/projects/firm/platforms/docs-sorter")
from team_llm import chat_fallback  # noqa: E402

CHAIN = [
    "openai",
    "glm",
    "deepseek",
    "groq",
    "qwen",
    "moonshot",
    "openrouter",
    "cloudflare",
]

# Мапа розділів -> (MD-файл, назва акта) — ті самі, що в enrich_explanations_v2
SECTION_MD = {
    "uhoda-pro-asotsiatsiiu-mizh-ukrainoiu-z": (
        "uhoda-pro-asotsiatsiiu-ukraina-yes.md",
        "Угода про асоціацію між Україною та ЄС",
    ),
    "pravyla-oformlennia-viz-dlia-v-izdu-v": (
        "pravyla-oformlennia-viz.md",
        "Постанова КМУ від 01.03.2017 № 118 «Про затвердження Правил оформлення віз»",
    ),
    "zakon-ukrainy-pro-derzhavnu": (
        "zakon-pro-derzhavnu-reiestratsiiu-aktiv-tsyvilnoho-stanu.md",
        "Закон України «Про державну реєстрацію актів цивільного стану»",
    ),
    "zakon-ukrainy-pro-vybory-narodnykh": (
        "zakon-pro-vybory-narodnykh-deputativ.md",
        "Закон України «Про вибори народних депутатів України»",
    ),
}

# Тематичні розділи без MD — підказка про відповідний акт
SECTION_HINT = {
    "vchynennia-notarialnykh-dii": (
        "Питання стосуються вчинення нотаріальних дій консулом. "
        "Джерела: Закон України «Про нотаріат», Цивільний кодекс України, "
        "Віденська конвенція про консульські зносини (1963)."
    ),
    "oformlennia-vizovykh-dokumentiv": (
        "Питання стосуються оформлення візових документів. "
        "Джерела: Постанова КМУ від 01.03.2017 № 118 «Про затвердження Правил оформлення віз», "
        "Закон України «Про правовий статус іноземців та осіб без громадянства»."
    ),
    "kryzove-reahuvannia": (
        "Питання стосуються кризового реагування та захисту громадян України за кордоном. "
        "Джерела: Закон України «Про дипломатичну службу», Постанова КМУ про порядок "
        "надання матеріальної допомоги громадянам України за кордоном, "
        "Віденська конвенція про консульські зносини (1963)."
    ),
}

# Для питань про ЄС (Угода про асоціацію) — додаткова підказка з реальними джерелами
EU_HINT = (
    "Це питання про інституції та історію Європейського Союзу. "
    "Джерела: Договір про Європейський Союз (Маастрихтський договір 1992), "
    "Договір про функціонування Європейського Союзу, Шенгенська угода 1985, "
    "Копенгагенські критерії (1993). Вкажи конкретний договір/акт як джерело."
)

SYSTEM_PROMPT = (
    "Ти — експерт з українського законодавства та міжнародного права для підготовки "
    "до тестування на посаду віцеконсула МЗС України. Твоє завдання — написати коротке "
    "пояснення до тестового питання, чому правильна відповідь є правильною, з посиланням "
    "на конкретну статтю (або пункт/частину) відповідного нормативного акта.\n\n"
    "ВАЖЛИВО: ref НІКОЛИ не має бути «не перевірено». Якщо в наданому фрагменті тексту "
    "немає потрібної норми — використай свої знання і вкажи РЕАЛЬНИЙ нормативний акт "
    "(закон, постанову, міжнародний договір, конвенцію), на якому ґрунтується правильна "
    "відповідь, з конкретною статтею/пунктом, якщо це можливо. Не вигадуй неіснуючих "
    "номерів статей — якщо точної статті не знаєш, вкажи назву акта без номера статті.\n\n"
    "Вимоги до відповіді:\n"
    "1. Поверни ТІЛЬКИ валідний JSON об'єкт без зайвого тексту, у форматі:\n"
    '   {"text": "пояснення українською, 1-3 речення", "ref": "Назва акта, стаття N"}\n'
    "2. text — стисле пояснення, чому правильна відповідь правильна. Не повторюй дослівно "
    "питання чи відповідь.\n"
    "3. ref — назва нормативного акта та конкретна стаття/пункт, на якій ґрунтується відповідь.\n"
    "4. Відповідь має бути українською мовою."
)


def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[«»\"'`.,;:!?()\-–—]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_llm_json(raw):
    if not raw:
        return None
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
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


def load_md_text(filename):
    path = os.path.join(MD_OUT, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4 :]
    return content.strip()


def extract_relevant(text, question, max_chars=9000):
    """Витягує релевантний фрагмент; якщо не знайдено — повертає більший початок."""
    if not text:
        return ""
    words = [w.lower() for w in re.findall(r"[А-Яа-яЇїІіЄєҐґ']{4,}", question)]
    words = [
        w
        for w in words
        if w
        not in (
            "який",
            "яка",
            "яке",
            "які",
            "скільки",
            "коли",
            "де",
            "ким",
            "чому",
            "як",
        )
    ]
    if not words:
        return text[:max_chars]
    sentences = re.split(r"(?<=[.!?])\s+(?=[А-ЯЇІЄҐ])", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]
    best = None
    best_score = 0
    for s in sentences:
        score = sum(1 for w in words if w in s.lower())
        if score > best_score:
            best_score = score
            best = s
    if best and best_score >= 2:
        idx = text.find(best)
        start = max(0, idx - 2000)
        end = min(len(text), idx + len(best) + 3500)
        return text[start:end]
    return text[:max_chars]


def gen_for_question(question, correct, section_title, act_text, act_name, hint):
    user = f"Розділ (нормативний акт): {section_title}\n\n"
    user += f"Питання: {question}\n\n"
    user += f"Правильна відповідь: {correct}\n\n"
    if act_text:
        user += (
            f"Фрагмент тексту акта (використовуй його для точного посилання на статтю):\n"
            f"--- ПОЧАТОК ФРАГМЕНТА ---\n{act_text}\n--- КІНЕЦЬ ФРАГМЕНТА ---\n\n"
        )
    elif act_name:
        user += f"Акт, на який слід посилатися: {act_name}\n\n"
    if hint:
        user += f"Додаткова підказка: {hint}\n\n"
    user += "Напиши пояснення та посилання на джерело у форматі JSON."
    for attempt in range(3):
        provider, out = chat_fallback(
            SYSTEM_PROMPT, user, chain=CHAIN, temperature=0.2, max_tokens=500
        )
        if out and not out.startswith("[ERROR"):
            parsed = parse_llm_json(out)
            if parsed:
                return parsed
        time.sleep(2)
    return None


def main():
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)

    state = {}
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            state = json.load(f)
    done = state.get("done", {})

    md_cache = {}
    fixed = 0
    failed = []

    for sec in bank["sections"]:
        sec_id = sec["id"]
        sec_title = sec["title"]

        act_name = None
        act_text = None
        hint = None
        if sec_id in SECTION_MD:
            fname, act_name = SECTION_MD[sec_id]
            if fname not in md_cache:
                md_cache[fname] = load_md_text(fname)
            act_text = md_cache[fname]
        elif sec_id in SECTION_HINT:
            hint = SECTION_HINT[sec_id]
        if sec_id == "uhoda-pro-asotsiatsiiu-mizh-ukrainoiu-z":
            hint = (hint or "") + " " + EU_HINT

        for q in sec["questions"]:
            qid = q["id"]
            ex = q.get("explain") or {}
            ref = ex.get("ref", "")
            # пропускаємо питання без проблеми
            if ref and "не перевірено" not in ref.lower():
                continue
            if done.get(qid):
                continue

            relevant = extract_relevant(act_text, q["question"]) if act_text else None
            explain = gen_for_question(
                q["question"], q.get("correct", ""), sec_title, relevant, act_name, hint
            )

            ok = False
            if explain and isinstance(explain, dict):
                t = explain.get("text", "")
                r = explain.get("ref", "")
                if (
                    isinstance(t, str)
                    and len(t.strip()) >= 20
                    and isinstance(r, str)
                    and r.strip()
                    and "не перевірено" not in r.lower()
                ):
                    ok = True

            if ok:
                q["explain"] = explain
                fixed += 1
                done[qid] = True
            else:
                failed.append((qid, explain))
                done[qid] = False

            if fixed % 5 == 0:
                with open(BANK_PATH, "w", encoding="utf-8") as f:
                    json.dump(bank, f, ensure_ascii=False, indent=2)
                with open(STATE_PATH, "w", encoding="utf-8") as f:
                    json.dump({"done": done}, f, ensure_ascii=False, indent=2)

    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump({"done": done}, f, ensure_ascii=False, indent=2)

    print(f"FIXED: {fixed}")
    print(f"FAILED: {len(failed)}")
    for qid, ex in failed[:20]:
        print("  ", qid, "->", ex)


if __name__ == "__main__":
    main()
