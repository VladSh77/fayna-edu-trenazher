#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Заповнює поле explain: {text, ref} для ВСІХ питань банку mzs-2026.json,
використовуючи завантажені тексти нормативних актів (MD у docs-sorter),
щоб пояснення містили ТОЧНІ статті/пункти з цих текстів.

Джерела:
  - Для розділу krainoznavstvo-polsha: використовує вже наявне поле quote
    (дослівна цитата з конспекту) як text, ref = "Конспект країнознавства Польщі".
  - Для решти розділів: генерація через LLM (team_llm.chat_fallback) з передачею
    релевантного фрагмента тексту відповідного акта, щоб LLM цитував точну статтю.

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
STATE_PATH = os.path.join(ROOT, "scripts", ".explain_state_v2.json")
KRAJOZNAWSTWO_REF = "Конспект країнознавства Польщі"

# База знань docs-sorter (MD-файли завантажених актів)
MD_OUT = "/Users/kobzar/Library/Mobile Documents/com~apple~CloudDocs/📚 База знань/_MD"

# Підключення team_llm (docs-sorter)
sys.path.insert(0, "/Users/kobzar/projects/firm/platforms/docs-sorter")
from team_llm import chat_fallback  # noqa: E402

# Порядок провайдерів: спочатку ті, що реально працюють (openai), потім fallback.
# deepseek може бути без балансу (402), glm іноді повертає порожній рядок.
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

# --- Мапа: id розділу банку -> (MD-файл, назва акта для ref) ---
# Якщо MD-файл відсутній — генерація без тексту (LLM за знаннями).
SECTION_MD = {
    "zakon-ukrainy-pro-hromadianstvo-ukrainy": (
        "zakon-pro-hromadianstvo.md",
        "Закон України «Про громадянство України»",
    ),
    "hromadianstvo-ukrainy": (
        "zakon-pro-hromadianstvo.md",
        "Закон України «Про громадянство України»",
    ),
    "zakon-ukrainy-pro-dyplomatychnu-sluzhbu": (
        "zakon-pro-dyplomatychnu-sluzhbu.md",
        "Закон України «Про дипломатичну службу»",
    ),
    "uhoda-pro-asotsiatsiiu-mizh-ukrainoiu-z": (
        "uhoda-pro-asotsiatsiiu-ukraina-yes.md",
        "Угода про асоціацію між Україною та ЄС",
    ),
    "pravyla-oformlennia-viz-dlia-v-izdu-v": (
        "pravyla-oformlennia-viz.md",
        "Постанова КМУ від 01.03.2017 № 118 «Про затвердження Правил оформлення віз»",
    ),
    "oformlennia-vizovykh-dokumentiv": (
        "pravyla-oformlennia-viz.md",
        "Постанова КМУ від 01.03.2017 № 118 «Про затвердження Правил оформлення віз»",
    ),
    "zakon-ukrainy-pro-derzhavnu": (
        "zakon-pro-derzhavnu-reiestratsiiu-aktiv-tsyvilnoho-stanu.md",
        "Закон України «Про державну реєстрацію актів цивільного стану»",
    ),
    "reiestratsiia-aktiv-tsyvilnoho-stanu": (
        "zakon-pro-derzhavnu-reiestratsiiu-aktiv-tsyvilnoho-stanu.md",
        "Закон України «Про державну реєстрацію актів цивільного стану»",
    ),
    "zakon-ukrainy-pro-notariat": (
        "zakon-pro-notariat.md",
        "Закон України «Про нотаріат»",
    ),
    "vchynennia-notarialnykh-dii": (
        "zakon-pro-notariat.md",
        "Закон України «Про нотаріат»",
    ),
    "videnska-konventsiia-pro-dyplomatychni": (
        "videnska-konventsiia-dyplomatychni-znosyny.md",
        "Віденська конвенція про дипломатичні зносини (1961)",
    ),
    "videnska-konventsiia-pro-konsulski": (
        "videnska-konventsiia-konsulski-znosyny.md",
        "Віденська конвенція про консульські зносини (1963)",
    ),
    "postanova-kabinetu-ministriv-ukrainy-2": (
        "postanova-kmu-55-dokumentuvannia.md",
        "Постанова КМУ від 17.01.2018 № 55 «Деякі питання документування управлінської діяльності»",
    ),
    "zakon-ukrainy-pro-vybory-prezydenta": (
        "zakon-pro-vybory-prezydenta.md",
        "Закон України «Про вибори Президента України» (втратив чинність, замінений Виборчим кодексом України)",
    ),
    "zakon-ukrainy-pro-derzhavnyi-reiestr": (
        "zakon-pro-derzhavnyi-reiestr-vyborciv.md",
        "Закон України «Про Державний реєстр виборців»",
    ),
    "vykonannia-zakonu-ukrainy-pro": (
        "zakon-pro-derzhavnyi-reiestr-vyborciv.md",
        "Закон України «Про Державний реєстр виборців»",
    ),
    "zakon-ukrainy-pro-vybory-narodnykh": (
        "zakon-pro-vybory-narodnykh-deputativ.md",
        "Закон України «Про вибори народних депутатів України» (втратив чинність, замінений Виборчим кодексом України)",
    ),
    "zakon-ukrainy-pro-pravovyi-status": (
        "zakon-pro-pravovyi-status-inozemtsiv.md",
        "Закон України «Про правовий статус іноземців та осіб без громадянства»",
    ),
    "zakon-ukrainy-pro-mizhnarodni-dohovory": (
        "zakon-pro-mizhnarodni-dohovory.md",
        "Закон України «Про міжнародні договори України»",
    ),
    "postanova-kabinetu-ministriv-pro": (
        "rehlament-verkhovnoi-rady.md",
        "Закон України «Про Регламент Верховної Ради України»",
    ),
    "postanova-kabinetu-ministriv-pro-2": (
        "rehlament-kabinetu-ministriv.md",
        "Постанова КМУ від 18.07.2007 № 950 «Про затвердження Регламенту Кабінету Міністрів України»",
    ),
    "zakon-ukrainy-pro-upravlinnia-ob": (
        "zakon-pro-upravlinnia-obiektamy-derzhavnoi-vlasnosti.md",
        "Закон України «Про управління об'єктами державної власності»",
    ),
    "polozhennia-pro-ministerstvo": (
        "polozhennia-pro-mzs.md",
        "Постанова КМУ від 30.03.2016 № 281 «Про затвердження Положення про Міністерство закордонних справ України»",
    ),
    "videnska-konventsiia-pro-pravo": (
        "videnska-konventsiia-pravo-mizhnarodnykh-dohovoriv.md",
        "Віденська конвенція про право міжнародних договорів (1969)",
    ),
    "nakaz-derzhavnoho-kaznacheistva-ukrainy": (
        "nakaz-kaznacheistva-130-typovi-formy-zapasiv.md",
        "Наказ Державного казначейства України від 18.12.2000 № 130 «Про затвердження типових форм обліку та списання запасів бюджетних установ»",
    ),
    "nakaz-ministerstva-finansiv-ukrainy-vid": (
        "nakaz-minfinu-879-inventaryzatsiia.md",
        "Наказ Мінфіну від 02.09.2014 № 879 «Про затвердження Положення про інвентаризацію активів та зобов'язань»",
    ),
    "postanova-kabinetu-ministriv-ukrainy": (
        "postanova-kmu-645.md",
        "Постанова КМУ від 17.07.2019 № 645",
    ),
    "zakon-ukrainy-pro-elektronni-dokumenty": (
        "zakon-pro-elektronni-dokumenty.md",
        "Закон України «Про електронні документи та електронний документообіг»",
    ),
}

# Розділи без прямого MD-файла (тематичні) — генерація за знаннями LLM
# з підказкою про відповідний акт.
SECTION_HINT = {
    "pasportni-pytannia": "Питання стосуються паспортних документів громадян України (Закон України «Про Єдиний державний демографічний реєстр», Постанова КМУ про паспорт громадянина України).",
    "zakhyst-prav-ta-interesiv-hromadian": "Питання стосуються захисту прав та інтересів громадян України за кордоном (Закон України «Про дипломатичну службу», Віденська конвенція про консульські зносини).",
    "kryzove-reahuvannia": "Питання стосуються кризового реагування та захисту громадян України за кордоном у надзвичайних ситуаціях.",
    "zasvidchennia-ofitsiinykh-dokumentiv": "Питання стосуються засвідчення офіційних документів (апостиль та легалізація) — Гаазька конвенція 1961 року, Закон України «Про міжнародні договори України».",
    "vytrebuvannia-dokumentiv": "Питання стосуються витребування документів (Закон України «Про нотаріат», консульські функції).",
    "orhanizatsiia-ta-provedennia-vyiznykh": "Питання стосуються організації та проведення виїзних консульських обслуговувань.",
    "pryznachennia-diialnist-i-prypynennia": "Питання стосуються призначення, діяльності і припинення повноважень нештатних (почесних) консулів (Віденська конвенція про консульські зносини).",
    "konsulskyi-zbir-ukrainy-ta-instruktsiia": "Питання стосуються Консульського збору України та Інструкції про порядок справляння сум консульського збору.",
}

SYSTEM_PROMPT = (
    "Ти — експерт з українського законодавства та міжнародного права для підготовки "
    "до тестування на посаду віцеконсула МЗС України. Твоє завдання — написати коротке "
    "пояснення до тестового питання, чому правильна відповідь є правильною, з посиланням "
    "на конкретну статтю (або пункт/частину) відповідного нормативного акта.\n\n"
    "Тобі буде надано фрагмент тексту відповідного нормативного акта. Використовуй ЙОГО "
    "для точного посилання на статтю/пункт. Не вигадуй номери статей, яких немає в наданому тексті.\n\n"
    "Вимоги до відповіді:\n"
    "1. Поверни ТІЛЬКИ валідний JSON об'єкт без зайвого тексту, у форматі:\n"
    '   {"text": "пояснення українською, 1-3 речення", "ref": "Назва акта, стаття N"}\n'
    "2. text — стисле пояснення, чому правильна відповідь правильна. Не повторюй дослівно "
    "питання чи відповідь.\n"
    "3. ref — назва нормативного акта та конкретна стаття/пункт, на якій ґрунтується відповідь. "
    "Формат: «Закон України «Про громадянство України», ст. 3» або "
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
    nt = normalize_text(text)
    if nt == normalize_text(question) or nt == normalize_text(correct):
        return False, "text_duplicates_q_or_a"
    if nt in section_existing_texts:
        return False, "text_duplicates_section"
    return True, None


def parse_llm_json(raw):
    """Витягує JSON з відповіді LLM (стійкий до markdown-обгорток)."""
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


def load_md_text(filename):
    """Завантажує текст MD-файла акта, прибираючи frontmatter."""
    path = os.path.join(MD_OUT, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # прибрати YAML frontmatter (--- ... ---)
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            content = content[end + 4 :]
    return content.strip()


def extract_relevant(text, question, max_chars=6000):
    """
    Витягує релевантний фрагмент тексту акта для питання.
    Шукає речення зі словами питання; якщо не знайдено — повертає початок тексту.
    """
    if not text:
        return ""
    # ключові слова з питання (іменники/слова довші 4 символів)
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
    # розбиваємо текст на речення (текст може бути одним великим рядком)
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
        # повертаємо фрагмент навколо знайденого речення
        idx = text.find(best)
        start = max(0, idx - 1500)
        end = min(len(text), idx + len(best) + 2500)
        return text[start:end]
    return text[:max_chars]


def gen_for_question(question, correct, section_title, act_text, act_name, hint):
    """Генерує пояснення через LLM. Повертає explain dict або None."""
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
    data = load_bank()
    state = load_state()
    done = state.get("done", {})

    # кеш текстів актів
    md_cache = {}

    total = 0
    generated = 0
    skipped = 0
    failed = []

    for sec in data["sections"]:
        sec_id = sec["id"]
        sec_title = sec["title"]

        # визначити акт для розділу
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

        section_existing_texts = set()
        for q in sec["questions"]:
            if q.get("explain") and q["explain"].get("text"):
                section_existing_texts.add(normalize_text(q["explain"]["text"]))

        for q in sec["questions"]:
            qid = q["id"]
            total += 1
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

            # Інакше — генерація через LLM з текстом акта
            if explain is None:
                relevant = (
                    extract_relevant(act_text, q["question"]) if act_text else None
                )
                explain = gen_for_question(
                    q["question"], correct, sec_title, relevant, act_name, hint
                )

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
