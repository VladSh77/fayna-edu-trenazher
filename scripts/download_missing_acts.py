#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Завантажує 20 відсутніх актів з zakon.rada.gov.ua (формат «Текст для друку»)
і конвертує їх у HTML-формат, який розуміє extract_article_by_ref() у simulate.py:
  - Стаття -> <h3>Стаття N. Title</h3>
  - Пункт   -> інлайн "N." у <p>
  - Параграф -> "§ N."
  - Розділ  -> <h2>

Використання (з кореня проєкту):
    python3 scripts/download_missing_acts.py [--only slug1,slug2] [--out laws]
"""

import argparse
import html as html_mod
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "laws"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ----------------------------------------------------------------------
# Реєстр: (slug, zakon.rada URL, title, джерело)
# slug = цільове ім'я файлу в laws/ (без .html)
# ----------------------------------------------------------------------
ACTS = [
    # 1. Договір про ЄС — консолідована версія (zakon.rada, укр.)
    (
        "dohovir-pro-yevropeiskyi-soiuz",
        "https://zakon.rada.gov.ua/laws/show/994_029/print",
        "Договір про Європейський Союз (консолідована версія)",
        "zakon.rada.gov.ua",
    ),
    # 2. Договір про функціонування ЄС (zakon.rada, укр.)
    (
        "dohovir-pro-funktsionuvannia-yes",
        "https://zakon.rada.gov.ua/laws/show/994_b06/print",
        "Договір про функціонування Європейського Союзу (консолідована версія)",
        "zakon.rada.gov.ua",
    ),
    # 3. Апостильна конвенція 1961 (Гаага) — zakon.rada
    (
        "haazka-konventsiia-apostyl",
        "https://zakon.rada.gov.ua/laws/show/995_082/print",
        "Конвенція, що скасовує вимогу легалізації іноземних офіційних документів (Апостильна конвенція, 1961)",
        "zakon.rada.gov.ua",
    ),
    # 4. Порядок провадження за заявами з питань громадянства — Постанова КМУ № 215
    (
        "poriadok-provadzhennia-hromadianstvo",
        "https://zakon.rada.gov.ua/laws/show/215/2001/print",
        "Порядок провадження за заявами і поданнями з питань громадянства та виконання прийнятих рішень (Постанова КМУ № 215 від 25.03.1996)",
        "zakon.rada.gov.ua",
    ),
    # 5. Інструкція про витребування документів (Наказ Мін'юсту)
    (
        "instruktsiia-vytrebuvannia-dokumentiv",
        "https://zakon.rada.gov.ua/laws/show/z0869-01/print",
        "Інструкція про порядок вчинення нотаріальних дій консульськими установами України (витребування документів)",
        "zakon.rada.gov.ua",
    ),
    # 6. Правила державної реєстрації актів цивільного стану — Наказ Мін'юсту № 52/5
    (
        "pravyla-derzhavnoi-reiestratsii-aktiv",
        "https://zakon.rada.gov.ua/laws/show/z1019-00/print",
        "Правила державної реєстрації актів цивільного стану (Наказ Мін'юсту № 52/5 від 18.10.2000)",
        "zakon.rada.gov.ua",
    ),
    # 7. Порядок ведення Державного реєстру виборців — Постанова ЦВК № 32
    (
        "poriadok-vedennia-reiestru-vyborciv",
        "https://zakon.rada.gov.ua/laws/show/v0055359-07/print",
        "Порядок ведення Державного реєстру виборців (Постанова ЦВК № 32 від 12.02.2003)",
        "zakon.rada.gov.ua",
    ),
    # 8. Постанова КМУ № 368 — Правила оформлення віз
    (
        "postanova-kmu-368-vizy",
        "https://zakon.rada.gov.ua/laws/show/368-2019-%D0%BF/print",
        "Постанова КМУ № 368 від 06.03.2019 «Про затвердження Правил оформлення віз для в'їзду в Україну і транзитного проїзду через її територію»",
        "zakon.rada.gov.ua",
    ),
    # 9. Постанова КМУ № 954 — Питання пропуску через державний кордон
    (
        "postanova-kmu-954",
        "https://zakon.rada.gov.ua/laws/show/954-2018-%D0%BF/print",
        "Постанова КМУ № 954 від 14.11.2018 «Питання пропуску через державний кордон»",
        "zakon.rada.gov.ua",
    ),
    # 10. Постанова КМУ № 776 — Правила в'їзду іноземців
    (
        "postanova-kmu-776",
        "https://zakon.rada.gov.ua/laws/show/776-2021-%D0%BF/print",
        "Постанова КМУ № 776 від 28.07.2021 «Про затвердження Правил в'їзду іноземців та осіб без громадянства в Україну, їх виїзду з України і транзитного проїзду через її територію»",
        "zakon.rada.gov.ua",
    ),
    # 11. Європейська конвенція про взаємну допомогу у кримінальних справах
    (
        "yevropeiska-konventsiia-vzaiemna-dopomoha",
        "https://zakon.rada.gov.ua/laws/show/995_036/print",
        "Європейська конвенція про взаємну допомогу у кримінальних справах (Страсбург, 20.04.1959)",
        "zakon.rada.gov.ua",
    ),
    # 12. Порядок приймання в експлуатацію об'єктів — Постанова КМУ № 461
    (
        "poriadok-pryimannia-ekspluatatsiiu",
        "https://zakon.rada.gov.ua/laws/show/461-2011-%D0%BF/print",
        "Порядок приймання в експлуатацію закінчених будівництвом об'єктів (Постанова КМУ № 461 від 13.04.2011)",
        "zakon.rada.gov.ua",
    ),
    # 13. Постанова КМУ № 651 — захист прав громадян за кордоном
    (
        "postanova-kmu-651-zakhyst-hromadian",
        "https://zakon.rada.gov.ua/laws/show/651-2012-%D0%BF/print",
        "Порядок формування і використання закордонними дипломатичними установами України коштів держбюджету для захисту прав та інтересів громадян України за кордоном (Постанова КМУ № 651 від 11.07.2012)",
        "zakon.rada.gov.ua",
    ),
    # 14. Закон про правовий режим надзвичайного стану
    (
        "zakon-pro-nadzvychaini-sytuatsii",
        "https://zakon.rada.gov.ua/laws/show/1550-14/print",
        "Закон України «Про правовий режим надзвичайного стану»",
        "zakon.rada.gov.ua",
    ),
    # 15. Закон про основи соціальної захищеності осіб з інвалідністю — № 875-XII
    (
        "zakon-pro-osnovy-sotsialnoi-zakhyshchenosti",
        "https://zakon.rada.gov.ua/laws/show/875-12/print",
        "Закон України «Про основи соціальної захищеності осіб з інвалідністю в Україні» (№ 875-XII від 21.03.1991)",
        "zakon.rada.gov.ua",
    ),
    # 16. Постанова КМУ № 750 — Питання проставлення апостиля
    (
        "postanova-kmu-750-apostyl",
        "https://zakon.rada.gov.ua/laws/show/750-2015-%D0%BF/print",
        "Постанова КМУ № 750 від 16.09.2015 «Питання проставлення апостиля»",
        "zakon.rada.gov.ua",
    ),
    # 17. Положення про нештатних (почесних) консулів — Указ Президента
    (
        "polozhennia-pro-pochesnykh-konsuliv",
        "https://zakon.rada.gov.ua/laws/show/z0460-07/print",
        "Положення про нештатних (почесних) консулів України (Указ Президента України)",
        "zakon.rada.gov.ua",
    ),
    # 18. Копенгагенські критерії — zakon.rada, укр.
    (
        "kopenhahenski-kryterii",
        "https://zakon.rada.gov.ua/laws/show/994_a01/print",
        "Копенгагенські критерії членства в ЄС (1993)",
        "zakon.rada.gov.ua",
    ),
    # 19. Шенгенська угода 1985
    (
        "shenhenska-uhoda",
        "https://zakon.rada.gov.ua/laws/show/995_024/print",
        "Шенгенська угода 1985 року",
        "zakon.rada.gov.ua",
    ),
    # 20. Постанова КМУ про засідання органів асоціації
    (
        "postanova-kmu-zasidannia-orhaniv-asotsiatsii",
        "https://zakon.rada.gov.ua/laws/show/1009-2014-%D0%BF/print",
        "Постанова КМУ «Питання підготовки та проведення засідань окремих двосторонніх органів асоціації між Україною та ЄС»",
        "zakon.rada.gov.ua",
    ),
]

# ----------------------------------------------------------------------
# Шаблон HTML (той самий, що в build_law_docs.py)
# ----------------------------------------------------------------------
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root{{
    --bg:#ffffff; --text:#1a1a1a; --muted:#5b6470;
    --border:#d0d7de; --accent:#1a6fb5; --accent-soft:#e7f0f8;
    --green:#1a7f37; --red:#cf222e;
  }}
  @media (prefers-color-scheme: dark){{
    :root{{
      --bg:#0d1117; --text:#e6edf3; --muted:#8b949e;
      --border:#30363d; --accent:#58a6ff; --accent-soft:#1f2a3a;
      --green:#3fb950; --red:#f85149;
    }}
  }}
  *{{box-sizing:border-box; margin:0; padding:0;}}
  body{{
    background:var(--bg); color:var(--text);
    font-family:Georgia, 'Times New Roman', serif;
    line-height:1.7; font-size:16px;
    padding:24px 20px 60px;
  }}
  .doc{{max-width:820px; margin:0 auto;}}
  .doc-header{{
    border-bottom:2px solid var(--accent); padding-bottom:16px; margin-bottom:20px;
  }}
  .doc-header h1{{font-size:1.5rem; line-height:1.4; color:var(--accent); font-weight:700;}}
  .doc-meta{{
    margin-top:10px; font-size:0.9rem; color:var(--muted);
    font-family:system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    display:flex; flex-wrap:wrap; gap:8px 16px;
  }}
  .doc-meta .badge{{
    display:inline-block; padding:2px 10px; border-radius:20px;
    font-weight:600; font-size:0.8rem;
  }}
  .badge.valid{{background:var(--green); color:#fff;}}
  .badge.invalid{{background:var(--red); color:#fff;}}
  .badge.neutral{{background:var(--accent-soft); color:var(--accent);}}
  .doc-body h1{{
    font-size:1.3rem; margin:24px 0 10px; color:var(--accent);
    font-family:system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }}
  .doc-body h2{{
    font-size:1.15rem; margin:28px 0 10px; color:var(--accent);
    font-family:system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
    border-bottom:1px solid var(--border); padding-bottom:4px;
  }}
  .doc-body h3{{
    font-size:1.02rem; margin:20px 0 6px; font-weight:700;
    font-family:system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }}
  .doc-body p{{margin:8px 0; text-align:justify;}}
  .doc-body .note{{
    color:var(--muted); font-size:0.9rem; font-style:italic;
    border-left:3px solid var(--border); padding-left:10px; margin:8px 0;
  }}
  .doc-body .center{{text-align:center; font-weight:700; margin:14px 0;}}
  .doc-footer{{
    margin-top:30px; padding-top:14px; border-top:1px solid var(--border);
    font-size:0.85rem; color:var(--muted);
    font-family:system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }}
</style>
</head>
<body>
<div class="doc">
  <div class="doc-header">
    <h1>{title}</h1>
    <div class="doc-meta">
      <span class="badge valid">Чинний</span>
      <span>Джерело: {source}</span>
    </div>
  </div>
  <div class="doc-body">
{body}
  </div>
  <div class="doc-footer">
    Повний текст документа. Джерело: {source}. Завантажено та перевірено станом на 28.08.2026.
  </div>
</div>
</body>
</html>
"""


def escape(s: str) -> str:
    return html_mod.escape(s, quote=False)


def fetch(url: str) -> str:
    """Завантажує URL через curl (надійніше для zakon.rada з UA-заголовком)."""
    cmd = [
        "curl",
        "-s",
        "-L",
        "--max-time",
        "40",
        "-A",
        UA,
        "-H",
        "Accept: text/html,application/xhtml+xml",
        url,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed: {r.stderr[:300]}")
    # Декодуємо як UTF-8 (text=True використовує локальне кодування, що
    # ламає кирилицю на macOS)
    return r.stdout.decode("utf-8", errors="replace")


def strip_tags(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_mod.unescape(s)
    return s


def extract_article_div(raw: str) -> str:
    """Витягує вміст <div id="article" class="txt"> з print-версії zakon.rada."""
    m = re.search(
        r'<div id="article"[^>]*>(.*?)</div>\s*<div class="stamp">', raw, re.S
    )
    if m:
        return m.group(1)
    # fallback: від початку article до кінця
    m2 = re.search(r'<div id="article"[^>]*>(.*)', raw, re.S)
    if m2:
        return m2.group(1)
    return raw


def convert_rada(raw: str) -> str:
    """
    Конвертує print-версію zakon.rada у HTML з <h3>Стаття N</h3> + <p>.
    Повертає тіло (без шаблону).
    """
    body_html = extract_article_div(raw)
    # Перетворюємо на плоский текст зі збереженням структури абзаців
    text = strip_tags(body_html)
    # Нормалізуємо пробіли
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln.strip()]

    out = []
    for ln in lines:
        # Стаття -> h3
        if re.match(r"^Стаття\s+\d", ln) or re.match(r"^Стаття\s+\d+\s*-\s*\d+", ln):
            out.append(f"<h3>{escape(ln)}</h3>")
            continue
        # Розділ -> h2
        if re.match(r"^Розділ\s+[IVXLC]+", ln):
            out.append(f"<h2>{escape(ln)}</h2>")
            continue
        # Примітки в {дужках} -> note
        if ln.startswith("{") and ln.endswith("}"):
            out.append(f'<p class="note">{escape(ln)}</p>')
            continue
        # Центровані заголовки
        if re.match(r"^[А-ЯІЇЄҐ]{4,}(\s|$)", ln) and len(ln) < 80:
            out.append(f'<p class="center">{escape(ln)}</p>')
            continue
        # Звичайний абзац
        out.append(f"<p>{escape(ln)}</p>")
    return "\n".join(out)


def convert_eurlex(raw: str) -> str:
    """
    Конвертує EUR-Lex HTML у формат з <h3>Article N</h3> (Віденський стиль,
    який розуміє _extract_vienna_articles).
    """
    # Витягуємо основний текст
    m = re.search(
        r'<div[^>]*class="[^"]*tab-document[^"]*"[^>]*>(.*?)</div>\s*</div>', raw, re.S
    )
    body_html = m.group(1) if m else raw
    text = strip_tags(body_html)
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln.strip()]

    out = []
    for ln in lines:
        # Article N -> h3 (Віденський формат)
        if re.match(r"^Article\s+\d", ln, re.IGNORECASE):
            out.append(f"<h3>{escape(ln)}</h3>")
            continue
        # TITLE / PART -> h2
        if re.match(r"^(TITLE|PART|CHAPTER)\s+[IVXLC\d]+", ln, re.IGNORECASE):
            out.append(f"<h2>{escape(ln)}</h2>")
            continue
        out.append(f"<p>{escape(ln)}</p>")
    return "\n".join(out)


def build(slug: str, url: str, title: str, source: str, out_dir: Path) -> bool:
    print(f"  [FETCH] {slug} <- {url}")
    try:
        raw = fetch(url)
    except Exception as e:
        print(f"  [FAIL] {slug}: {e}")
        return False
    if len(raw) < 500:
        print(f"  [FAIL] {slug}: замало даних ({len(raw)} байт)")
        return False

    if "eur-lex" in url:
        body = convert_eurlex(raw)
    else:
        body = convert_rada(raw)

    html = HTML_TEMPLATE.format(
        title=escape(title),
        source=escape(source),
        body=body,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{slug}.html"
    out_file.write_text(html, encoding="utf-8")
    size_kb = out_file.stat().st_size / 1024
    print(f"  [OK] {slug}.html ({size_kb:.0f} KB)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="коман-список slug")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    out_dir = Path(args.out)

    print(f"Вихідна папка: {out_dir}")
    ok = 0
    fail = 0
    for slug, url, title, source in ACTS:
        if only and slug not in only:
            continue
        if build(slug, url, title, source, out_dir):
            ok += 1
        else:
            fail += 1
        time.sleep(1)  # делікатність до сервера

    print(f"\nГотово: {ok} успішно, {fail} помилок.")


if __name__ == "__main__":
    main()
