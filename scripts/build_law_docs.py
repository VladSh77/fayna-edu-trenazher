#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конвертує MD-файли законів/актів з бази знань docs-sorter у читабельні
HTML-документи у папці laws/ тренажера МЗС.

Кожен акт стає окремим standalone HTML-файлом, відформатованим як юридичний
документ (Розділ -> h2, Стаття -> h3, абзаци -> p), з метаданими (статус,
редакція) у шапці. Ці файли завантажуються в модальне вікно тренажера
замість зовнішніх посилань на zakon.rada.gov.ua.

Використання:
  python3 build_law_docs.py [--only slug1,slug2] [--out DIR]
"""

import argparse
import re
from pathlib import Path

# --- шляхи ---
WORK = Path(__file__).resolve().parent
PROJECT = WORK.parent
KB_MD = Path(
    "/Users/kobzar/Library/Mobile Documents/com~apple~CloudDocs/📚 База знань/_MD"
)
DEFAULT_OUT = PROJECT / "laws"

# --- реєстр: slug MD -> (ключові слова для LEGISLATION, назва акта) ---
# slug — ім'я файлу в базі знань (без .md)
# keys — ключові слова, які зустрічаються в explain.ref і мають мапитись на цей акт
# title — коротка назва для шапки документа
ACTS = [
    (
        "vyborchyi-kodeks-ukrainy",
        ["Виборчий кодекс", "вибори Президента", "вибори народних депутатів"],
        "Виборчий кодекс України",
    ),
    (
        "zakon-pro-hromadianstvo",
        ["громадянство України"],
        "Закон України «Про громадянство України»",
    ),
    (
        "zakon-pro-dyplomatychnu-sluzhbu",
        ["дипломатичну службу"],
        "Закон України «Про дипломатичну службу»",
    ),
    ("zakon-pro-notariat", ["нотаріат"], "Закон України «Про нотаріат»"),
    (
        "zakon-pro-pravovyi-status-inozemtsiv",
        ["правовий статус іноземців", "правовий статус осіб"],
        "Закон України «Про правовий статус іноземців та осіб без громадянства»",
    ),
    (
        "zakon-pro-mizhnarodni-dohovory",
        ["міжнародні договори України"],
        "Закон України «Про міжнародні договори України»",
    ),
    (
        "zakon-pro-derzhavnu-reiestratsiiu-aktiv-tsyvilnoho-stanu",
        ["державну реєстрацію актів цивільного стану"],
        "Закон України «Про державну реєстрацію актів цивільного стану»",
    ),
    (
        "zakon-pro-derzhavnyi-reiestr-vyborciv",
        ["Державний реєстр виборців"],
        "Закон України «Про Державний реєстр виборців»",
    ),
    (
        "zakon-pro-upravlinnia-obiektamy-derzhavnoi-vlasnosti",
        ["управління об'єктами державної власності"],
        "Закон України «Про управління об'єктами державної власності»",
    ),
    (
        "zakon-pro-elektronni-dokumenty",
        ["електронні документи"],
        "Закон України «Про електронні документи та електронний документообіг»",
    ),
    (
        "rehlament-verkhovnoi-rady",
        ["Регламент Верховної Ради"],
        "Закон України «Про Регламент Верховної Ради України»",
    ),
    (
        "pravyla-oformlennia-viz",
        [
            "Правила оформлення віз",
            "№ 118",
            "консульського збору",
            "виїзних консульських обслуговувань",
            "матеріальної допомоги громадянам України за кордоном",
            "повернення до України позбавлених батьківського піклування дітей",
            "Консульський збір України",
        ],
        "Постанова КМУ № 118 «Про затвердження Правил оформлення віз»",
    ),
    ("postanova-kmu-645", ["№ 645"], "Постанова КМУ від 17.07.2019 № 645"),
    (
        "typova-instruktsiia-dilovodstva",
        ["Типової інструкції з діловодства", "діловодство"],
        "Постанова КМУ № 736 «Про затвердження Типової інструкції з діловодства»",
    ),
    (
        "rehlament-kabinetu-ministriv",
        ["Регламент Кабінету Міністрів"],
        "Постанова КМУ № 950 «Про затвердження Регламенту Кабінету Міністрів України»",
    ),
    (
        "nakaz-minfinu-879-inventaryzatsiia",
        ["№ 879", "інвентаризацію"],
        "Наказ Мінфіну № 879 «Про затвердження Положення про інвентаризацію»",
    ),
    (
        "videnska-konventsiia-pravo-mizhnarodnykh-dohovoriv",
        ["Віденська конвенція про право міжнародних договорів"],
        "Віденська конвенція про право міжнародних договорів (1969)",
    ),
    (
        "videnska-konventsiia-dyplomatychni-znosyny",
        ["Віденська конвенція про дипломатичні зносини"],
        "Віденська конвенція про дипломатичні зносини (1961)",
    ),
    (
        "videnska-konventsiia-konsulski-znosyny",
        ["Віденська конвенція про консульські зносини"],
        "Віденська конвенція про консульські зносини (1963)",
    ),
    (
        "uhoda-pro-asotsiatsiiu-ukraina-yes",
        ["Угода про асоціацію"],
        "Угода про асоціацію між Україною та ЄС (2014)",
    ),
    (
        "postanova-kmu-55-dokumentuvannia",
        ["документування управлінської діяльності", "документування"],
        "Постанова КМУ № 55 «Деякі питання документування управлінської діяльності»",
    ),
    (
        "polozhennia-pro-mzs",
        ["Положення про Міністерство закордонних справ", "Положення про МЗС"],
        "Постанова КМУ № 281 «Про затвердження Положення про МЗС України»",
    ),
    (
        "nakaz-kaznacheistva-130-typovi-formy-zapasiv",
        ["№ 130", "Державного казначейства"],
        "Наказ Держказначейства № 130 «Про затвердження типових форм обліку та списання запасів»",
    ),
    # --- Додаткові акти, додані для повної імітації (завдання 23) ---
    (
        "zakon-pro-yedynyi-derzhavnyi-demohrafichnyi-reiestr",
        ["Єдиний державний демографічний реєстр", "демографічний реєстр"],
        "Закон України «Про Єдиний державний демографічний реєстр»",
    ),
    (
        "konsulskyi-statut-ukrainy",
        ["Консульський статут", "консульську службу", "консульські установи"],
        "Консульський статут України (Указ Президента від 02.04.1994 № 127/94)",
    ),
    (
        "kryminalnyi-protsesualnyi-kodeks-ukrainy",
        ["Кримінальний процесуальний кодекс"],
        "Кримінальний процесуальний кодекс України",
    ),
    (
        "kodeks-ukrainy-pro-administratyvni-pravoporushennia",
        [
            "Кодекс України про адміністративні правопорушення",
            "адміністративні правопорушення",
        ],
        "Кодекс України про адміністративні правопорушення",
    ),
    (
        "zakon-pro-okhoronu-dytynstva",
        ["охорону дитинства"],
        "Закон України «Про охорону дитинства»",
    ),
    (
        "tsyvilnyi-kodeks-ukrainy",
        ["Цивільний кодекс"],
        "Цивільний кодекс України",
    ),
    (
        "simeinyi-kodeks-ukrainy",
        ["Сімейний кодекс"],
        "Сімейний кодекс України",
    ),
    (
        "kryminalnyi-kodeks-ukrainy",
        ["Кримінальний кодекс"],
        "Кримінальний кодекс України",
    ),
    (
        "zakon-pro-natsionalnu-politsiiu",
        ["Національну поліцію", "Національної поліції"],
        "Закон України «Про Національну поліцію»",
    ),
    (
        "zakon-pro-mizhnarodne-pryvatne-pravo",
        ["міжнародне приватне право"],
        "Закон України «Про міжнародне приватне право»",
    ),
]

# --- шаблон HTML-документа ---
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
      {meta_badges}
      {meta_extra}
    </div>
  </div>
  <div class="doc-body">
{body}
  </div>
  <div class="doc-footer">
    Повний текст документа. Джерело: {source}. Станом на {redaktsiia}.
  </div>
</div>
</body>
</html>
"""


def parse_frontmatter(text: str):
    """Повертає (meta_dict, body_text) з MD-файлу."""
    meta = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = text[end + 4 :].strip()
            return meta, body
    return {}, text.strip()


def md_to_html(body: str) -> str:
    """Конвертує тіло MD (плоский текст з рядками) у HTML зі структурою."""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    out = []
    for ln in lines:
        # Markdown-заголовок (# ...) -> h1
        m = re.match(r"^#{1,6}\s+(.*)$", ln)
        if m:
            out.append(f"<h1>{escape(m.group(1))}</h1>")
            continue
        # Розділ -> h2
        if re.match(r"^Розділ\s+[IVXLC]+", ln):
            out.append(f"<h2>{escape(ln)}</h2>")
            continue
        # Стаття -> h3
        if re.match(r"^Стаття\s+\d", ln) or re.match(r"^Стаття\s+\d+\s*-\s*\d+", ln):
            out.append(f"<h3>{escape(ln)}</h3>")
            continue
        # Примітки в {дужках} -> note
        if ln.startswith("{") and ln.endswith("}"):
            out.append(f'<p class="note">{escape(ln)}</p>')
            continue
        # Центровані заголовки (ЗАКОН УКРАЇНИ, РОЗДІЛ тощо) -> center
        if re.match(r"^[А-ЯІЇЄҐ]{4,}(\s|$)", ln) and len(ln) < 80:
            out.append(f'<p class="center">{escape(ln)}</p>')
            continue
        # Звичайний абзац
        out.append(f"<p>{escape(ln)}</p>")
    return "\n".join(out)


def escape(s: str) -> str:
    return s.replace("&", "&").replace("<", "<").replace(">", ">")


def build_doc(slug: str, keys, title: str, out_dir: Path) -> bool:
    src = KB_MD / f"{slug}.md"
    if not src.exists():
        print(f"  [SKIP] {slug}: файл не знайдено в базі знань")
        return False
    text = src.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)

    status = meta.get("status", "")
    redaktsiia = meta.get("redaktsiia", "—")
    source = meta.get("джерело", "zakon.rada.gov.ua")

    if status:
        cls = (
            "valid"
            if "чинн" in status.lower()
            else ("invalid" if "втрат" in status.lower() else "neutral")
        )
        badge = f'<span class="badge {cls}">{escape(status)}</span>'
    else:
        badge = ""
    meta_badges = badge
    meta_extra = (
        f"<span>Редакція: {escape(redaktsiia)}</span>" if redaktsiia != "—" else ""
    )

    html_body = md_to_html(body)
    html = HTML_TEMPLATE.format(
        title=escape(title),
        meta_badges=meta_badges,
        meta_extra=meta_extra,
        body=html_body,
        source=escape(source),
        redaktsiia=escape(redaktsiia),
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{slug}.html"
    out_file.write_text(html, encoding="utf-8")
    size_kb = out_file.stat().st_size / 1024
    print(f"  [OK] {slug}.html ({size_kb:.0f} KB)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="коман-список slug, які обробити")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    only = set(s.strip() for s in args.only.split(",")) if args.only else None
    out_dir = Path(args.out)

    print(f"Вихідна папка: {out_dir}")
    ok = 0
    for slug, keys, title in ACTS:
        if only and slug not in only:
            continue
        if build_doc(slug, keys, title, out_dir):
            ok += 1
    print(f"\nГотово: {ok} документів у {out_dir}")


if __name__ == "__main__":
    main()
