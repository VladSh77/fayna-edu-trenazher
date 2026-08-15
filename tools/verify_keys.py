#!/usr/bin/env python3
"""Незалежна перевірка ключів банку іншою моделлю."""

import argparse
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BANK_DEFAULT = "banks/mzs-2026.json"
OUT_DEFAULT = "reports/verify_keys.md"
TMP_DIR = ".verify_tmp"
PACK_SIZE = 10
RETRIES = 2
THRESHOLD = 0.10
MIN_ANSWERED_RATIO = 0.60

PROMPT_TEMPLATE = """Ти — юрист-експерт з українського права. Нижче 10 тестових питань із ключем
«правильної» відповіді, який поставила ІНША модель. Твоє завдання — незалежно
перевірити КОЖЕН ключ.
Для кожного питання віддай рядок строго у форматі:
<ID> | <ВЕРДИКТ> | <впевненість 0-100> | <стаття/норма або "не знаю"> | <коротко чому>
ВЕРДИКТ — рівно одне слово: ПІДТВЕРДЖУЮ (ключ правильний), СПРОСТОВУЮ (правильна
інша з наведених — назви яка), НЕВИЗНАЧЕНО (питання некоректне, кілька правильних,
або бракує даних).
Якщо не впевнений — став НЕВИЗНАЧЕНО, не вгадуй. Хибне ПІДТВЕРДЖУЮ гірше за чесне НЕВИЗНАЧЕНО.
Жодного тексту поза цими рядками."""


def find_research_cli():
    """Знайти research_cli.py."""
    candidates = [
        Path("../docs-sorter/research_cli.py"),
        Path.home() / "Developer/Fayna-Workspace/Projects/docs-sorter/research_cli.py",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_bank(path):
    """Завантажити банк питань."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        sections = data.get("sections", data.get("questions", []))
    elif isinstance(data, list):
        sections = data
    else:
        raise ValueError("Невідома структура банку")
    return sections


def extract_questions(sections):
    """Витягти всі питання з секцій."""
    questions = []
    for section in sections:
        if isinstance(section, dict):
            section_name = section.get("title", section.get("name", "без назви"))
            items = section.get("questions", section.get("items", []))
            for q in items:
                if isinstance(q, dict):
                    qid = q.get("id", q.get("question_id", ""))
                    text = q.get("question", q.get("text", ""))
                    key = q.get("key", q.get("answer", q.get("correct", "")))
                    options = q.get("options", [])
                    questions.append({
                        "id": str(qid),
                        "section": str(section_name),
                        "question": str(text),
                        "key": str(key),
                        "options": options,
                    })
    return questions


def stratified_sample(questions, n, seed):
    """Стратифікована вибірка."""
    rng = random.Random(seed)
    sections = {}
    for q in questions:
        sections.setdefault(q["section"], []).append(q)

    sample = []
    section_names = list(sections.keys())
    rng.shuffle(section_names)

    # спочатку по одному з кожної секції
    for name in section_names:
        if len(sample) >= n:
            break
        sample.append(rng.choice(sections[name]))

    # потім пропорційно
    remaining = n - len(sample)
    if remaining > 0:
        total = len(questions)
        for name in section_names:
            if remaining <= 0:
                break
            count = max(0, round(len(sections[name]) / total * remaining))
            for _ in range(count):
                if remaining <= 0:
                    break
                sample.append(rng.choice(sections[name]))
                remaining -= 1

    # якщо ще не вистачає — добираємо випадково
    if len(sample) < n:
        pool = [q for q in questions if q not in sample]
        rng.shuffle(pool)
        sample.extend(pool[: n - len(sample)])

    return sample[:n]


def build_task_file(path):
    """Створити файл-завдання."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(PROMPT_TEMPLATE)


def build_input_file(path, questions):
    """Створити файл-вхід із питаннями."""
    lines = []
    for q in questions:
        lines.append(f"ID: {q['id']}")
        lines.append(f"Питання: {q['question']}")
        if q["options"]:
            for i, opt in enumerate(q["options"], 1):
                lines.append(f"  {i}. {opt}")
        lines.append(f"Ключ (від іншої моделі): {q['key']}")
        lines.append("---")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_provider(research_cli, task_file, input_file, out_file, provider, model):
    """Викликати research_cli."""
    cmd = [
        sys.executable,
        str(research_cli),
        "chat",
        "--task-file", str(task_file),
        "--input-file", str(input_file),
        "--out", str(out_file),
        "--provider", provider,
    ]
    if model:
        cmd.extend(["--model", model])

    for attempt in range(RETRIES + 1):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(out_file):
            with open(out_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                return True, result.returncode, len(content.encode("utf-8")), ""
        if attempt < RETRIES:
            continue
    # зібрати помилку
    error_msg = ""
    if result.returncode != 0:
        error_msg = f"exit_{result.returncode}: {result.stderr[:200]}"
    elif os.path.exists(out_file):
        with open(out_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            error_msg = "empty_output"
    else:
        error_msg = "no_output_file"
    return False, result.returncode, 0, error_msg


def parse_response(raw_text):
    """Розібрати відповідь моделі."""
    parsed = {}
    unparsed = []
    pattern = re.compile(
        r"^\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$"
    )
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = pattern.match(line)
        if m:
            qid = m.group(1).strip()
            verdict = m.group(2).strip().upper()
            confidence = m.group(3).strip()
            norm = m.group(4).strip()
            reason = m.group(5).strip()
            if verdict in ("ПІДТВЕРДЖУЮ", "СПРОСТОВУЮ", "НЕВИЗНАЧЕНО"):
                parsed[qid] = {
                    "verdict": verdict,
                    "confidence": confidence,
                    "norm": norm,
                    "reason": reason,
                }
            else:
                unparsed.append(line)
        else:
            unparsed.append(line)
    return parsed, unparsed


def main():
    parser = argparse.ArgumentParser(description="Незалежна перевірка ключів банку")
    parser.add_argument("--bank", default=BANK_DEFAULT)
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--provider", default="glm")
    parser.add_argument("--model", default=None)
    parser.add_argument("--fallback", default=None, help="Список провайдерів через кому, напр. openrouter:google/gemini-3.7-flash,openai")
    parser.add_argument("--out", default=OUT_DEFAULT)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # знайти research_cli
    research_cli = find_research_cli()
    if research_cli is None:
        print("ПОМИЛКА: research_cli.py не знайдено (шукав ../docs-sorter/research_cli.py та ~/Developer/Fayna-Workspace/Projects/docs-sorter/research_cli.py)", file=sys.stderr)
        sys.exit(2)

    # завантажити банк
    try:
        sections = load_bank(args.bank)
    except Exception as e:
        print(f"ПОМИЛКА: не вдалося завантажити банк {args.bank}: {e}", file=sys.stderr)
        sys.exit(2)

    questions = extract_questions(sections)
    if not questions:
        print("ПОМИЛКА: банк порожній або не містить питань", file=sys.stderr)
        sys.exit(2)

    # вибірка
    sample = stratified_sample(questions, args.n, args.seed)
    total_in_bank = len(questions)

    # створити тимчасову теку
    os.makedirs(TMP_DIR, exist_ok=True)

    # підготувати провайдерів
    providers = []
    if args.provider:
        providers.append({"provider": args.provider, "model": args.model})
    if args.fallback:
        for item in args.fallback.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                prov, model = item.split(":", 1)
                providers.append({"provider": prov.strip(), "model": model.strip()})
            else:
                providers.append({"provider": item, "model": None})

    # пакети
    all_results = {}
    all_unparsed = []
    all_provider_used = {}
    log_lines = []
    consecutive_rate_limited = 0
    last_error = ""

    for i in range(0, len(sample), PACK_SIZE):
        pack = sample[i : i + PACK_SIZE]
        pack_num = i // PACK_SIZE + 1

        task_file = Path(TMP_DIR) / f"task-{pack_num:02d}.txt"
        input_file = Path(TMP_DIR) / f"input-{pack_num:02d}.txt"
        out_file = Path(TMP_DIR) / f"out-{pack_num:02d}.txt"
        raw_file = Path(TMP_DIR) / f"raw-{pack_num:02d}.txt"

        build_task_file(task_file)
        build_input_file(input_file, pack)

        pack_ok = False
        pack_error = ""
        pack_provider_used = ""
        pack_bytes = 0
        pack_exit_code = -1

        for prov_idx, prov_info in enumerate(providers):
            ok, exit_code, bytes_out, error_msg = run_provider(
                research_cli, task_file, input_file, out_file,
                prov_info["provider"], prov_info["model"]
            )
            pack_exit_code = exit_code
            pack_bytes = bytes_out

            if ok:
                # зберегти сиру відповідь
                with open(out_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                with open(raw_file, "w", encoding="utf-8") as f:
                    f.write(raw)

                parsed, unparsed = parse_response(raw)
                all_results.update(parsed)
                all_unparsed.extend(unparsed)
                pack_ok = True
                pack_provider_used = prov_info["provider"]
                if prov_info["model"]:
                    pack_provider_used += f":{prov_info['model']}"
                consecutive_rate_limited = 0
                break
            else:
                pack_error = error_msg
                # записати raw з помилкою
                with open(raw_file, "w", encoding="utf-8") as f:
                    f.write(f"ERROR: {error_msg}\n")

                # перевірка на rate limit
                if "429" in error_msg or "rate limit" in error_msg.lower():
                    consecutive_rate_limited += 1
                    if consecutive_rate_limited >= 2:
                        print(f"рецензент {prov_info['provider']} впирається в ліміт — візьми іншого", file=sys.stderr)
                        sys.exit(3)
                else:
                    consecutive_rate_limited = 0

        if not pack_ok:
            print(f"ПОПЕРЕДЖЕННЯ: пакет {pack_num} не вдалося обробити: {pack_error[:200]}", file=sys.stderr)
            all_provider_used[pack_num] = "НЕ ВДАЛОСЯ"
        else:
            all_provider_used[pack_num] = pack_provider_used

        # лог
        log_lines.append(
            f"пакет {pack_num} | {pack_provider_used if pack_ok else 'FAILED'} | "
            f"{pack_exit_code} | {pack_bytes} | {len(all_results) if pack_ok else 0}"
        )

    # записати run.log
    with open(Path(TMP_DIR) / "run.log", "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")

    # зібрати результати
    confirmed = []
    refuted = []
    undetermined = []
    for q in sample:
        qid = q["id"]
        if qid in all_results:
            verdict = all_results[qid]["verdict"]
            if verdict == "ПІДТВЕРДЖУЮ":
                confirmed.append(q)
            elif verdict == "СПРОСТОВУЮ":
                refuted.append(q)
            else:
                undetermined.append(q)
        else:
            undetermined.append(q)

    # звіт
    total_checked = len(sample)
    answered = len(all_results)
    pct = lambda n: round(n / answered * 100) if answered else 0

    lines = []
    lines.append("# Незалежна перевірка ключів банку")
    lines.append(f"Провайдер-рецензент: {args.provider} · вибірка {total_checked} з {total_in_bank} · seed {args.seed} · дата — {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"Отримано вердиктів: {answered} з {total_checked}")
    lines.append("")

    if answered < total_checked:
        lines.append("## ⚠️ Без відповіді рецензента")
        for q in sample:
            if q["id"] not in all_results:
                lines.append(f"- {q['id']}")
        lines.append("")

    lines.append("## Підсумок")
    lines.append(f"ПІДТВЕРДЖУЮ: {len(confirmed)} ({pct(len(confirmed))}%)")
    lines.append(f"СПРОСТОВУЮ: {len(refuted)} ({pct(len(refuted))}%)")
    lines.append(f"НЕВИЗНАЧЕНО: {len(undetermined)} ({pct(len(undetermined))}%)")
    lines.append(f"не розібрано: {len(all_unparsed)}")
    lines.append(f"(відповідей {answered} з {total_checked})")
    lines.append("")

    if refuted:
        lines.append("## 🔴 СПРОСТОВАНІ — перевірити руками")
        lines.append("| ID | розділ | питання | наш ключ | що каже рецензент | норма |")
        lines.append("|---|---|---|---|---|---|")
        for q in refuted:
            info = all_results.get(q["id"], {})
            reason = info.get("reason", "")
            norm = info.get("norm", "")
            lines.append(f"| {q['id']} | {q['section']} | {q['question']} | {q['key']} | {reason} | {norm} |")
        lines.append("")

    if undetermined:
        lines.append("## 🟡 НЕВИЗНАЧЕНІ")
        lines.append("| ID | розділ | питання | наш ключ | коментар |")
        lines.append("|---|---|---|---|---|")
        for q in undetermined:
            info = all_results.get(q["id"], {})
            reason = info.get("reason", "не розібрано")
            lines.append(f"| {q['id']} | {q['section']} | {q['question']} | {q['key']} | {reason} |")
        lines.append("")

    if confirmed:
        lines.append("## ✅ Підтверджені")
        ids = ", ".join(q["id"] for q in confirmed)
        lines.append(ids)
        lines.append("")

    if all_unparsed:
        lines.append("## Не розібрано")
        for line in all_unparsed:
            lines.append(f"- `{line}`")
        lines.append("")

    # записати звіт
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # код виходу
    if answered == 0:
        print("ВЕРДИКТ: ПЕРЕВІРКА НЕ ВІДБУЛАСЬ — жодної відповіді від рецензента")
        sys.exit(3)
    elif answered / total_checked < MIN_ANSWERED_RATIO:
        print(f"ВЕРДИКТ: ПЕРЕВІРКА НЕПОВНА — отримано {answered} з {total_checked}")
        sys.exit(3)
    else:
        refuted_ratio = len(refuted) / answered if answered else 0
        if refuted_ratio < THRESHOLD:
            print(f"ВЕРДИКТ: ok — спростовано {len(refuted)} з {answered} ({pct(len(refuted))}%) (відповідей {answered} з {total_checked})")
            sys.exit(0)
        else:
            print(f"ВЕРДИКТ: ПОТРІБЕН РУЧНИЙ РОЗБІР — спростовано {len(refuted)} з {answered} ({pct(len(refuted))}%) (відповідей {answered} з {total_checked})")
            sys.exit(1)


if __name__ == "__main__":
    main()
