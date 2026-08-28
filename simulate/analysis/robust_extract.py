#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Покращений витяг тексту статті/пункту для LLM-аудиту (Крок 2e).

Виправляє відомі баги базового simulate.extract_article_by_ref:
  1) "§ N" (Регламент КМУ) — шукає "§ N." напряму, а не "N.";
  2) "п. N-M" (напр. "8-1") — обробляє дефісні номери пунктів (формат "8 - 1 .");
  3) "п. N" у документах типу Правила/Інструкція, де є і постанова (оперативна
     частина), і тіло Правил/Інструкції — обирає пункт із тіла (після маркера
     "Ці Правила"/"Ця Інструкція"), а не з оперативної частини постанови;
  4) повертає ПОВНИЙ текст (без обрізання), щоб LLM бачив увесь пункт/статтю.

Використовується ТІЛЬКИ в аналітичних скриптах аудиту, не чіпає прод simulate.py.
"""

import re

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


def robust_extract_article_by_ref(html_text, ref):
    """
    Покращений витяг. Повертає (title, body_text) — body_text це ПЛОСКИЙ текст
    (без HTML), повний, не обрізаний.
    """
    # 1) "§ N" — Регламент КМУ
    m = re.search(r"§\s*([0-9]+)", ref)
    if m:
        title, body = _extract_section(html_text, int(m.group(1)))
        if body:
            return title, body

    # 2) "п. N-M" / "пункт N-M" — дефісний номер
    m = re.search(r"п(?:ункт)?\.?\s*([0-9]+)\s*-\s*([0-9]+)", ref, re.IGNORECASE)
    if m:
        point_str = f"{m.group(1)}-{m.group(2)}"
        title, body = _extract_point(html_text, point_str, prefer_body=True)
        if body:
            return title, body

    # 3) "п. N" / "пункт N" — пункт (переважно з тіла Правил/Інструкції)
    m = re.search(r"п(?:ункт)?\.?\s*([0-9]+)", ref, re.IGNORECASE)
    if m:
        title, body = _extract_point(html_text, m.group(1), prefer_body=True)
        if body:
            return title, body

    # 4) "ст. N" / "стаття N" — стаття (базовий витяг)
    return None, None


def _extract_article(html_text, ref):
    """
    Витяг статті "ст. N" / "стаття N" (включно з Віденськими конвенціями
    "Article N" та Консульським статутом "С т а т т я N").
    Делегує базовому simulate.extract_article_by_ref (імпортується ліниво,
    щоб уникнути циклічного імпорту).
    """
    import simulate  # noqa: PLC0415

    return simulate.extract_article_by_ref(html_text, ref)


def _extract_point_all(html_text, point_str, prefer_body=True):
    """
    Повертає СПИСОК усіх текстів пунктів 'N.' / 'N-M.' у документі.
    Корисно для консолідованих документів, де нумерація пунктів
    перезапускається в кожному розділі (напр. Типова інструкція з діловодства).
    """
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)

    if "-" in point_str:
        a, b = point_str.split("-", 1)
        num_pat = re.escape(a) + r"\s*-\s*" + re.escape(b)
    else:
        num_pat = re.escape(point_str)

    start_pat = re.compile(r"(?<!\d)" + num_pat + r"\s*\.\s*")
    next_pat = re.compile(r"(?<!\d)(\d{1,3}(?:\s*-\s*\d{1,3})?)\s*\.\s*")

    start = _find_body_start(html_text) if prefer_body else 0
    results = []
    pos = start
    while True:
        m = start_pat.search(plain, pos)
        if not m:
            break
        begin = m.start()
        # пропускаємо "N", що є другою частиною дефісного діапазону "X-N"
        if "-" not in point_str:
            before = plain[max(0, begin - 12) : begin]
            if re.search(r"\d\s*-\s*$", before):
                pos = m.end()
                continue
        rest = plain[m.end() :]
        nxt = next_pat.search(rest)
        if nxt:
            end = m.end() + nxt.start()
        else:
            end = len(plain)
        results.append(plain[begin:end].strip())
        pos = m.end()
    return results


def _score_keywords(text, keywords):
    """Кількість значущих слів із keywords, що зустрічаються в text."""
    if not keywords:
        return 0
    low = text.lower()
    score = 0
    for kw in keywords:
        if kw and len(kw) >= 3 and kw.lower() in low:
            score += 1
    return score


def robust_extract_article_by_ref_scored(html_text, ref, keywords=None):
    """
    Як robust_extract_article_by_ref, але для пунктів з неоднозначною нумерацією
    (кілька 'п. N' у консолідованому документі) обирає пункт із найбільшим
    лексичним збігом із keywords (значущі слова питання/відповіді).
    Повертає (title, body_text).
    """
    # 1) "§ N" — Регламент КМУ
    m = re.search(r"§\s*([0-9]+)", ref)
    if m:
        title, body = _extract_section(html_text, int(m.group(1)))
        if body:
            return title, body

    # 2) "п. N-M" / "пункт N-M" — дефісний номер
    m = re.search(r"п(?:ункт)?\.?\s*([0-9]+)\s*-\s*([0-9]+)", ref, re.IGNORECASE)
    if m:
        point_str = f"{m.group(1)}-{m.group(2)}"
        cands = _extract_point_all(html_text, point_str, prefer_body=True)
        if cands:
            best = max(cands, key=lambda c: _score_keywords(c, keywords))
            return f"Пункт {point_str}", best

    # 3) "п. N" / "пункт N" — пункт (переважно з тіла Правил/Інструкції)
    m = re.search(r"п(?:ункт)?\.?\s*([0-9]+)", ref, re.IGNORECASE)
    if m:
        point_str = m.group(1)
        cands = _extract_point_all(html_text, point_str, prefer_body=True)
        if cands:
            best = max(cands, key=lambda c: _score_keywords(c, keywords))
            return f"Пункт {point_str}", best

    # 4) "ст. N" / "стаття N" — стаття (базовий витяг)
    m = re.search(r"ст(?:атя)?\.?\s*([0-9]+(?:\s*-\s*[0-9]+)?)", ref, re.IGNORECASE)
    if m:
        return _extract_article(html_text, ref)

    return None, None
