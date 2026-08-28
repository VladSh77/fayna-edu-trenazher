#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Семантична перевірка відповідей тренажера МЗС «Очима людини».

Перевіряє кожну з 1088 відповідей банку banks/mzs-2026.json на:
  1. ЗМІСТОВУ КОРЕКТНІСТЬ — чи правильна відповідь (correct) справді міститься
     в повному тексті відповідного нормативного акта (laws/*.html), на який
     посилається explain.ref.
  2. ФОРМАТНУ ЯКІСТЬ — обрізані речення, подвійні пробіли, зламані символи,
     порожні поля, дублікати варіантів.

Використання:
  python3 tools/verify_human_answers.py
  python3 tools/verify_human_answers.py --bank banks/mzs-2026.json

Результат: звіт UI_HUMAN_AUDIT_REPORT.md + вивід у консоль.
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BANK = os.path.join(ROOT, "banks", "mzs-2026.json")
LAWS_DIR = os.path.join(ROOT, "laws")
REPORT = os.path.join(ROOT, "UI_HUMAN_AUDIT_REPORT.md")

# Регулярні вирази для перевірки формату
RE_DOUBLE_SPACE = re.compile(r"[ \t]{2,}")
RE_TRUNCATED = re.compile(r"…\s*$|\.\.\.\s*$|\.\.\s*$")
RE_BROKEN_CHARS = re.compile(r"[ÃÂÐÐ]|â€|â€™|â€œ|â€\u009d|â€š|Ã©|Ã¨|Ã±|Ã¼|Ã¶|Ã¤")
RE_LEADING_TRAILING = re.compile(r"^\s+|\s+$")
RE_HTML_TAG = re.compile(r"<[^>]+>")
RE_MULTI_SPACE = re.compile(r"\s{2,}")


def load_bank(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_law_text(filepath):
    """Витягує чистий текст із HTML-файлу закону."""
    try:
        with open(filepath, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return None
    # Видаляємо скрипти та стилі
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    # Замінюємо теги на пробіли
    text = re.sub(r"<[^>]+>", " ", html)
    # Розкодовуємо HTML-сутності
    import html as html_mod

    text = html_mod.unescape(text)
    # Нормалізуємо пробіли
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def map_ref_to_law(ref):
    """Визначає файл закону за рядком джерела (explain.ref)."""
    if not ref:
        return None
    r = ref.lower()
    # Проста евристика: шукаємо файл, чия назва/ключові слова збігаються
    # Спершу спробуємо знайти за ключовими словами з ref
    keywords = {
        "громадянство": "zakon-pro-hromadianstvo.html",
        "нотаріат": "zakon-pro-notariat.html",
        "дипломатичну службу": "zakon-pro-dyplomatychnu-sluzhbu.html",
        "виборчий кодекс": "vyborchyi-kodeks-ukrainy.html",
        "цивільний кодекс": "tsyvilnyi-kodeks-ukrainy.html",
        "сімейний кодекс": "simeinyi-kodeks-ukrainy.html",
        "кримінальний процесуальний": "kryminalnyi-protsesualnyi-kodeks-ukrainy.html",
        "кримінальний кодекс": "kryminalnyi-kodeks-ukrainy.html",
        "адміністративні правопорушення": "kodeks-ukrainy-pro-administratyvni-pravoporushennia.html",
        "міжнародне приватне право": "zakon-pro-mizhnarodne-pryvatne-pravo.html",
        "охорону дитинства": "zakon-pro-okhoronu-dytynstva.html",
        "правовий статус іноземців": "zakon-pro-pravovyi-status-inozemtsiv.html",
        "міжнародні договори": "zakon-pro-mizhnarodni-dohovory.html",
        "реєстрацію актів цивільного стану": "zakon-pro-derzhavnu-reiestratsiiu-aktiv-tsyvilnoho-stanu.html",
        "державний реєстр виборців": "zakon-pro-derzhavnyi-reiestr-vyborciv.html",
        "управління об": "zakon-pro-upravlinnia-obiektamy-derzhavnoi-vlasnosti.html",
        "електронні документи": "zakon-pro-elektronni-dokumenty.html",
        "регламент верховної ради": "rehlament-verkhovnoi-rady.html",
        "демографічний реєстр": "zakon-pro-yedynyi-derzhavnyi-demohrafichnyi-reiestr.html",
        "надзвичайного стану": "zakon-pro-nadzvychaini-sytuatsii.html",
        "національну поліцію": "zakon-pro-natsionalnu-politsiiu.html",
        "соціальної захищеності": "zakon-pro-osnovy-sotsialnoi-zakhyshchenosti.html",
        "регламент кабінету": "rehlament-kabinetu-ministriv.html",
        "консульський статут": "konsulskyi-statut-ukrainy.html",
        "шенген": "shenhenska-uhoda.html",
        "копенгаген": "kopenhahenski-kryterii.html",
        "апостиль": "haazka-konventsiia-apostyl.html",
        "віденська конвенція про право": "videnska-konventsiia-pravo-mizhnarodnykh-dohovoriv.html",
        "віденська конвенція про дипломатичні": "videnska-konventsiia-dyplomatychni-znosyny.html",
        "віденська конвенція про консульські": "videnska-konventsiia-konsulski-znosyny.html",
        "угода про асоціацію": "uhoda-pro-asotsiatsiiu-ukraina-yes.html",
        "функціонування європейського союзу": "dohovir-pro-funktsionuvannia-yes.html",
        "договір про європейський союз": "dohovir-pro-yevropeiskyi-soiuz.html",
        "взаємну допомогу у кримінальних": "yevropeiska-konventsiia-vzaiemna-dopomoha.html",
        "правила оформлення віз": "pravyla-oformlennia-viz.html",
        "типової інструкції": "typova-instruktsiia-dilovodstva.html",
        "документування": "postanova-kmu-55-dokumentuvannia.html",
        "інвентаризацію": "nakaz-minfinu-879-inventaryzatsiia.html",
        "витребування": "instruktsiia-vytrebuvannia-dokumentiv.html",
        "приймання в експлуатацію": "poriadok-pryimannia-ekspluatatsiiu.html",
        "почесних консулів": "polozhennia-pro-pochesnykh-konsuliv.html",
        "положення про мзс": "polozhennia-pro-mzs.html",
        "порядок провадження за заявами": "poriadok-provadzhennia-hromadianstvo.html",
        "ведення реєстру виборців": "poriadok-vedennia-reiestru-vyborciv.html",
        "правила державної реєстрації актів": "pravyla-derzhavnoi-reiestratsii-aktiv.html",
        "засідання органів асоціації": "postanova-kmu-zasidannia-orhaniv-asotsiatsii.html",
        "№ 879": "nakaz-minfinu-879-inventaryzatsiia.html",
        "№ 130": "nakaz-kaznacheistva-130-typovi-formy-zapasiv.html",
        "№ 645": "postanova-kmu-645.html",
        "№ 776": "postanova-kmu-776.html",
        "№ 368": "postanova-kmu-368-vizy.html",
        "№ 651": "postanova-kmu-651-zakhyst-hromadian.html",
        "№ 118": "pravyla-oformlennia-viz.html",
        "№ 750": "postanova-kmu-750-apostyl.html",
        "№ 954": "postanova-kmu-954.html",
    }
    for kw, file in keywords.items():
        if kw in r:
            return os.path.join(LAWS_DIR, file)
    return None


def check_format(value, field, issues):
    """Перевіряє форматну якість рядка."""
    if not value or not str(value).strip():
        issues.append(f"{field}: порожнє значення")
        return
    s = str(value)
    if RE_LEADING_TRAILING.search(s):
        issues.append(f"{field}: зайві пробіли на початку/кінці")
    if RE_DOUBLE_SPACE.search(s):
        issues.append(f"{field}: подвійні пробіли")
    if RE_TRUNCATED.search(s):
        issues.append(f"{field}: обрізане речення (…/...)")
    if RE_BROKEN_CHARS.search(s):
        issues.append(f"{field}: зламані символи (mojibake)")
    if RE_HTML_TAG.search(s):
        issues.append(f"{field}: HTML-теги в тексті")


def verify_bank(bank, verbose=False):
    """Повна перевірка банку. Повертає звіт."""
    total = bank.get("total", 0)
    sections = bank.get("sections", [])
    results = {
        "total_questions": 0,
        "format_ok": 0,
        "format_issues": [],
        "content_checked": 0,
        "content_ok": 0,
        "content_warn": [],
        "content_missing_law": [],
        "duplicate_options": [],
        "empty_fields": [],
        "section_counts": {},
    }

    for sec in sections:
        sec_id = sec.get("id")
        qs = sec.get("questions", [])
        results["section_counts"][sec_id] = len(qs)
        for q in qs:
            results["total_questions"] += 1
            qid = q.get("id", "?")
            question = q.get("question", "")
            correct = q.get("correct", "")
            wrong = q.get("wrong", [])
            explain = q.get("explain", {}) or {}
            explain_text = explain.get("text", "")
            ref = explain.get("ref", "")

            # --- Форматна перевірка ---
            issues = []
            check_format(question, "питання", issues)
            check_format(correct, "правильна відповідь", issues)
            for i, w in enumerate(wrong):
                check_format(w, f"неправильна відповідь #{i + 1}", issues)
            check_format(explain_text, "пояснення", issues)

            # Дублікати варіантів
            all_opts = [correct] + list(wrong)
            norm_opts = [
                re.sub(r"\s+", " ", str(o).strip().lower()) for o in all_opts if o
            ]
            if len(norm_opts) != len(set(norm_opts)):
                results["duplicate_options"].append(qid)

            # Порожні поля
            if not question.strip():
                results["empty_fields"].append(f"{qid}: порожнє питання")
            if not correct.strip():
                results["empty_fields"].append(f"{qid}: порожня правильна відповідь")

            if issues:
                results["format_issues"].append({"id": qid, "issues": issues})
            else:
                results["format_ok"] += 1

            # --- Змістова перевірка (за наявності ref) ---
            if ref:
                law_file = map_ref_to_law(ref)
                if law_file and os.path.exists(law_file):
                    results["content_checked"] += 1
                    law_text = load_law_text(law_file)
                    if law_text:
                        # Шукаємо ключові слова правильної відповіді в тексті закону
                        correct_norm = re.sub(r"\s+", " ", correct.strip().lower())
                        # Для коротких відповідей (1-3 слова) шукаємо фразу
                        words = [
                            w
                            for w in re.split(r"[\s,;:()\-–—]+", correct_norm)
                            if len(w) > 3
                        ]
                        if words:
                            # Перевіряємо, чи всі значущі слова є в тексті закону
                            found = sum(1 for w in words if w in law_text)
                            ratio = found / len(words) if words else 0
                            if ratio >= 0.7:
                                results["content_ok"] += 1
                            else:
                                results["content_warn"].append(
                                    {
                                        "id": qid,
                                        "ref": ref,
                                        "correct": correct,
                                        "found_ratio": round(ratio, 2),
                                    }
                                )
                        else:
                            # Дуже коротка відповідь — перевіряємо повну фразу
                            if correct_norm in law_text:
                                results["content_ok"] += 1
                            else:
                                results["content_warn"].append(
                                    {
                                        "id": qid,
                                        "ref": ref,
                                        "correct": correct,
                                        "found_ratio": 0,
                                    }
                                )
                    else:
                        results["content_missing_law"].append(
                            {"id": qid, "ref": ref, "file": law_file}
                        )
                else:
                    results["content_missing_law"].append(
                        {"id": qid, "ref": ref, "file": law_file}
                    )

    return results


def write_report(results, bank_path):
    lines = []
    lines.append("# UI_HUMAN_AUDIT_REPORT — Семантична перевірка відповідей")
    lines.append("")
    lines.append(f"- **Банк:** `{bank_path}`")
    lines.append(f"- **Всього питань:** {results['total_questions']}")
    lines.append(f"- **Розділів:** {len(results['section_counts'])}")
    lines.append("")
    lines.append("## 1. Форматна якість")
    lines.append("")
    lines.append(
        f"- ✅ Формат коректний: **{results['format_ok']}/{results['total_questions']}**"
    )
    lines.append(f"- ⚠️ Проблеми формату: **{len(results['format_issues'])}**")
    lines.append(f"- 🔁 Дублікати варіантів: **{len(results['duplicate_options'])}**")
    lines.append(f"- ⬜ Порожні поля: **{len(results['empty_fields'])}**")
    lines.append("")
    if results["format_issues"]:
        lines.append("### Проблеми формату (деталі)")
        lines.append("")
        lines.append("| ID | Проблеми |")
        lines.append("|----|----------|")
        for fi in results["format_issues"][:50]:
            lines.append(f"| {fi['id']} | {'; '.join(fi['issues'])} |")
        lines.append("")
    if results["duplicate_options"]:
        lines.append("### Дублікати варіантів")
        lines.append("")
        lines.append(", ".join(results["duplicate_options"][:50]))
        lines.append("")
    if results["empty_fields"]:
        lines.append("### Порожні поля")
        lines.append("")
        for e in results["empty_fields"][:50]:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("## 2. Змістова коректність (перевірка проти текстів законів)")
    lines.append("")
    lines.append(
        f"- 🔍 Перевірено з посиланням на закон: **{results['content_checked']}**"
    )
    lines.append(
        f"- ✅ Відповідь підтверджена текстом закону: **{results['content_ok']}**"
    )
    lines.append(
        f"- ⚠️ Відповідь не знайдена в тексті закону: **{len(results['content_warn'])}**"
    )
    lines.append(
        f"- ❌ Закон не знайдено/не завантажено: **{len(results['content_missing_law'])}**"
    )
    lines.append("")
    if results["content_warn"]:
        lines.append("### Відповіді, не підтверджені текстом закону")
        lines.append("")
        lines.append("| ID | Джерело | Правильна відповідь | Збіг |")
        lines.append("|----|---------|---------------------|------|")
        for w in results["content_warn"][:50]:
            lines.append(
                f"| {w['id']} | {w['ref']} | {w['correct']} | {w['found_ratio']} |"
            )
        lines.append("")
    if results["content_missing_law"]:
        lines.append("### Закони не знайдено")
        lines.append("")
        for m in results["content_missing_law"][:50]:
            lines.append(f"- `{m['id']}` → `{m['ref']}` → `{m['file']}`")
        lines.append("")

    lines.append("## 3. Підсумок")
    lines.append("")
    format_pct = (
        round(results["format_ok"] / results["total_questions"] * 100, 1)
        if results["total_questions"]
        else 0
    )
    content_pct = (
        round(results["content_ok"] / results["content_checked"] * 100, 1)
        if results["content_checked"]
        else 0
    )
    lines.append(f"- **Форматна якість:** {format_pct}%")
    lines.append(
        f"- **Змістова коректність:** {content_pct}% (з {results['content_checked']} перевірених)"
    )
    lines.append("")

    with open(REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return REPORT


def main():
    parser = argparse.ArgumentParser(
        description="Семантична перевірка відповідей тренажера МЗС"
    )
    parser.add_argument("--bank", default=DEFAULT_BANK, help="Шлях до банку JSON")
    parser.add_argument("--verbose", action="store_true", help="Детальний вивід")
    args = parser.parse_args()

    bank = load_bank(args.bank)
    print(f"Завантажено банк: {args.bank}")
    print(f"Питань: {bank.get('total')}, розділів: {len(bank.get('sections', []))}")

    results = verify_bank(bank, verbose=args.verbose)

    print("\n=== ФОРМАТ ===")
    print(f"Коректний формат: {results['format_ok']}/{results['total_questions']}")
    print(f"Проблеми формату: {len(results['format_issues'])}")
    print(f"Дублікати варіантів: {len(results['duplicate_options'])}")
    print(f"Порожні поля: {len(results['empty_fields'])}")

    print("\n=== ЗМІСТ ===")
    print(f"Перевірено з законом: {results['content_checked']}")
    print(f"Підтверджено: {results['content_ok']}")
    print(f"Не підтверджено: {len(results['content_warn'])}")
    print(f"Закон не знайдено: {len(results['content_missing_law'])}")

    report = write_report(results, args.bank)
    print(f"\nЗвіт збережено: {report}")

    # Exit code: 0 якщо немає критичних проблем
    critical = len(results["format_issues"]) + len(results["empty_fields"])
    if critical > 0:
        print(f"\n⚠️ Знайдено {critical} критичних проблем формату.")
        sys.exit(1)
    print("\n✅ Перевірка завершена успішно.")
    sys.exit(0)


if __name__ == "__main__":
    main()
