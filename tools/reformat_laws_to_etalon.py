#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reformat_laws_to_etalon.py
==========================
Приводить ВСІ документи законів (laws/*.html) до еталонного формату
(еталон — haazka-konventsiia-apostyl.html: чиста типографіка, читабельні
абзаци, жирні заголовки статей, без суцільних стін тексту).

Що робить скрипт для кожного файлу:
  1. Парсить HTML (html.parser) і знаходить тіло документа (.doc-body або body).
  2. Regex-cleanup тексту:
       - відновлює пропуски: «ст.178№429» -> «ст.178 № 429», «№429» -> «№ 429»
       - прибирає зайві пробіли перед комами/крапками/крапками з комою
       - нормалізує множинні пробіли
  3. Розбиває «суцільні стіни тексту» — дуже довгі <p> (> ~1400 символів)
     на окремі читабельні абзаци за межами речень.
  4. Гігантські блоки «{Із змінами...}» у преамбулі згортає у <details>
     (щоб не займали пів екрана суцільною стіною).
  5. Заголовки статей (<h3>Стаття N. ...</h3>) приводить до єдиного вигляду:
     жирний, без зайвих пробілів навколо номера («Стаття 7 - 1 .» -> «Стаття 7-1.»).
  6. Зберігає файл на місці (з резервною копією .bak).

Використання:
    python3 tools/reformat_laws_to_etalon.py            # всі 53 закони
    python3 tools/reformat_laws_to_etalon.py --dry-run  # тільки показати, що зміниться
    python3 tools/reformat_laws_to_etalon.py laws/rehlament-verkhovnoi-rady.html
"""

import glob
import html as html_mod
import os
import re
import sys
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Конфігурація
# ---------------------------------------------------------------------------
LAWS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "laws"
)

# Поріг довжини <p>, після якого вважаємо його «стіною тексту» і розбиваємо
MAX_PARAGRAPH_CHARS = 1400

# Поріг довжини блоку «{Із змінами...}», після якого згортаємо в <details>
MAX_AMENDMENT_CHARS = 900


# ---------------------------------------------------------------------------
# Regex-cleanup тексту
# ---------------------------------------------------------------------------
def cleanup_text(text: str) -> str:
    """Відновлює типографіку: пропуски, коми, крапки, множинні пробіли."""
    if not text:
        return text

    # «ст.178№429» -> «ст.178 № 429» ; «№429» -> «№ 429»
    text = re.sub(r"(ст\.\s*\d+)\s*(№)", r"\1 \2", text)
    text = re.sub(r"(№)\s*(\d)", r"\1 \2", text)

    # «ст.133)» -> «ст. 133)» (номер статті після «ст.»)
    text = re.sub(r"\bст\.(\d)", r"ст. \1", text)

    # «п.5» -> «п. 5» (пункт)
    text = re.sub(r"\bп\.(\d)", r"п. \1", text)

    # «ч.3» -> «ч. 3» (частина)
    text = re.sub(r"\bч\.(\d)", r"ч. \1", text)

    # «абз.2» -> «абз. 2» (абзац)
    text = re.sub(r"\bабз\.(\d)", r"абз. \1", text)

    # прибрати пробіл перед комою/крапкою/крапкою з комою/двокрапкою
    text = re.sub(r"\s+([,.;:])", r"\1", text)

    # прибрати пробіл перед закриваючою дужкою
    text = re.sub(r"\s+\)", r")", text)

    # прибрати пробіл після відкриваючої дужки
    text = re.sub(r"\(\s+", r"(", text)

    # нормалізувати множинні пробіли (але зберегти переноси рядків)
    text = re.sub(r"[ \t]{2,}", " ", text)

    # прибрати пробіли на початку/в кінці кожного рядка
    text = "\n".join(line.strip() for line in text.split("\n"))

    return text.strip()


def split_long_paragraph(text: str) -> list:
    """Розбиває довгий текст на читабельні абзаци за межами речень.

    Повертає список рядків (абзаців). Якщо текст короткий — один елемент.
    """
    if len(text) <= MAX_PARAGRAPH_CHARS:
        return [text]

    # Розбиваємо за межами речень (крапка + пробіл + велика літера / цифра)
    # Але не розриваємо скорочення «ст.», «п.», «ч.», «абз.», «№», ініціали.
    sentences = re.split(r'(?<=[.!?])\s+(?=[А-ЯІЇЄҐA-Z0-9«"(\[])', text)

    chunks = []
    current = ""
    for sent in sentences:
        # Не розривати скорочення на кшталт «ст. 133» — вони вже не містять
        # крапки з пробілом+великою, тому потраплять у той самий шматок.
        if len(current) + len(sent) + 1 <= MAX_PARAGRAPH_CHARS:
            current = (current + " " + sent).strip() if current else sent
        else:
            if current:
                chunks.append(current)
            current = sent

    if current:
        chunks.append(current)

    # Якщо не вдалося розбити (один гігантський шматок без меж речень) —
    # примусово ріжемо по ~1200 символів на межі пробілу.
    if len(chunks) == 1 and len(chunks[0]) > MAX_PARAGRAPH_CHARS:
        chunks = _hard_split(chunks[0])

    return chunks


def _hard_split(text: str, limit: int = 1200) -> list:
    """Примусово ріже довгий текст на шматки по межі пробілу."""
    out = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


def normalize_article_title(text: str) -> str:
    """Приводить заголовок статті до єдиного вигляду.

    «Стаття 7 - 1 . Документообіг» -> «Стаття 7-1. Документообіг»
    «Стаття 1. Правові засади»     -> «Стаття 1. Правові засади»
    """
    t = text.strip()
    # «Стаття 7 - 1 .» -> «Стаття 7-1.»
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", t)
    # «Стаття 7 -1» -> «Стаття 7-1»
    t = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", t)
    # «Стаття 7 .» -> «Стаття 7.»
    t = re.sub(r"(\d)\s*\.", r"\1.", t)
    # «Стаття 7-1 .» -> «Стаття 7-1.»
    t = re.sub(r"(\d)\s*\.", r"\1.", t)
    # прибрати зайві пробіли
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Парсер HTML
# ---------------------------------------------------------------------------
class LawParser(HTMLParser):
    """Збирає структуру документа: список блоків (tag, attrs, text)."""

    VOID = {"br", "hr", "img", "meta", "link", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []  # список (tag, attrs, inner_html)
        self.stack = []  # стек відкритих тегів
        self.buf = []  # накопичення тексту поточного блоку
        self.in_body = False
        self.in_doc_body = False
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if tag == "div" and self._has_class(attrs, "doc-body"):
            self.in_doc_body = True
        self.stack.append((tag, dict(attrs)))
        self.buf.append("")

    def handle_endtag(self, tag):
        # закриваємо до відповідного відкриваючого
        while self.stack:
            open_tag, attrs = self.stack.pop()
            content = "".join(self.buf)
            self.buf.pop()
            if open_tag == tag:
                self.blocks.append((open_tag, attrs, content))
                break
            else:
                # непарний тег — просто зберігаємо як текст
                self.blocks.append((open_tag, attrs, content))
        if tag == "div" and self.in_doc_body:
            self.in_doc_body = False
        if tag == "body":
            self.in_body = False

    def handle_startendtag(self, tag, attrs):
        # самозакривні теги
        self.blocks.append((tag, dict(attrs), ""))

    def handle_data(self, data):
        if self.buf:
            self.buf[-1] += data

    @staticmethod
    def _has_class(attrs, cls):
        for k, v in attrs:
            if k == "class" and cls in (v or "").split():
                return True
        return False


# ---------------------------------------------------------------------------
# Основна логіка
# ---------------------------------------------------------------------------
def reformat_file(path: str, dry_run: bool = False) -> dict:
    """Обробляє один файл закону. Повертає звіт про зміни."""
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    report = {"file": os.path.basename(path), "changed": False, "notes": []}

    # --- 1. Regex-cleanup усього тексту (безпечно, не ламає теги) ---
    # Обробляємо лише текст між тегами, не самі теги.
    cleaned = _cleanup_html_text(original, report)

    # --- 2. Розбивка «стін тексту» та згортання гігантських «{Із змінами...}» ---
    cleaned = _restructure_paragraphs(cleaned, report)

    if cleaned != original:
        report["changed"] = True

    if not dry_run and report["changed"]:
        # резервна копія
        bak = path + ".bak"
        if not os.path.exists(bak):
            with open(bak, "w", encoding="utf-8") as f:
                f.write(original)
        with open(path, "w", encoding="utf-8") as f:
            f.write(cleaned)

    return report


def _cleanup_html_text(html_text: str, report: dict) -> str:
    """Застосовує cleanup_text до тексту всередині тегів, не чіпаючи самі теги."""
    # Розбиваємо на шматки: теги та текст між ними
    parts = re.split(r"(<[^>]+>)", html_text)
    out = []
    cleaned_any = False
    for part in parts:
        if part.startswith("<"):
            out.append(part)
        else:
            new = cleanup_text(part)
            if new != part:
                cleaned_any = True
            out.append(new)
    if cleaned_any:
        report["notes"].append("regex-cleanup типографіки")
    return "".join(out)


def _collapse_amendments(text: str):
    """Якщо абзац — це переважно історія змін у {…} або гігантська преамбула,
    згортає її в <details>.

    Повертає HTML-рядок або None, якщо абзац не є «стіною змін».
    """
    # ЗАХИСТ: якщо всередині є заголовки статей (<h2>/<h3>) — це не преамбула,
    # а весь документ (мальформований <p> проковтнув усе тіло). Не чіпаємо.
    if re.search(r"<h[23][^>]*>", text):
        return None
    # Знаходимо всі блоки {…}
    braces = re.findall(r"\{[^{}]*\}", text)
    braces_text = "".join(braces)

    # Ознаки «історії змін» / преамбули:
    #  1) багато блоків {…}
    #  2) багато посилань на ВВР (Відомості Верховної Ради)
    vvr_count = len(re.findall(r"ВВР", text))
    brace_ratio = len(braces_text) / max(len(text), 1)

    is_amendment_wall = (
        (braces and brace_ratio > 0.30)
        or (len(text) > 3000 and vvr_count >= 3)
        or (len(text) > 8000 and braces)
    )

    if not is_amendment_wall:
        return None

    # Відокремлюємо «живий» текст (поза дужками) від історії змін
    live_parts = re.split(r"\{[^{}]*\}", text)
    live_text = " ".join(p.strip() for p in live_parts if p.strip()).strip()

    summary = (live_text[:140] if live_text else "Історія змін документа").rstrip() + "…"
    details = (
        f'<details class="law-amendments"><summary>📜 {html_mod.escape(summary)}</summary>'
        f'<div class="law-amendments-body">{html_mod.escape(text)}</div></details>'
    )
    return details


def _restructure_paragraphs(html_text: str, report: dict) -> str:
    """Розбиває довгі <p> на абзаци та згортає гігантські «{Із змінами...}»."""
    # Знаходимо всі <p ...>...</p> (без вкладених <p>)
    pattern = re.compile(r"(<p(?:\s[^>]*)?>)(.*?)(</p>)", re.DOTALL)

    def repl(m):
        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)

        # --- ЗАХИСТ: якщо <p> містить заголовки статей (<h2>/<h3>) або
        # вкладені <p> — це мальформований <p>, що проковтнув увесь документ.
        # Не розбиваємо й не згортаємо, лишаємо як є (типографіку вже почищено).
        if re.search(r"<h[23][^>]*>", inner) or "<p" in inner:
            return open_tag + inner + close_tag

        # --- Згортання гігантських «{Із змінами...}» ---
        # Якщо весь <p> — це один великий блок змін у фігурних дужках
        stripped = inner.strip()
        if (
            stripped.startswith("{")
            and stripped.endswith("}")
            and len(stripped) > MAX_AMENDMENT_CHARS
        ):
            report["notes"].append("згорнуто гігантський блок змін у <details>")
            summary = stripped[:120].rstrip() + "…"
            details = (
                f'<details class="law-amendments"><summary>📜 {html_mod.escape(summary)}</summary>'
                f'<div class="law-amendments-body">{inner}</div></details>'
            )
            return details

        # --- Розбивка довгих абзаців ---
        # Видаляємо теги всередині для оцінки довжини тексту
        text_only = re.sub(r"<[^>]+>", "", inner)
        if len(text_only) > MAX_PARAGRAPH_CHARS:
            # Якщо абзац — це переважно історія змін у {…}, згортаємо її в <details>
            collapsed = _collapse_amendments(text_only)
            if collapsed is not None:
                report["notes"].append(
                    f"згорнуто історію змін у <details> ({len(text_only)} симв.)"
                )
                return collapsed
            report["notes"].append(
                f"розбито стіну тексту ({len(text_only)} симв.) на абзаци"
            )
            chunks = split_long_paragraph(text_only)
            # Якщо всередині були <b>/<i> — втрачаємо їх, але це прийнятно для стін тексту
            paras = "".join(f"<p>{html_mod.escape(c)}</p>" for c in chunks)
            return paras

        return open_tag + inner + close_tag

    return pattern.sub(repl, html_text)


def normalize_article_headers(html_text: str, report: dict) -> str:
    """Приводить заголовки <h3>Стаття N. ...</h3> до єдиного вигляду."""
    pattern = re.compile(r"(<h3[^>]*>)(.*?)(</h3>)", re.DOTALL)

    def repl(m):
        open_tag, inner, close_tag = m.group(1), m.group(2), m.group(3)
        text_only = re.sub(r"<[^>]+>", "", inner).strip()
        if re.match(r"^\s*Стаття\s*\d", text_only, re.IGNORECASE):
            new_title = normalize_article_title(text_only)
            if new_title != text_only:
                report["notes"].append(
                    f"нормалізовано заголовок: «{text_only}» -> «{new_title}»"
                )
            # Жирний заголовок статті
            return f"{open_tag}<strong>{html_mod.escape(new_title)}</strong>{close_tag}"
        return open_tag + inner + close_tag

    return pattern.sub(repl, html_text)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    targets = [a for a in args if not a.startswith("--")]

    if targets:
        files = [
            t
            if os.path.isabs(t)
            else os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))), t
            )
            for t in targets
        ]
    else:
        files = sorted(glob.glob(os.path.join(LAWS_DIR, "*.html")))

    total_changed = 0
    total_notes = 0
    print(f"{'DRY-RUN ' if dry_run else ''}Обробка {len(files)} файлів законів...\n")

    for f in files:
        if not os.path.exists(f):
            print(f"  ✗ НЕ ЗНАЙДЕНО: {f}")
            continue
        report = reformat_file(f, dry_run=dry_run)
        # Додатково нормалізуємо заголовки статей
        if report["changed"]:
            with open(f, "r", encoding="utf-8") as fh:
                content = fh.read()
            content2 = normalize_article_headers(content, report)
            if content2 != content:
                with open(f, "w", encoding="utf-8") as fh:
                    fh.write(content2)

        status = "✎ ЗМІНЕНО" if report["changed"] else "✓ без змін"
        print(f"  {status}: {os.path.basename(f)}")
        for note in report["notes"]:
            print(f"      • {note}")
            total_notes += 1
        if report["changed"]:
            total_changed += 1

    print(f"\nГотово. Змінено файлів: {total_changed}, всього правок: {total_notes}.")
    if dry_run:
        print("(режим --dry-run: файли не записані)")


if __name__ == "__main__":
    main()
