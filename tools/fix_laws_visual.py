#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_laws_visual.py
==================
Приводить ВСІ документи законів (laws/*.html) до ЕТАЛОННОГО візуального формату:

  1. Sticky-шапка закону (.law-header, position:sticky; top:0; z-index:100;
     background:#fff; border-bottom) — текст скролиться ПІД нею, плашка
     «Повний текст документа» НІКОЛИ не перекриває текст.
  2. Назва закону в шапці — українською (з <title> або <h1>), без трансліту.
  3. Кожна стаття обгортається в окремий блок <div class="law-article"> з
     заголовком <h3 class="law-article-title"> — з відступами між статтями.
  4. Відновлення абзаців <p> з нормальними відступами (margin).
  5. Regex-cleanup типографіки: «ст.178№429» -> «ст.178 № 429», «№429» -> «№ 429».
  6. Плашка «Повний текст документа» переноситься у футер, а не накладається
     на початок тексту.

Структура результату:
    <div class="law">
      <header class="law-header">
        <h1>Назва закону (українською)</h1>
        <div class="law-meta">…</div>
      </header>
      <div class="law-content">
        <div class="law-article" id="article-1">
          <h3 class="law-article-title">Стаття 1. …</h3>
          <p>…</p>
        </div>
        …
      </div>
      <footer class="law-footer">Повний текст документа…</footer>
    </div>

Використання:
    python3 tools/fix_laws_visual.py            # всі 53 закони
    python3 tools/fix_laws_visual.py --dry-run  # тільки показати, що зміниться
    python3 tools/fix_laws_visual.py laws/zakon-pro-hromadianstvo.html
"""

import glob
import os
import re
import sys

LAWS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "laws"
)


# ---------------------------------------------------------------------------
# Regex-cleanup типографіки
# ---------------------------------------------------------------------------
def cleanup_text(text: str) -> str:
    """Відновлює пропуски та нормалізує типографіку в тексті."""
    if not text:
        return text
    # «ст.178№429» -> «ст.178 № 429»
    text = re.sub(r"(ст\.\s*\d+)\s*(№)", r"\1 \2", text)
    # «№429» -> «№ 429»
    text = re.sub(r"(№)\s*(\d)", r"\1 \2", text)
    # «ст.178» -> «ст. 178»
    text = re.sub(r"(ст\.)\s*(\d)", r"\1 \2", text)
    # «п.1» -> «п. 1»
    text = re.sub(r"(п\.)\s*(\d)", r"\1 \2", text)
    # «ч.1» -> «ч. 1»
    text = re.sub(r"(ч\.)\s*(\d)", r"\1 \2", text)
    # «абз.1» -> «абз. 1»
    text = re.sub(r"(абз\.)\s*(\d)", r"\1 \2", text)
    # прибрати пробіл перед комою/крапкою/крапкою з комою/двокрапкою
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    # нормалізувати множинні пробіли
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def normalize_article_title(text: str) -> str:
    """«Стаття 7 - 1 .» -> «Стаття 7-1.» ; «Стаття  1 .» -> «Стаття 1.»"""
    if not text:
        return text
    # «Стаття 7 - 1 .» -> «Стаття 7-1.»
    text = re.sub(r"(\d)\s*-\s*(\d)\s*\.", r"\1-\2.", text)
    # «Стаття 1 .» -> «Стаття 1.»
    text = re.sub(r"(\d)\s*\.", r"\1.", text)
    # множинні пробіли
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Парсинг структури документа
# ---------------------------------------------------------------------------
def extract_title(html: str) -> str:
    """Витягує назву закону українською з <title> або першого <h1>."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
    if m:
        t = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if t:
            return t
    return "Повний текст документа"


def extract_meta(html: str) -> str:
    """Витягує мета-рядок (статус, редакція) з .doc-meta, якщо є."""
    m = re.search(
        r'<div[^>]*class="[^"]*doc-meta[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I
    )
    if m:
        inner = m.group(1)
        # прибрати бейджі-спани, залишити текст
        inner = re.sub(
            r"<span[^>]*class=\"[^\"]*badge[^\"]*\"[^>]*>.*?</span>",
            "",
            inner,
            flags=re.S | re.I,
        )
        inner = re.sub(r"<[^>]+>", " ", inner)
        inner = re.sub(r"\s+", " ", inner).strip()
        if inner:
            return inner
    return ""


def extract_footer(html: str) -> str:
    """Витягує текст футера «Повний текст документа…» з .doc-footer."""
    m = re.search(
        r'<div[^>]*class="[^"]*doc-footer[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I
    )
    if m:
        inner = re.sub(r"<[^>]+>", " ", m.group(1))
        inner = re.sub(r"\s+", " ", inner).strip()
        if inner:
            return inner
    return "Повний текст документа"


def split_long_paragraph(text: str, limit: int = 1400) -> list:
    """Розбиває довгий абзац на читабельні частини за межами речень."""
    if len(text) <= limit:
        return [text]
    parts = []
    current = ""
    # Розбиваємо за реченнями (крапка + пробіл + велика літера)
    sentences = re.split(r"(?<=[.!?])\s+(?=[А-ЯІЇЄҐA-Z«\"(])", text)
    for s in sentences:
        if len(current) + len(s) + 1 > limit and current:
            parts.append(current.strip())
            current = s
        else:
            current = (current + " " + s).strip()
    if current:
        parts.append(current.strip())
    return parts


# ---------------------------------------------------------------------------
# Токенізація тіла документа
# ---------------------------------------------------------------------------
_BLOCK_TAG = r"(?:h[1-6]|p|pre|div|details|table|ul|ol|blockquote|section|article|figure|hr|center|li)"

def tokenize_body(body: str) -> list:
    """Розбиває тіло на top-level блоки, ЗБЕРІГАЮЧИ всі типи елементів
    (pre, table, ul, ol, div, p, h1-6, details, blockquote…)."""
    tokens = []
    pos = 0
    n = len(body)
    # Патерн для початку блоку: <tag ...> або <tag>
    open_re = re.compile(r"<(" + _BLOCK_TAG + r")(\s[^>]*)?>", re.I)
    while pos < n:
        m = open_re.search(body, pos)
        if not m:
            # Залишок тексту (текст поза блоками)
            rest = body[pos:].strip()
            if rest:
                tokens.append(rest)
            break
        # Текст до відкриваючого тега
        if m.start() > pos:
            pre = body[pos:m.start()].strip()
            if pre:
                tokens.append(pre)
        tag = m.group(1).lower()
        start = m.start()
        # Знаходимо відповідний закриваючий тег (враховуючи вкладеність)
        end = find_closing(body, start, tag)
        if end is None:
            # Немає закриваючого тега — беремо до кінця
            tokens.append(body[start:].strip())
            break
        tokens.append(body[start:end])
        pos = end
    return tokens


def find_closing(text: str, open_pos: int, tag: str) -> int:
    """Повертає позицію після закриваючого тега </tag>, враховуючи вкладеність."""
    open_re = re.compile(r"<" + tag + r"(\s[^>]*)?>", re.I)
    close_re = re.compile(r"</" + tag + r"\s*>", re.I)
    depth = 0
    pos = open_pos
    while True:
        om = open_re.search(text, pos)
        cm = close_re.search(text, pos)
        if cm is None:
            return None
        if om is not None and om.start() < cm.start():
            depth += 1
            pos = om.end()
        else:
            depth -= 1
            if depth == 0:
                return cm.end()
            pos = cm.end()


# ---------------------------------------------------------------------------
# Побудова еталонного HTML
# ---------------------------------------------------------------------------
def build_etalon(html: str) -> str:
    """Перетворює сирий/старий HTML закону в еталонну структуру."""
    title = extract_title(html)
    meta = extract_meta(html)
    footer = extract_footer(html)

    # Витягуємо тіло: .doc-body або body
    body_m = re.search(
        r'<div[^>]*class="[^"]*doc-body[^"]*"[^>]*>(.*?)</div>\s*<div[^>]*class="[^"]*doc-footer',
        html,
        re.S | re.I,
    )
    if not body_m:
        body_m = re.search(
            r'<div[^>]*class="[^"]*doc-body[^"]*"[^>]*>(.*?)</div>', html, re.S | re.I
        )
    if not body_m:
        body_m = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
    if not body_m:
        return html
    body = body_m.group(1)

    # Видаляємо вже наявні обгортки статей, щоб не дублювати
    body = re.sub(r'<div[^>]*class="[^"]*law-article[^"]*"[^>]*>', "", body)
    body = re.sub(r"</div>\s*(?=<h3|<h2|<details|</div>)", "", body)

    # Токенізуємо top-level елементи тіла, ЗБЕРІГАЮЧИ всі типи (pre, table, ul, ol, div, p, h1-6, details, blockquote…)
    tokens = tokenize_body(body)

    articles = []  # list of (title_text, [html_chunks])
    current_title = None
    current_chunks = []
    preamble = []  # блоки до першої статті (преамбула, details змін)

    def flush_article():
        nonlocal current_title, current_chunks
        if current_title is not None:
            articles.append((current_title, current_chunks))
        current_title = None
        current_chunks = []

    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue
        # Заголовок статті
        hm = re.match(r"<h3[^>]*>(.*?)</h3>", tok, re.S | re.I)
        if hm:
            title_text = re.sub(r"<[^>]+>", "", hm.group(1)).strip()
            title_text = normalize_article_title(title_text)
            if re.match(r"^Стаття\s*\d", title_text, re.I):
                flush_article()
                current_title = title_text
                continue
            # інакше — це звичайний h3 (не стаття), додаємо до поточного блоку
            if current_title is not None:
                current_chunks.append(tok)
            else:
                preamble.append(tok)
            continue
        # Розділ (h2) — початок нового розділу, але не статті
        hm2 = re.match(r"<h2[^>]*>(.*?)</h2>", tok, re.S | re.I)
        if hm2:
            if current_title is not None:
                current_chunks.append(tok)
            else:
                preamble.append(tok)
            continue
        # Абзац
        pm = re.match(r"<p[^>]*>(.*?)</p>", tok, re.S | re.I)
        if pm:
            inner = pm.group(1)
            inner = re.sub(r"<[^>]+>", "", inner)
            inner = cleanup_text(inner)
            if not inner.strip():
                continue
            for part in split_long_paragraph(inner):
                part_html = f"<p>{part}</p>"
                if current_title is not None:
                    current_chunks.append(part_html)
                else:
                    preamble.append(part_html)
            continue
        # details (зміни), pre, div, table, ul, ol та інші блоки
        if current_title is not None:
            current_chunks.append(tok)
        else:
            preamble.append(tok)

    flush_article()

    # Збираємо еталонний HTML
    out = []
    out.append('<!DOCTYPE html><html lang="uk"><head><meta charset="UTF-8">')
    out.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    out.append(f"<title>{title}</title>")
    out.append("""
<style>
:root{
  --bg:#ffffff; --text:#1a1a1a; --muted:#5b6470;
  --border:#d0d7de; --accent:#1a6fb5; --accent-soft:#e7f0f8;
  --green:#1a7f37; --red:#cf222e;
}
@media (prefers-color-scheme: dark){:root{
  --bg:#0d1117; --text:#e6edf3; --muted:#8b949e;
  --border:#30363d; --accent:#58a6ff; --accent-soft:#1f2a3a;
  --green:#3fb950; --red:#f85149;
}}
*{box-sizing:border-box; margin:0; padding:0;}
html{scroll-behavior:smooth;}
body{
  background:var(--bg); color:var(--text);
  font-family:Georgia,'Times New Roman',serif;
  line-height:1.75; font-size:16px;
}
.law{max-width:860px; margin:0 auto;}
/* Sticky-шапка: текст скролиться ПІД нею, ніколи не перекривається */
.law-header{
  position:sticky; top:0; z-index:100;
  background:var(--bg); border-bottom:2px solid var(--accent);
  padding:14px 20px; box-shadow:0 2px 8px rgba(0,0,0,0.06);
}
.law-header h1{
  font-size:1.35rem; line-height:1.35; color:var(--accent);
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  font-weight:700;
}
.law-meta{
  margin-top:6px; font-size:0.85rem; color:var(--muted);
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
.law-content{padding:20px 20px 40px;}
/* Блок статті з відступами */
.law-article{
  margin:0 0 22px; padding:0 0 18px;
  border-bottom:1px solid var(--border);
}
.law-article:last-child{border-bottom:none;}
.law-article-title{
  font-size:1.05rem; font-weight:700; margin:0 0 10px;
  padding:10px 14px; background:var(--accent-soft);
  border-left:4px solid var(--accent); border-radius:0 8px 8px 0;
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  scroll-margin-top:90px;
}
.law-content h2{
  font-size:1.15rem; margin:26px 0 12px; color:var(--accent);
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  border-bottom:1px solid var(--border); padding-bottom:4px;
  scroll-margin-top:90px;
}
.law-content p{
  margin:12px 0; text-align:left; line-height:1.75;
}
.law-content p + p{margin-top:14px;}
.law-content .note{
  margin:14px 0; padding:12px 14px; background:var(--accent-soft);
  border-left:4px solid var(--accent); border-radius:0 8px 8px 0;
  font-size:0.9rem; color:var(--muted); font-style:italic;
}
.law-content details.law-amendments{
  margin:14px 0; border:1px solid var(--border); border-radius:8px;
  background:var(--accent-soft);
}
.law-content details.law-amendments summary{
  cursor:pointer; padding:10px 14px; font-weight:600;
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  color:var(--accent); user-select:none;
}
.law-content details.law-amendments summary:hover{background:rgba(0,0,0,0.03);}
.law-content details.law-amendments .law-amendments-body{
  padding:0 14px 12px; font-size:0.9rem; color:var(--muted);
  max-height:320px; overflow-y:auto; line-height:1.6;
}
.law-footer{
  margin-top:10px; padding:14px 20px; border-top:1px solid var(--border);
  font-size:0.85rem; color:var(--muted);
  font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
}
</style></head><body><div class="law">""")

    # Шапка
    out.append('<header class="law-header">')
    out.append(f"<h1>{title}</h1>")
    if meta:
        out.append(f'<div class="law-meta">{meta}</div>')
    out.append("</header>")

    # Контент
    out.append('<div class="law-content">')
    # Преамбула
    for chunk in preamble:
        out.append(chunk)
    # Статті
    for idx, (art_title, chunks) in enumerate(articles, start=1):
        out.append(f'<div class="law-article" id="article-{idx}">')
        out.append(f'<h3 class="law-article-title">{art_title}</h3>')
        for chunk in chunks:
            out.append(chunk)
        out.append("</div>")
    out.append("</div>")

    # Футер
    out.append(f'<footer class="law-footer">{footer}</footer>')
    out.append("</div></body></html>")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Обробка файлів
# ---------------------------------------------------------------------------
def reformat_file(path: str, dry_run: bool = False) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    new_html = build_etalon(html)
    if new_html == html:
        return {"path": path, "changed": False, "articles": 0}

    articles = len(re.findall(r'class="law-article"', new_html))
    if not dry_run:
        bak = path + ".bak"
        if not os.path.exists(bak):
            os.rename(path, bak)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_html)
    return {"path": path, "changed": True, "articles": articles}


def main():
    dry_run = "--dry-run" in sys.argv
    targets = [a for a in sys.argv[1:] if not a.startswith("--")]
    if targets:
        files = [
            t if os.path.isabs(t) else os.path.join(LAWS_DIR, os.path.basename(t))
            for t in targets
        ]
    else:
        files = sorted(glob.glob(os.path.join(LAWS_DIR, "*.html")))

    changed = 0
    total_articles = 0
    for path in files:
        if not os.path.exists(path):
            print(f"⚠️  Файл не знайдено: {path}")
            continue
        res = reformat_file(path, dry_run)
        if res["changed"]:
            changed += 1
            total_articles += res["articles"]
            mode = "DRY-RUN" if dry_run else "OK"
            print(f"[{mode}] {os.path.basename(path)} — {res['articles']} статей")
        else:
            print(f"[=] {os.path.basename(path)} — без змін")

    print(
        f"\nОброблено файлів: {len(files)}, змінено: {changed}, статей: {total_articles}"
    )
    if dry_run:
        print(
            "Це був dry-run — файли НЕ змінено. Запустіть без --dry-run для застосування."
        )


if __name__ == "__main__":
    main()
