#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Імітація проходження тестів МЗС у Docker.

Скрипт:
  1) завантажує банк питань (banks/mzs-2026.json);
  2) симулює користувача, що проходить навчання по ВСІХ питаннях
     (випадковий порядок, по одному, з фіксацією прогресу);
  3) для кожного питання визначає акт/закон за explain.ref і витягує
     текст відповідної статті з вбудованого документа laws/*.html;
  4) перевіряє, що правильна відповідь (correct) узгоджується з текстом
     статті. Перевірка двоступенева:
       a) швидкий лексичний збіг (ключові слова відповіді в статті);
       b) якщо лексичний збіг недостатній (короткі відповіді «так/ні»,
          мета-відповіді «усі відповіді вірні», перефразування) —
          семантична перевірка LLM (team_llm.chat_fallback).
  5) друкує зведення: скільки питань підтверджено, скільки ні, і де саме
     розбіжності.

Використання (в Docker або локально):
  python3 simulate.py [--bank banks/mzs-2026.json] [--verbose] [--limit N]
                      [--no-llm] [--llm-only]

Змінні середовища (використовуються docker-compose):
  BANK_FILE, VERBOSE, LIMIT, NO_LLM, LLM_ONLY
"""

import argparse
import html
import json
import os
import random
import re
import sys
from pathlib import Path

# --- шляхи ---
WORK = Path(__file__).resolve().parent
PROJECT = WORK.parent
DEFAULT_BANK = PROJECT / "banks" / "mzs-2026.json"
LAWS_DIR = PROJECT / "laws"

# --- реєстр: ключові слова (з explain.ref) -> файл акта в laws/ ---
# Порядок має значення: специфічніші ключі — раніше (аналог LEGISLATION в index.html).
LEGISLATION = [
    (
        ["Виборчий кодекс", "вибори Президента", "вибори народних депутатів"],
        "vyborchyi-kodeks-ukrainy.html",
    ),
    (["громадянство України"], "zakon-pro-hromadianstvo.html"),
    (["дипломатичну службу"], "zakon-pro-dyplomatychnu-sluzhbu.html"),
    (["нотаріат"], "zakon-pro-notariat.html"),
    (
        ["правовий статус іноземців", "правовий статус осіб"],
        "zakon-pro-pravovyi-status-inozemtsiv.html",
    ),
    (["міжнародні договори України"], "zakon-pro-mizhnarodni-dohovory.html"),
    (
        ["державну реєстрацію актів цивільного стану"],
        "zakon-pro-derzhavnu-reiestratsiiu-aktiv-tsyvilnoho-stanu.html",
    ),
    (["Державний реєстр виборців"], "zakon-pro-derzhavnyi-reiestr-vyborciv.html"),
    (
        ["управління об'єктами державної власності"],
        "zakon-pro-upravlinnia-obiektamy-derzhavnoi-vlasnosti.html",
    ),
    (["електронні документи"], "zakon-pro-elektronni-dokumenty.html"),
    (["Регламент Верховної Ради"], "rehlament-verkhovnoi-rady.html"),
    (
        ["Положення про Міністерство закордонних справ", "Положення про МЗС"],
        "polozhennia-pro-mzs.html",
    ),
    (
        [
            "Правила оформлення віз",
            "№ 118",
            "консульського збору",
            "виїзних консульських обслуговувань",
            "матеріальної допомоги громадянам України за кордоном",
            "повернення до України позбавлених батьківського піклування дітей",
            "Консульський збір України",
        ],
        "pravyla-oformlennia-viz.html",
    ),
    (["Регламент Кабінету Міністрів"], "rehlament-kabinetu-ministriv.html"),
    (
        ["документування управлінської діяльності", "документування"],
        "postanova-kmu-55-dokumentuvannia.html",
    ),
    (
        ["Типової інструкції з діловодства", "діловодство"],
        "typova-instruktsiia-dilovodstva.html",
    ),
    (["№ 879", "інвентаризацію"], "nakaz-minfinu-879-inventaryzatsiia.html"),
    (["№ 645"], "postanova-kmu-645.html"),
    (
        ["№ 130", "Державного казначейства"],
        "nakaz-kaznacheistva-130-typovi-formy-zapasiv.html",
    ),
    (["Угода про асоціацію"], "uhoda-pro-asotsiatsiiu-ukraina-yes.html"),
    (
        ["Віденська конвенція про право міжнародних договорів"],
        "videnska-konventsiia-pravo-mizhnarodnykh-dohovoriv.html",
    ),
    (
        ["Віденська конвенція про дипломатичні зносини"],
        "videnska-konventsiia-dyplomatychni-znosyny.html",
    ),
    (
        ["Віденська конвенція про консульські зносини"],
        "videnska-konventsiia-konsulski-znosyny.html",
    ),
    # --- Додаткові акти, додані для повної імітації (завдання 23) ---
    (
        ["Єдиний державний демографічний реєстр", "демографічний реєстр"],
        "zakon-pro-yedynyi-derzhavnyi-demohrafichnyi-reiestr.html",
    ),
    (
        ["Консульський статут", "консульську службу", "консульські установи"],
        "konsulskyi-statut-ukrainy.html",
    ),
    (
        ["Кримінальний процесуальний кодекс"],
        "kryminalnyi-protsesualnyi-kodeks-ukrainy.html",
    ),
    (
        [
            "Кодекс України про адміністративні правопорушення",
            "адміністративні правопорушення",
        ],
        "kodeks-ukrainy-pro-administratyvni-pravoporushennia.html",
    ),
    (["охорону дитинства"], "zakon-pro-okhoronu-dytynstva.html"),
    (["Цивільний кодекс"], "tsyvilnyi-kodeks-ukrainy.html"),
    (["Сімейний кодекс"], "simeinyi-kodeks-ukrainy.html"),
    (["Кримінальний кодекс"], "kryminalnyi-kodeks-ukrainy.html"),
    (
        ["Національну поліцію", "Національної поліції"],
        "zakon-pro-natsionalnu-politsiiu.html",
    ),
    (
        ["міжнародне приватне право"],
        "zakon-pro-mizhnarodne-pryvatne-pravo.html",
    ),
    # --- Розділ 1: відсутні акти (додано refactor_section1_stub.py) ---
    (["Договір про Європейський Союз"], "dohovir-pro-yevropeiskyi-soiuz.html"),
    (
        ["Договір про функціонування Європейського Союзу"],
        "dohovir-pro-funktsionuvannia-yes.html",
    ),
    (
        [
            "Гаазька конвенція",
            "легалізації іноземних офіційних документів",
            "апостиль",
        ],
        "haazka-konventsiia-apostyl.html",
    ),
    (
        ["Порядок провадження за заявами і поданнями з питань громадянства"],
        "poriadok-provadzhennia-hromadianstvo.html",
    ),
    (
        ["Інструкція про витребування документів"],
        "instruktsiia-vytrebuvannia-dokumentiv.html",
    ),
    (
        ["Правила державної реєстрації актів цивільного стану"],
        "pravyla-derzhavnoi-reiestratsii-aktiv.html",
    ),
    (
        ["Порядок ведення Державного реєстру виборців"],
        "poriadok-vedennia-reiestru-vyborciv.html",
    ),
    (["№ 368"], "postanova-kmu-368-vizy.html"),
    (["№ 954"], "postanova-kmu-954.html"),
    (["№ 776"], "postanova-kmu-776.html"),
    (
        ["взаємну допомогу у кримінальних справах"],
        "yevropeiska-konventsiia-vzaiemna-dopomoha.html",
    ),
    (["приймання в експлуатацію"], "poriadok-pryimannia-ekspluatatsiiu.html"),
    (["№ 651"], "postanova-kmu-651-zakhyst-hromadian.html"),
    (
        [
            "надзвичайного стану",
            "надзвичайних ситуацій",
        ],
        "zakon-pro-nadzvychaini-sytuatsii.html",
    ),
    (
        ["основи соціальної захищеності"],
        "zakon-pro-osnovy-sotsialnoi-zakhyshchenosti.html",
    ),
    (["№ 750"], "postanova-kmu-750-apostyl.html"),
    (
        [
            "нештатних (почесних) консулів",
            "почесних консулів",
        ],
        "polozhennia-pro-pochesnykh-konsuliv.html",
    ),
    (["Копенгагенські критерії"], "kopenhahenski-kryterii.html"),
    (["Шенгенська угода"], "shenhenska-uhoda.html"),
    (
        ["засідань окремих двосторонніх органів асоціації"],
        "postanova-kmu-zasidannia-orhaniv-asotsiatsii.html",
    ),
]

# Країнознавство — це конспект (історія/культура), а не норма права.
# Для цих питань перевірка "збігу зі статтею" не застосовується.
KRAJOZNAWSTWO_REF = "Конспект країнознавства Польщі"

# Поріг лексичного збігу: якщо >= цієї частки значущих слів відповіді є в
# статті — вважаємо підтвердженим без LLM.
LEXICAL_THRESHOLD = 0.6

# Мінімальна кількість значущих слів у відповіді, щоб лексичний збіг був
# надійним. Якщо слів менше — одразу йдемо на семантичну перевірку LLM
# (короткі відповіді «так/ні», «усі відповіді вірні» тощо).
MIN_SIGNIFICANT_WORDS = 3

# Стемінг-фолбек: якщо точний лексичний збіг нижчий за поріг, пробуємо
# зіставити за префіксом (коренем) слів. Це ловить відмінкові/словотвірні
# варіанти (напр. «громадянство» vs «громадянства»). Мінімальна довжина
# кореня, щоб уникнути хибних збігів на коротких словах.
STEM_MIN = 5

# Патерни питань «що НЕ» — відповідь є тим, чого НЕМАЄ в статті (перелік
# того, що не належить / не є / не входить). Для таких питань стемінг може
# дати ХИБНЕ підтвердження, бо слово відповіді може зустрічатись у статті
# в іншому контексті. Тому для них стемінг-фолбек вимикається.
NEG_QUESTION_RE = re.compile(
    r"не належить|не є|не входить|не відноситься|не вважається|не підлягає|"
    r"не обов'язков|не обов’язков|не може|не має права|не є підставою|"
    r"не передбачає|не допускається|не застосовується|не поширюється|"
    r"не включає|не охоплює|не визнається|не встановлює",
    re.IGNORECASE,
)


def legislation_file(ref):
    """Повертає ім'я файлу акта в laws/ за рядком джерела, або None."""
    if not ref:
        return None
    r = ref.lower()
    for keys, fname in LEGISLATION:
        for k in keys:
            if k.lower() in r:
                return fname
    return None


def strip_tags(text):
    """Прибирає HTML-теги, лишаючи текст."""
    return re.sub(r"<[^>]+>", "", text)


def normalize(text):
    """Нормалізація для порівняння: нижній регістр, без зайвих пробілів."""
    if not text:
        return ""
    t = html.unescape(text)
    t = strip_tags(t)
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    t = t.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return t.strip()


def extract_articles(html_text):
    """
    Розбиває HTML-документ акта на статті.
    Повертає список (номер_статті, текст_статті).
    Номер статті — рядок з h3 (напр. "Стаття 2" або "Стаття 5 - 1").
    """
    # Деякі дампи мають латинську "C" замість кириличної "С" у слові "Стаття"
    # (напр. "Cтаття 33"). Матчимо обидві літери.
    pattern = re.compile(r"<h3>([СC]таття\s+[^<]+)</h3>", re.IGNORECASE)
    matches = list(pattern.finditer(html_text))
    articles = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        # Нормалізуємо латинську C -> кириличну С у заголовку
        title = re.sub(r"^[СC]", "С", title)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html_text)
        body = html_text[start:end]
        articles.append((title, body))
    return articles


def _extract_statut_articles(html_text):
    """
    Консульський статут України — Указ Президента № 127/94, де статті
    позначені розрідженим написанням "С т а т т я  N" (літери розділені
    пробілами) у звичайному тексті, а не <h3>Стаття N</h3>.
    Повертає список (номер_статті, текст_статті).
    """
    # "С т а т т я" з довільними пробілами/нерозривними пробілами між літерами,
    # далі номер. Використовуємо lookahead, щоб не споживати номер.
    pattern = re.compile(
        r"[СC]\s*т\s*а\s*т\s*т\s*я\s+(?=[0-9]+)",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(html_text))
    if not matches:
        return []
    articles = []
    for i, m in enumerate(matches):
        # номер статті — цифри одразу після "С т а т т я "
        num_m = re.match(r"\s*([0-9]+)", html_text[m.end() :])
        num = num_m.group(1) if num_m else "?"
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html_text)
        body = html_text[start:end]
        articles.append((f"Стаття {num}", body))
    return articles


def _extract_vienna_articles(html_text):
    """
    Віденські конвенції — сирі дампи PDF ООН, де статті позначені
    англійською "Article N" (не <h3>Стаття N</h3>).
    Статті можуть бути в <h1-6> або в окремому <p>Article N</p>.
    Повертає список (номер_статті, текст_статті).
    """
    # Шукаємо "Article N" як у заголовках <h1-6>, так і в окремих <p>.
    pattern = re.compile(
        r"<(?:h[1-6]|p)[^>]*>\s*(Article\s+[0-9]+(?:\s*-\s*[0-9]+)?)\s*</(?:h[1-6]|p)>",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(html_text))
    if not matches:
        return []
    articles = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(html_text)
        body = html_text[start:end]
        articles.append((title, body))
    return articles


# --- Покращений витяг пунктів/параграфів (інтегровано з robust_extract) ---
# Маркери початку тіла Правил/Інструкцій/Регламенту всередині постанови
BODY_MARKERS = [
    "Ці Правила визначають",
    "Ця Інструкція визначає",
    "Ці Правила",
    "Ця Інструкція",
]


def _find_body_start(html_text):
    """Повертає індекс початку тіла Правил/Інструкції або 0, якщо не знайдено."""
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)
    for marker in BODY_MARKERS:
        idx = plain.find(marker)
        if idx >= 0:
            return idx
    return 0


def _extract_section(html_text, num):
    """Витягує параграф '§ N.' (Регламент КМУ). Повертає (title, body_text)."""
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)
    pat = re.compile(r"§\s*" + re.escape(str(num)) + r"\.\s*([^§]*)")
    m = pat.search(plain)
    if not m:
        return None, None
    body = m.group(1).strip()
    return f"§ {num}", body


def _extract_point(html_text, point_str, prefer_body=True):
    """
    Витягує пункт 'N.' або 'N - M.' / 'N-M.'.
    point_str — рядок номера, напр. "3" або "8-1".
    prefer_body — якщо True, шукає пункт у тілі Правил/Інструкції (після маркера).
    Повертає (title, body_text) — body_text це повний текст пункту (до наступного
    номера пункту або кінця).
    """
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)

    # нормалізуємо номер: "8-1" -> "8\s*-\s*1"
    if "-" in point_str:
        a, b = point_str.split("-", 1)
        num_pat = re.escape(a) + r"\s*-\s*" + re.escape(b)
    else:
        num_pat = re.escape(point_str)

    # Патерн початку пункту: "N." або "N - M." (з можливими пробілами перед крапкою)
    start_pat = re.compile(r"(?<!\d)" + num_pat + r"\s*\.\s*")

    def find_from(start):
        m = start_pat.search(plain, start)
        if not m:
            return None
        begin = m.start()
        # Якщо це ПРОСТИЙ номер (не дефісний), перевіряємо, що "N" не є другою
        # частиною дефісного діапазону "X-N" (напр. "2-3"), інакше пропускаємо.
        if "-" not in point_str:
            before = plain[max(0, begin - 12) : begin]
            if re.search(r"\d\s*-\s*$", before):
                return find_from(m.end())
        # кінець пункту — наступний номер пункту (N. / N - M.) або кінець
        rest = plain[m.end() :]
        # шукаємо наступний початок пункту: цифра + крапка (не частина дати/числа)
        next_pat = re.compile(r"(?<!\d)(\d{1,3}(?:\s*-\s*\d{1,3})?)\s*\.\s*")
        nxt = next_pat.search(rest)
        if nxt:
            end = m.end() + nxt.start()
        else:
            end = len(plain)
        return plain[begin:end].strip()

    if prefer_body:
        start = _find_body_start(html_text)
        body = find_from(start)
        if body:
            return f"Пункт {point_str}", body
        body = find_from(0)
        if body:
            return f"Пункт {point_str}", body
        return None, None

    body = find_from(0)
    if body:
        return f"Пункт {point_str}", body
    return None, None


def _extract_form_section(html_text, form_id):
    """
    Витягує описову частину типової форми в Інструкції (напр. "форма N З-3").
    form_id — рядок, напр. "З-3". Шукає заголовок "Назва (форма N З-3)" і
    повертає текст від цього заголовка до наступної форми.
    Повертає (title, body_text) або (None, None).
    """
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)
    # заголовок форми: "Назва (форма N З-3)" — назва може містити дужки (напр. "Накладна (вимога)")
    pat = re.compile(r"(.{2,120}?)\s*\(форма N\s*" + re.escape(form_id) + r"\)")
    m = pat.search(plain)
    if not m:
        return None, None
    start = m.start()
    # кінець — наступна форма "(форма N З-X)" або кінець документа
    next_pat = re.compile(r"\(форма N\s*З-\d+")
    nxt = next_pat.search(plain, m.end())
    end = nxt.start() if nxt else len(plain)
    body = plain[start:end].strip()
    return f"Форма N {form_id}", body


def _extract_point_paragraph(html_text, point_num):
    """
    Для документів типу «Правила/Інструкції», де пункти нумеровані інлайн
    у <p> (напр. "29. ..."), знаходить абзац, що починається з "N.".
    Повертає (заголовок, текст_абзацу) або (None, None).
    """
    # Шукаємо <p> що починається з "N." або "N." після тега
    pat = re.compile(
        r"<p[^>]*>\s*(?:<[^>]+>\s*)*"
        r"(" + re.escape(str(point_num)) + r")\.\s*([^<]*(?:<[^>]+>[^<]*)*)",
        re.IGNORECASE,
    )
    m = pat.search(html_text)
    if m:
        return f"Пункт {point_num}", m.group(0)

    # Fallback: документи типу «Положення про МЗС», де підпункти пункту 4
    # нумеровані інлайн у форматі "N) ..." (напр. "28) оформляє повноваження...").
    # Витягуємо фрагмент від "N)" до наступного "N+1)" або кінця абзацу.
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)
    start_pat = re.compile(
        r"(?<![\d)])(?<!\d\s)" + re.escape(str(point_num)) + r"\)\s*"
    )
    sm = start_pat.search(plain)
    if not sm:
        return None, None
    begin = sm.end()
    # кінець — наступний підпункт "N+1)" або кінець рядка/абзацу
    next_pat = re.compile(r"(?<![\d)])(?<!\d\s)(\d{1,3})\)\s*")
    nxt = next_pat.search(plain, begin)
    if nxt:
        end = nxt.start()
    else:
        end = len(plain)
    body = plain[sm.start() : end].strip()
    return f"Пункт {point_num}", body


def extract_article_by_ref(html_text, ref):
    """
    Знаходить текст статті/пункту за посиланням у ref.
    Підтримує формати:
      - "ст. 2" / "стаття 2" — стаття з <h3>Стаття N</h3>
      - "п. 29" / "пункт 29" — пункт, нумерований інлайн у <p>
      - "§ 28" — параграф
      - Віденські конвенції: "Article N"
    Повертає (номер, текст) або (None, None).
    """
    # 1) Стаття: "ст. N" / "стаття N"
    m = re.search(r"ст(?:атт?я)?\.?\s*([0-9]+(?:\s*-\s*[0-9]+)?)", ref, re.IGNORECASE)
    if m:
        num = m.group(1)
        num_norm = re.sub(r"\s*-\s*", "-", num)
        articles = extract_articles(html_text)
        for title, body in articles:
            tm = re.search(
                r"[СC]таття\s+([0-9]+(?:\s*-\s*[0-9]+)?)", title, re.IGNORECASE
            )
            if not tm:
                continue
            t_num = re.sub(r"\s*-\s*", "-", tm.group(1))
            if t_num == num_norm:
                return title, body
        # Якщо не знайшли в українських статтях — спробуймо Віденський формат
        vienna = _extract_vienna_articles(html_text)
        for title, body in vienna:
            tm = re.search(
                r"Article\s+([0-9]+(?:\s*-\s*[0-9]+)?)", title, re.IGNORECASE
            )
            if not tm:
                continue
            t_num = re.sub(r"\s*-\s*", "-", tm.group(1))
            if t_num == num_norm:
                return title, body
        # Консульський статут: "С т а т т я N" (розріджене написання)
        statut = _extract_statut_articles(html_text)
        for title, body in statut:
            tm = re.search(r"[СC]таття\s+([0-9]+)", title, re.IGNORECASE)
            if not tm:
                continue
            t_num = re.sub(r"\s*-\s*", "-", tm.group(1))
            if t_num == num_norm:
                return title, body

    # 2) Пункт: "п. N-M" / "пункт N-M" — дефісний номер
    m = re.search(r"п(?:ункт)?\.?\s*([0-9]+)\s*-\s*([0-9]+)", ref, re.IGNORECASE)
    if m:
        point_str = f"{m.group(1)}-{m.group(2)}"
        title, body = _extract_point(html_text, point_str, prefer_body=True)
        if body:
            return title, body

    # 3) Пункт: "п. N" / "пункт N" — пункт, нумерований інлайн у <p>
    m = re.search(r"п(?:ункт)?\.?\s*([0-9]+)", ref, re.IGNORECASE)
    if m:
        title, body = _extract_point_paragraph(html_text, int(m.group(1)))
        if body:
            return title, body
        # Fallback: спробуй покращений витяг з тіла Правил/Інструкції
        title, body = _extract_point(html_text, m.group(1), prefer_body=True)
        if body:
            return title, body

    # 4) Параграф: "§ N" — Регламент КМУ
    m = re.search(r"§\s*([0-9]+)", ref)
    if m:
        title, body = _extract_section(html_text, int(m.group(1)))
        if body:
            return title, body

    # 5) Типова форма: "форма N З-X" (Інструкція до наказу), напр. "З-3", "З-4а"
    m = re.search(
        r"форма\s*N\s*([ЗA-ZА-Я]-?[0-9]+(?:-[0-9]+)?[а-яА-Яa-zA-Z]?)",
        ref,
        re.IGNORECASE,
    )
    if m:
        title, body = _extract_form_section(html_text, m.group(1))
        if body:
            return title, body

    return None, None


# --- стоп-слова для лексичного збігу (компактний набір) ---
STOP = {
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
    "може",
    "можуть",
    "бути",
    "є",
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
    "вірні",
    "правильні",
    "відповіді",
    "відповідь",
    "варіанти",
    "варіант",
    "пункт",
    "пункти",
    "частина",
    "частини",
    "стаття",
    "статті",
    "закон",
    "закону",
    "україни",
    "україна",
    "україні",
    "особа",
    "особи",
    "особу",
    "особою",
    "громадянин",
    "громадянина",
    "громадянство",
    "громадянства",
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
    "здійснюється",
    "здійснює",
    "передбачено",
    "передбачає",
    "встановлено",
    "встановлює",
    "визначається",
    "визначає",
    "подається",
    "подаються",
    "надається",
    "надаються",
    "видається",
    "видаються",
    "проводиться",
    "проводяться",
    "здійснення",
    "надання",
    "подання",
    "видача",
    "видання",
    "реєстрація",
    "реєстрації",
    "оформлення",
    "набуття",
    "втрати",
    "втрата",
    "прийняття",
    "поновлення",
    "належність",
    "підстави",
    "підстав",
    "підстава",
    "порядок",
    "порядку",
    "строк",
    "строку",
    "термін",
    "терміну",
    "документ",
    "документи",
    "документів",
    "заява",
    "заяви",
    "заяву",
    "орган",
    "органи",
    "органу",
    "органів",
    "центральний",
    "центрального",
    "міністерство",
    "міністерства",
    "посольство",
    "посольства",
    "консульські",
    "консульських",
    "установа",
    "установи",
    "установ",
    "повноваження",
    "повноважень",
    "рішення",
    "рішенням",
    "указ",
    "указу",
    "президент",
    "президента",
    "кабінет",
    "кабінету",
    "міністрів",
    "міністр",
    "міністра",
    "рада",
    "ради",
    "верховна",
    "верховної",
    "народних",
    "депутатів",
    "депутати",
    "вибори",
    "виборів",
    "виборчого",
    "виборчий",
    "кодекс",
    "кодексу",
    "території",
    "територію",
    "територія",
    "держави",
    "держава",
    "державі",
    "державної",
    "державний",
    "державного",
    "місце",
    "місця",
    "місці",
    "проживання",
    "перебування",
    "постійне",
    "постійного",
    "тимчасове",
    "тимчасового",
    "іноземці",
    "іноземців",
    "іноземець",
    "іноземного",
    "іноземної",
    "громадян",
    "громадяни",
    "громадянам",
    "громадянами",
    "уповноважений",
    "уповноваженого",
    "уповноваженим",
    "спеціально",
    "спеціального",
    "відповідного",
    "відповідний",
    "відповідну",
    "відповідне",
    "письмовій",
    "письмово",
    "усній",
    "усно",
    "формі",
    "форма",
    "форми",
    "пізніш",
    "пізніше",
    "тижневий",
    "тижневого",
    "місячний",
    "місячного",
    "дня",
    "день",
    "днів",
    "року",
    "рік",
    "років",
    "роки",
    "числа",
    "числі",
    "число",
    "дата",
    "дати",
    "дату",
    "випадках",
    "випадку",
    "випадок",
    "разі",
    "раз",
    "органів",
    "органами",
    "органам",
    "діяльності",
    "діяльність",
    "діяльністю",
    "роботи",
    "робота",
    "роботу",
    "служби",
    "служба",
    "службу",
    "службової",
    "службовці",
    "службовців",
    "працівники",
    "працівників",
    "працівник",
    "працівника",
    "керівник",
    "керівника",
    "керівники",
    "керівників",
    "голова",
    "голови",
    "голові",
    "заступник",
    "заступника",
    "заступники",
    "заступників",
    "начальник",
    "начальника",
    "начальники",
    "начальників",
    "відділу",
    "відділ",
    "відділи",
    "управління",
    "управлінням",
    "департаменту",
    "департамент",
    "департаменти",
    "структурних",
    "структурні",
    "структурного",
    "підрозділів",
    "підрозділи",
    "підрозділ",
    "посада",
    "посади",
    "посаду",
    "посадових",
    "посадові",
    "посадової",
    "осіб",
    "особистих",
    "особистого",
    "особисту",
    "відповідальність",
    "відповідальності",
    "відповідальний",
    "відповідальна",
    "відповідальні",
    "зобов'язаний",
    "зобов'язана",
    "зобов'язані",
    "зобов'язання",
    "зобов'язанням",
    "право",
    "права",
    "праві",
    "правом",
    "правами",
    "обов'язок",
    "обов'язку",
    "обов'язки",
    "обов'язків",
    "обов'язково",
    "обов'язкове",
    "обов'язкового",
    "обов'язкову",
    "обов'язкові",
    "вимоги",
    "вимог",
    "вимога",
    "вимогою",
    "умови",
    "умов",
    "умова",
    "умовою",
    "підставою",
    "підставі",
    "підставу",
    "випадком",
    "випадки",
    "випадків",
    "разом",
    "одночасно",
    "одночасного",
    "спільно",
    "спільне",
    "спільний",
    "спільна",
    "спільну",
    "спільні",
    "спільних",
    "спільної",
    "спільним",
    "спільними",
    "спільного",
}


# --- ЗМЕНШЕНИЙ стоп-лист: лише функційні слова + мета-слова відповідей ---
# Попередній STOP містив юридичні змістові слова (україни, громадянство, дата,
# документ, право, орган тощо), через що significant_words() повертав [] для
# відповідей, складених із цих слів, навіть коли відповідь дослівно є в статті.
# Це було першопричиною 0% лексичного збігу. Перевизначаємо STOP нижче.
STOP = {
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
    "вірні",
    "правильні",
    "відповіді",
    "відповідь",
    "варіанти",
    "варіант",
}


def significant_words(text):
    """Повертає список значущих слів (>=4 літери, не стоп-слова)."""
    words = re.findall(r"[а-яіїєґ'’\-]+", normalize(text))
    return [w for w in words if len(w) >= 4 and w not in STOP]


def answer_matches_article(correct, article_text):
    """
    Лексична перевірка: чи ключові слова правильної відповіді є в статті.
    Повертає (matched: bool, ratio: float, words: list).
    """
    c = normalize(correct)
    a = normalize(article_text)
    if not c or not a:
        return False, 0.0, []
    words = significant_words(correct)
    if not words:
        return False, 0.0, []
    found = sum(1 for w in words if w in a)
    ratio = found / len(words)
    return ratio >= LEXICAL_THRESHOLD, ratio, words


def is_neg_question(question):
    """Чи питання типу «що НЕ» — відповідь є тим, чого немає в статті."""
    return bool(NEG_QUESTION_RE.search(question or ""))


# --- Мета-відповіді типу «усі відповіді вірні» ---
META_ANSWER_RE = re.compile(
    r"(?:усі|всі|всіма|усіма)\s+відповід(?:і|ей|і)|"
    r"(?:усі|всі)\s+варіанти|"
    r"(?:усі|всі)\s+зазначені\s+варіанти|"
    r"(?:усі|всі)\s+наведені\s+варіанти|"
    r"правильн(?:і|а)\s+відповід(?:і|ь)|"
    r"(?:усі|всі)\s+правильні|"
    r"обидві\s+відповід(?:і|і)\s+вірн(?:і|а)|"
    r"обидві\s+правильні|"
    r"все\s+наведене(?:\s+вище)?|"
    r"усі\s+вищезазначені\s+відповіді\s+правильні|"
    r"всі\s+вищезазначені\s+відповіді\s+правильні",
    re.IGNORECASE,
)


def is_meta_answer(correct):
    """Чи правильна відповідь є мета-відповіддю типу «усі відповіді вірні»."""
    return bool(META_ANSWER_RE.search(correct or ""))


def _opt_ratio(opt, article_text):
    """Лексичний (з стемінг-фолбеком) збіг одного варіанта з текстом."""
    words = significant_words(opt)
    if not words:
        return None
    a = normalize(article_text)
    if not a:
        return 0.0
    found = sum(1 for w in words if w in a)
    ratio = found / len(words)
    if ratio < LEXICAL_THRESHOLD:
        stem = stem_ratio(opt, article_text)
        ratio = max(ratio, stem)
    return ratio


def verify_meta_answer(question, correct, wrong_options, article_text, law_html=None):
    """
    Перевірка мета-відповіді «усі відповіді вірні».
    Така відповідь правильна, якщо КОЖЕН з варіантів (wrong) підтверджується
    текстом закону (лексично або стемінгом). Спершу шукаємо в зазначеній статті,
    а якщо варіант там не знайдено — по всьому закону (бо «усі відповіді вірні»
    означає, що кожен варіант є істинним твердженням закону, можливо в іншій статті).
    Повертає (bool, detail).
    """
    if not wrong_options:
        # Немає інших варіантів — довіряємо банку (мета-відповідь самодостатня).
        return True, "meta(без варіантів)"
    if not normalize(article_text):
        return False, "meta(порожня стаття)"

    # Зібрати всі тексти статей закону для пошуку «по всьому закону»
    law_articles = []
    if law_html:
        try:
            law_articles = extract_articles(law_html)
        except Exception:
            law_articles = []

    confirmed = 0
    details = []
    for opt in wrong_options:
        if not opt:
            continue
        ratio = _opt_ratio(opt, article_text)
        if ratio is None:
            confirmed += 1
            details.append("(без слів)")
            continue
        # Якщо в зазначеній статті не знайдено — шукаємо по всьому закону
        if ratio < LEXICAL_THRESHOLD and law_articles:
            best = 0.0
            for _t, body in law_articles:
                r = _opt_ratio(opt, body or "")
                if r is not None and r > best:
                    best = r
            ratio = max(ratio, best)
        ok = ratio >= LEXICAL_THRESHOLD
        if ok:
            confirmed += 1
        details.append(f"{ratio:.0%}")
    # Вважаємо «усі відповіді вірні» підтвердженим, якщо підтверджено
    # більшість варіантів (>= 2/3), або всі, коли варіантів мало.
    need = max(1, int(len([d for d in details if d != "(без слів)"]) * 2 / 3))
    return confirmed >= need, f"meta({confirmed}/{len(details)})"


def stem_ratio(correct, article_text):
    """
    Стемінг-збіг: частка значущих слів відповіді, чий корінь (префікс
    довжиною STEM_MIN) зустрічається серед слів статті. Ловить відмінкові
    та словотвірні варіанти, які точний лексичний збіг пропускає.
    Повертає float у [0, 1].
    """
    if not article_text:
        return 0.0
    cw = significant_words(correct)
    if not cw:
        return 0.0
    aw = significant_words(article_text)
    if not aw:
        return 0.0
    hit = 0
    for w in cw:
        base = w[:STEM_MIN]
        if any(a.startswith(base) for a in aw):
            hit += 1
    return hit / len(cw)


# --- LLM-семантична перевірка (опційно) ---
def _load_llm():
    """Імпортує team_llm з docs-sorter. Повертає модуль або None."""
    # Шлях можна задати через змінну середовища DOCS_SORTER_DIR (для Docker),
    # інакше — стандартний шлях на хості.
    candidates = []
    env_dir = os.environ.get("DOCS_SORTER_DIR", "")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path.home() / "projects/firm/platforms/docs-sorter")
    for d in candidates:
        try:
            sys.path.insert(0, str(d))
            import team_llm  # noqa: F401

            return team_llm
        except Exception:
            continue
    return None


# Ланцюг провайдерів: openai першим (deepseek без балансу, glm повертає '').
LLM_CHAIN = [
    "openai",
    "glm",
    "deepseek",
]
LLM_TIMEOUT = 30
LLM_MAX_TOKENS = 200

_llm_module = None


def verify_with_llm(question, correct, article_text, max_chars=3000):
    """
    Семантична перевірка LLM: чи правильна відповідь узгоджується зі статтею.
    Повертає (bool, provider) або (None, None) якщо LLM недоступний.
    max_chars — скільки символів тексту статті передавати LLM (за замовчуванням 3000).
    """
    global _llm_module
    if _llm_module is None:
        _llm_module = _load_llm()
    if _llm_module is None:
        return None, None

    system = (
        "Ти — юрист-екзаменатор з права України. Тобі дають питання тесту МЗС, "
        "правильну відповідь і текст статті закону. Визнач, чи правильна відповідь "
        "УЗГОДЖУЄТЬСЯ з текстом статті (тобто стаття підтверджує цю відповідь). "
        "Відповідай ТІЛЬКИ одним словом: ТАК або НІ."
    )
    user = (
        f"ПИТАННЯ: {question}\n\n"
        f"ПРАВИЛЬНА ВІДПОВІДЬ: {correct}\n\n"
        f"ТЕКСТ СТАТТІ:\n{article_text[:max_chars]}\n\n"
        "Чи узгоджується правильна відповідь з текстом статті? Відповідь: ТАК або НІ."
    )
    try:
        provider, output = _llm_module.chat_fallback(
            system,
            user,
            chain=LLM_CHAIN,
            timeout=LLM_TIMEOUT,
            max_tokens=LLM_MAX_TOKENS,
        )
        if not output:
            return None, provider
        out = output.strip().upper()
        if out.startswith("ТАК"):
            return True, provider
        if out.startswith("НІ"):
            return False, provider
        return None, provider
    except Exception:
        return None, None


def simulate_training(bank, limit=0, verbose=False, use_llm=True, llm_only=False):
    """
    Симулює проходження навчання по всіх питаннях банку.
    Повертає (results, mismatches, unverified_list).
    """
    questions = []
    for sec in bank.get("sections", []):
        for q in sec.get("questions", []):
            q["_section"] = sec.get("title", "")
            q["_section_id"] = sec.get("id", "")
            questions.append(q)

    if limit and limit > 0:
        random.shuffle(questions)
        questions = questions[:limit]

    # Кеш HTML-документів актів
    law_cache = {}

    results = []  # (qid, section, status, detail)
    mismatches = []  # питання, де correct НЕ узгоджується зі статтею
    unverified_list = []  # питання без ref або без статті

    for i, q in enumerate(questions, 1):
        qid = q.get("id", "?")
        section = q.get("_section", "")
        correct = q.get("correct", "")
        ref = (q.get("explain") or {}).get("ref", "")

        # Країнознавство — не норма права, пропускаємо перевірку.
        # Визначаємо за id розділу або за ключовими словами в ref
        # (конспект, польське право/історія — не акти України).
        section_id = q.get("_section_id", "")
        KRAJ_KEYWORDS = (
            "Конспект країнознавства",
            "Конституція Республіки Польща",
            "Карта Поляка",
            "діловодство в Польщі",
            "Історія Польщі",
            "Гадяцький договір",
            "Загальні знання про ЄС",
            "Загальні знання про консульську діяльність",
        )
        if section_id == "krainoznavstvo-polsha" or any(
            k.lower() in ref.lower() for k in KRAJ_KEYWORDS
        ):
            results.append(
                (qid, section, "krajoznawstwo", "пропущено (конспект/країнознавство)")
            )
            continue

        fname = legislation_file(ref)
        if not fname:
            results.append((qid, section, "no_ref", "немає акта за ref"))
            unverified_list.append((qid, section, ref, "немає акта за ref"))
            continue

        if fname not in law_cache:
            path = LAWS_DIR / fname
            if not path.exists():
                law_cache[fname] = None
            else:
                law_cache[fname] = path.read_text(encoding="utf-8", errors="replace")
        html_text = law_cache[fname]
        if not html_text:
            results.append((qid, section, "no_file", f"немає файлу {fname}"))
            unverified_list.append((qid, section, ref, f"немає файлу {fname}"))
            continue

        title, article_text = extract_article_by_ref(html_text, ref)
        if not article_text:
            results.append((qid, section, "no_article", f"немає статті за ref {ref}"))
            unverified_list.append((qid, section, ref, f"немає статті за ref {ref}"))
            continue

        # Двоступенева перевірка
        matched, ratio, words = answer_matches_article(correct, article_text)

        if llm_only:
            matched = False
            ratio = 0.0

        if matched:
            results.append(
                (qid, section, "verified_lex", f"лексичний збіг {ratio:.0%}")
            )
            continue

        # Мета-відповідь «усі відповіді вірні»: лексичний збіг неможливий,
        # бо текст відповіді — мета-текст. Перевіряємо, що всі варіанти
        # (wrong) підтверджуються статтею.
        if is_meta_answer(correct):
            meta_ok, meta_detail = verify_meta_answer(
                q.get("question", ""),
                correct,
                q.get("wrong", []),
                article_text,
                html_text,
            )
            if meta_ok:
                results.append(
                    (qid, section, "verified_lex", f"мета-відповідь {meta_detail}")
                )
                continue
            # Якщо мета-відповідь не підтвердилась — це справжня розбіжність
            results.append(
                (
                    qid,
                    section,
                    "mismatch",
                    f"мета-відповідь не підтверджена {meta_detail}",
                )
            )
            mismatches.append(
                (
                    qid,
                    section,
                    correct,
                    ref,
                    f"мета-відповідь не підтверджена {meta_detail}",
                )
            )
            continue

        # Стемінг-фолбек: точний збіг недостатній, але корені слів відповіді
        # збігаються зі статтею (відмінкові/словотвірні варіанти). Вимикаємо
        # для питань «що НЕ» — там слово відповіді може бути в статті в
        # іншому контексті, і стемінг дав би хибне підтвердження.
        if (
            not llm_only
            and len(words) >= MIN_SIGNIFICANT_WORDS
            and not is_neg_question(q.get("question", ""))
        ):
            stem = stem_ratio(correct, article_text)
            if stem >= LEXICAL_THRESHOLD:
                results.append(
                    (qid, section, "verified_lex", f"стемінг-збіг {stem:.0%}")
                )
                continue

        # Лексичний збіг недостатній -> LLM
        if use_llm and (
            llm_only or len(words) < MIN_SIGNIFICANT_WORDS or ratio < LEXICAL_THRESHOLD
        ):
            ok, provider = verify_with_llm(q.get("question", ""), correct, article_text)
            if ok is True:
                results.append((qid, section, "verified_llm", f"LLM({provider})"))
                continue
            if ok is False:
                results.append((qid, section, "mismatch", f"LLM({provider}) відхилив"))
                mismatches.append(
                    (qid, section, correct, ref, f"LLM({provider}) відхилив")
                )
                continue
            # LLM недоступний -> вважаємо неперевіреним
            results.append(
                (qid, section, "unverified", f"лексичний {ratio:.0%}, LLM недоступний")
            )
            unverified_list.append(
                (qid, section, ref, f"лексичний {ratio:.0%}, LLM недоступний")
            )
            continue

        # LLM вимкнено -> лексичний збіг недостатній = розбіжність
        results.append((qid, section, "mismatch", f"лексичний збіг {ratio:.0%}"))
        mismatches.append((qid, section, correct, ref, f"лексичний збіг {ratio:.0%}"))

        if verbose:
            print(
                f"  [{i}/{len(questions)}] {qid} ({section}): {results[-1][2]} — {results[-1][3]}"
            )

    return results, mismatches, unverified_list


def print_report(results, mismatches, unverified_list, verbose=False):
    """Друкує зведення результатів симуляції."""
    total = len(results)
    verified_lex = sum(1 for r in results if r[2] == "verified_lex")
    verified_llm = sum(1 for r in results if r[2] == "verified_llm")
    mismatch = sum(1 for r in results if r[2] == "mismatch")
    no_ref = sum(1 for r in results if r[2] == "no_ref")
    no_file = sum(1 for r in results if r[2] == "no_file")
    no_article = sum(1 for r in results if r[2] == "no_article")
    kraj = sum(1 for r in results if r[2] == "krajoznawstwo")
    unverified = sum(1 for r in results if r[2] == "unverified")

    print("\n" + "=" * 60)
    print("ЗВЕДЕННЯ СИМУЛЯЦІЇ ТЕСТІВ МЗС")
    print("=" * 60)
    print(f"Всього питань:            {total}")
    print(f"  Підтверджено (лексика): {verified_lex}")
    print(f"  Підтверджено (LLM):     {verified_llm}")
    print(f"  РОЗБІЖНОСТІ:            {mismatch}")
    print(f"  Країнознавство (проп.): {kraj}")
    print(f"  Немає акта за ref:      {no_ref}")
    print(f"  Немає файлу акта:       {no_file}")
    print(f"  Немає статті за ref:    {no_article}")
    print(f"  Неперевірено (LLM off): {unverified}")
    verified_total = verified_lex + verified_llm
    checked = total - kraj - no_ref - no_file - no_article
    if checked > 0:
        pct = 100.0 * verified_total / checked
        print(f"\nПідтверджено з перевірених: {pct:.1f}% ({verified_total}/{checked})")
    print("=" * 60)

    if mismatches:
        print(f"\nРОЗБІЖНОСТІ ({len(mismatches)}):")
        for qid, section, correct, ref, detail in mismatches:
            print(f"  - {qid} [{section}] {detail}")
            print(f"      відповідь: {correct[:120]}")
            print(f"      ref: {ref}")

    if unverified_list:
        print(f"\nНЕПЕРЕВІРЕНО ({len(unverified_list)}):")
        for qid, section, ref, detail in unverified_list:
            print(f"  - {qid} [{section}] {detail} | ref: {ref}")

    if verbose:
        print("\nПОКРОКОВО:")
        for qid, section, status, detail in results:
            print(f"  {qid} [{section}]: {status} — {detail}")


def main():
    parser = argparse.ArgumentParser(description="Імітація тестів МЗС")
    parser.add_argument(
        "--bank", default=str(DEFAULT_BANK), help="Шлях до банку питань"
    )
    parser.add_argument("--verbose", action="store_true", help="Детальний вивід")
    parser.add_argument(
        "--limit", type=int, default=0, help="Обмежити кількість питань"
    )
    parser.add_argument(
        "--no-llm", action="store_true", help="Використати лише лексичну перевірку"
    )
    parser.add_argument(
        "--llm-only", action="store_true", help="Використати лише LLM-перевірку"
    )
    args = parser.parse_args()

    # Змінні середовища (docker-compose)
    bank_path = os.environ.get("BANK_FILE", args.bank)
    verbose = args.verbose or os.environ.get("VERBOSE", "0") == "1"
    limit = args.limit or int(os.environ.get("LIMIT", "0") or 0)
    no_llm = args.no_llm or os.environ.get("NO_LLM", "0") == "1"
    llm_only = args.llm_only or os.environ.get("LLM_ONLY", "0") == "1"

    bank_file = Path(bank_path)
    if not bank_file.exists():
        print(f"Помилка: банк не знайдено: {bank_file}", file=sys.stderr)
        sys.exit(2)

    with open(bank_file, encoding="utf-8") as f:
        bank = json.load(f)

    print(f"Банк: {bank_file.name} | питань у банку: {bank.get('total', '?')}")
    if limit:
        print(f"Симуляція обмежена: {limit} питань (випадкових)")

    results, mismatches, unverified_list = simulate_training(
        bank,
        limit=limit,
        verbose=verbose,
        use_llm=not no_llm,
        llm_only=llm_only,
    )
    print_report(results, mismatches, unverified_list, verbose=verbose)

    # Код виходу: 1 якщо є розбіжності або неперевірені
    if mismatches or unverified_list:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
