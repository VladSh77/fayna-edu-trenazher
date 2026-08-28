#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Повна перевірочна симуляція всієї бази питань МЗС (1088 питань / 37 розділів).

Для кожного питання:
  1) визначає файл закону за ref (legislation_file);
  2) якщо файлу немає в laws/            -> MISSING_LAW
  3) якщо ref не зіставляється з жодним актом -> REF_INVALID (немає акта за ref)
  4) якщо за ref не знайдено статті/пункту   -> REF_INVALID (немає статті за ref)
  5) інакше перевіряє, чи правильна відповідь узгоджується з текстом статті:
       - лексичний збіг (answer_matches_article / stem_ratio)
       - мета-відповіді «усі відповіді вірні»
       - LLM-семантична перевірка (verify_with_llm)
     Якщо узгоджується -> VALID, інакше -> TEXT_MISMATCH.

Класифікація результату:
  VALID          — все вірно (ref існує, стаття знайдена, відповідь узгоджується)
  REF_INVALID    — немає такої статті / немає акта за ref
  TEXT_MISMATCH  — відповідь суперечить нормі статті
  MISSING_LAW    — немає файла закону в laws/
  KRAJOZNAWSTWO  — конспект/країнознавство (не норма права, пропускається)
  UNVERIFIED     — LLM недоступний і лексичний збіг недостатній

Батчинг:
  --batch-size N   обробляти по N питань за раз (напр. 100)
  --by-section     обробляти по розділах (37 блоків)
  Результати кожного блоку дописуються в simulation_results.json
  (атомарно, з резюме блоку), тож симуляцію можна переривати й
  продовжувати з місця зупинки (--resume).

Використання:
  python run_full_simulation.py [--bank PATH] [--limit N] [--batch-size N]
      [--by-section] [--resume] [--no-llm] [--verbose] [--out PATH]
"""

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

# Додаємо теку simulate/ до шляху, щоб імпортувати simulate.py.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import simulate  # noqa: E402

PROJECT = HERE.parent
DEFAULT_BANK = PROJECT / "banks" / "mzs-2026.fixed2.json"
LAWS_DIR = PROJECT / "laws"
DEFAULT_OUT = HERE / "simulation_results.json"

# Класифікація результатів
VALID = "VALID"
REF_INVALID = "REF_INVALID"
TEXT_MISMATCH = "TEXT_MISMATCH"
MISSING_LAW = "MISSING_LAW"
KRAJOZNAWSTWO = "KRAJOZNAWSTWO"
UNVERIFIED = "UNVERIFIED"

# Ключові слова країнознавства (не норма права)
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


def load_bank(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flatten_questions(bank):
    """Повертає список питань з прив'язкою до розділу."""
    questions = []
    for sec in bank.get("sections", []):
        for q in sec.get("questions", []):
            q = dict(q)
            q["_section"] = sec.get("title", "")
            q["_section_id"] = sec.get("id", "")
            questions.append(q)
    return questions


def is_krajoznawstwo(q):
    section_id = q.get("_section_id", "")
    ref = (q.get("explain") or {}).get("ref", "")
    if section_id == "krainoznavstvo-polsha":
        return True
    return any(k.lower() in ref.lower() for k in KRAJ_KEYWORDS)


def classify_question(q, law_cache, use_llm=True, verbose=False):
    """
    Класифікує одне питання. Повертає dict з результатом.
    """
    qid = q.get("id", "?")
    section = q.get("_section", "")
    correct = q.get("correct", "")
    wrong = q.get("wrong", []) or []
    ref = (q.get("explain") or {}).get("ref", "")

    base = {
        "id": qid,
        "section": section,
        "section_id": q.get("_section_id", ""),
        "question": q.get("question", ""),
        "correct": correct,
        "wrong": wrong,
        "ref": ref,
        "status": None,
        "detail": "",
        "article_title": None,
        "provider": None,
        "lex_ratio": None,
    }

    # Країнознавство — не норма права
    if is_krajoznawstwo(q):
        base["status"] = KRAJOZNAWSTWO
        base["detail"] = "пропущено (конспект/країнознавство)"
        return base

    # 1) Визначаємо файл закону за ref
    fname = simulate.legislation_file(ref)
    if not fname:
        base["status"] = REF_INVALID
        base["detail"] = f"немає акта за ref: {ref!r}"
        return base

    # 2) Завантажуємо файл закону (з кешем)
    if fname not in law_cache:
        path = LAWS_DIR / fname
        if not path.exists():
            law_cache[fname] = None
        else:
            law_cache[fname] = path.read_text(encoding="utf-8", errors="replace")
    html_text = law_cache[fname]

    if html_text is None:
        base["status"] = MISSING_LAW
        base["detail"] = f"немає файлу закону: {fname}"
        return base

    # 3) Витягуємо статтю за ref
    title, article_text = simulate.extract_article_by_ref(html_text, ref)
    if not article_text:
        base["status"] = REF_INVALID
        base["detail"] = f"немає статті за ref: {ref}"
        return base
    base["article_title"] = title

    # 4) Перевірка узгодженості відповіді зі статтею
    matched, ratio, words = simulate.answer_matches_article(correct, article_text)
    base["lex_ratio"] = round(ratio, 4)

    if matched:
        base["status"] = VALID
        base["detail"] = f"лексичний збіг {ratio:.0%}"
        return base

    # Мета-відповідь «усі відповіді вірні»
    if simulate.is_meta_answer(correct):
        meta_ok, meta_detail = simulate.verify_meta_answer(
            q.get("question", ""), correct, wrong, article_text, html_text
        )
        if meta_ok:
            base["status"] = VALID
            base["detail"] = f"мета-відповідь {meta_detail}"
            return base
        base["status"] = TEXT_MISMATCH
        base["detail"] = f"мета-відповідь не підтверджена {meta_detail}"
        return base

    # Стемінг-фолбек (вимикаємо для питань «що НЕ»)
    if len(words) >= simulate.MIN_SIGNIFICANT_WORDS and not simulate.is_neg_question(
        q.get("question", "")
    ):
        stem = simulate.stem_ratio(correct, article_text)
        if stem >= simulate.LEXICAL_THRESHOLD:
            base["status"] = VALID
            base["detail"] = f"стемінг-збіг {stem:.0%}"
            return base

    # LLM-семантична перевірка
    if use_llm:
        ok, provider = simulate.verify_with_llm(
            q.get("question", ""), correct, article_text, max_chars=12000
        )
        base["provider"] = provider
        if ok is True:
            base["status"] = VALID
            base["detail"] = f"LLM({provider}) підтвердив"
            return base
        if ok is False:
            base["status"] = TEXT_MISMATCH
            base["detail"] = f"LLM({provider}) відхилив"
            return base
        # LLM недоступний
        base["status"] = UNVERIFIED
        base["detail"] = f"лексичний {ratio:.0%}, LLM недоступний"
        return base

    # LLM вимкнено -> лексичний збіг недостатній = розбіжність
    base["status"] = TEXT_MISMATCH
    base["detail"] = f"лексичний збіг {ratio:.0%}"
    return base


def summarize(results):
    """Підраховує кількість за статусами."""
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def build_report(results, total_questions):
    """Формує підсумковий звіт у %."""
    counts = summarize(results)
    total = len(results)
    report = {
        "total_questions": total_questions,
        "processed": total,
        "counts": counts,
        "percent": {},
    }
    for status in (
        VALID,
        REF_INVALID,
        TEXT_MISMATCH,
        MISSING_LAW,
        KRAJOZNAWSTWO,
        UNVERIFIED,
    ):
        c = counts.get(status, 0)
        report["percent"][status] = round(100.0 * c / total, 2) if total else 0.0
    # Загальний показник «чистоти» бази: частка VALID серед перевірених
    # (без країнознавства, яке не є нормою права).
    checked = total - counts.get(KRAJOZNAWSTWO, 0)
    valid = counts.get(VALID, 0)
    report["valid_rate"] = round(100.0 * valid / checked, 2) if checked else 0.0
    return report


def print_report(report):
    print("\n" + "=" * 60)
    print("ПІДСУМКОВИЙ ЗВІТ ПОВНОЇ СИМУЛЯЦІЇ")
    print("=" * 60)
    print(f"Всього питань у банку: {report['total_questions']}")
    print(f"Опрацьовано:           {report['processed']}")
    print("-" * 60)
    for status in (
        VALID,
        REF_INVALID,
        TEXT_MISMATCH,
        MISSING_LAW,
        KRAJOZNAWSTWO,
        UNVERIFIED,
    ):
        c = report["counts"].get(status, 0)
        p = report["percent"].get(status, 0.0)
        print(f"  {status:<16} {c:>5}  ({p:>6.2f}%)")
    print("-" * 60)
    print(f"  Частка VALID серед перевірених: {report['valid_rate']:.2f}%")
    print("=" * 60)


def save_results(results, out_path, report=None, append=False):
    """Зберігає результати в JSON. Якщо append — дописує до наявного файлу."""
    data = {"meta": {}, "results": results}
    if report:
        data["report"] = report
    if append and out_path.exists():
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
            old_results = old.get("results", [])
            # Дедуплікація за id (щоб повторний блок не дублював записи)
            seen = {r["id"] for r in old_results}
            for r in results:
                if r["id"] not in seen:
                    old_results.append(r)
                    seen.add(r["id"])
            data["results"] = old_results
            if report:
                old["report"] = report
            data = old
        except Exception:
            pass
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out_path)


def _env_int(name, default):
    """Читає int зі змінної середовища, інакше default."""
    v = os.environ.get(name, "")
    if v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _env_flag(name, default=False):
    """Читає прапорець (1/true/yes) зі змінної середовища."""
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def main():
    ap = argparse.ArgumentParser(description="Повна перевірочна симуляція МЗС")
    ap.add_argument(
        "--bank",
        default=os.environ.get("BANK_FILE", str(DEFAULT_BANK)),
        help="Шлях до банку питань",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=_env_int("LIMIT", 0),
        help="Максимум питань (0 = всі 1088)",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=_env_int("BATCH_SIZE", 0),
        help="Обробляти по N питань за блок (0 = без батчингу)",
    )
    ap.add_argument(
        "--by-section", action="store_true", help="Обробляти по розділах (37 блоків)"
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="Продовжити з місця зупинки (пропустити вже оброблені id)",
    )
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="Вимкнути LLM-семантичну перевірку (лише лексика)",
    )
    ap.add_argument(
        "--verbose", action="store_true", help="Детальний вивід по кожному питанню"
    )
    ap.add_argument(
        "--out",
        default=os.environ.get("OUT_FILE", str(DEFAULT_OUT)),
        help="Шлях до файлу результатів",
    )
    ap.add_argument(
        "--seed", type=int, default=42, help="Seed для перемішування при --limit"
    )
    args = ap.parse_args()

    # Підтримка BATCH_MODE=section через змінну середовища (docker-compose).
    batch_mode = os.environ.get("BATCH_MODE", "").strip().lower()
    if batch_mode in ("section", "1", "true", "yes"):
        args.by_section = True
    # RESUME / NO_LLM / VERBOSE зі змінних середовища
    if _env_flag("RESUME"):
        args.resume = True
    if _env_flag("NO_LLM"):
        args.no_llm = True
    if _env_flag("VERBOSE"):
        args.verbose = True

    bank_path = Path(args.bank)
    if not bank_path.exists():
        print(f"Помилка: банк не знайдено: {bank_path}", file=sys.stderr)
        sys.exit(1)

    bank = load_bank(bank_path)
    questions = flatten_questions(bank)
    total_questions = len(questions)

    if args.limit and args.limit > 0:
        random.seed(args.seed)
        random.shuffle(questions)
        questions = questions[: args.limit]

    # Якщо --resume — завантажуємо вже оброблені id
    done_ids = set()
    out_path = Path(args.out)
    if args.resume and out_path.exists():
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
            done_ids = {r["id"] for r in old.get("results", [])}
            print(f"Resume: пропускаємо {len(done_ids)} вже оброблених питань")
        except Exception:
            done_ids = set()

    use_llm = not args.no_llm
    law_cache = {}
    all_results = []
    append = args.resume

    # Формуємо блоки
    if args.by_section:
        # Групуємо за розділом, зберігаючи порядок
        blocks = []
        seen_sec = []
        for q in questions:
            sid = q.get("_section_id", "")
            if sid not in seen_sec:
                seen_sec.append(sid)
        for sid in seen_sec:
            block = [q for q in questions if q.get("_section_id", "") == sid]
            blocks.append((f"section:{sid}", block))
    elif args.batch_size and args.batch_size > 0:
        bs = args.batch_size
        blocks = [
            (f"batch:{i // bs + 1}", questions[i : i + bs])
            for i in range(0, len(questions), bs)
        ]
    else:
        blocks = [("all", questions)]

    print(f"Банк: {bank_path}")
    print(f"Питань: {total_questions}, блоків: {len(blocks)}")
    print(f"LLM: {'увімкнено' if use_llm else 'вимкнено'}")
    print()

    start_all = time.time()
    for block_name, block in blocks:
        # Фільтруємо вже оброблені (resume)
        todo = [q for q in block if q.get("id") not in done_ids]
        if not todo:
            print(f"[{block_name}] вже оброблено, пропускаємо")
            continue
        print(f"[{block_name}] обробляю {len(todo)} питань...")
        block_results = []
        for i, q in enumerate(todo, 1):
            r = classify_question(q, law_cache, use_llm=use_llm, verbose=args.verbose)
            block_results.append(r)
            done_ids.add(r["id"])
            if args.verbose:
                print(
                    f"  [{i}/{len(todo)}] {r['id']} ({r['section']}): "
                    f"{r['status']} — {r['detail']}"
                )
        all_results.extend(block_results)

        # Проміжне збереження після кожного блоку
        report = build_report(all_results, total_questions)
        save_results(all_results, out_path, report=report, append=append)
        append = True  # після першого блоку — дописуємо
        print(
            f"[{block_name}] готово. Статуси: "
            + ", ".join(f"{k}={v}" for k, v in summarize(block_results).items())
        )

    elapsed = time.time() - start_all
    report = build_report(all_results, total_questions)
    report["elapsed_sec"] = round(elapsed, 1)
    save_results(all_results, out_path, report=report, append=append)

    print_report(report)
    print(f"\nРезультати збережено: {out_path}")
    print(f"Час виконання: {elapsed:.1f} с")


if __name__ == "__main__":
    main()
