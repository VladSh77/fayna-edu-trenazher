#!/usr/bin/env python3
"""Quarantine questions with disproven keys from the bank."""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK_PATH = ROOT / "banks" / "mzs-2026.json"
QUARANTINE_PATH = ROOT / "banks" / "_quarantine.json"
MANIFEST_PATH = ROOT / "banks" / "manifest.json"
REPORT_PATH = ROOT / "reports" / "verify_keys_FULL.md"
QUARANTINE_REPORT_PATH = ROOT / "reports" / "QUARANTINE.md"
BACKUP_PATH = ROOT / "banks" / "mzs-2026.json.bak"


def parse_report(path):
    if not path.exists():
        print(f"Звіт не знайдено: {path}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    disputed = set()
    uncertain = set()

    in_disputed = False
    in_uncertain = False

    for line in text.splitlines():
        if line.startswith("## 🔴 СПРОСТОВАНІ"):
            in_disputed = True
            in_uncertain = False
            continue
        if line.startswith("## 🟡 НЕВИЗНАЧЕНІ"):
            in_disputed = False
            in_uncertain = True
            continue
        if line.startswith("## ") and not line.startswith("## 🔴") and not line.startswith("## 🟡"):
            in_disputed = False
            in_uncertain = False
            continue

        if not (in_disputed or in_uncertain):
            continue

        if not line.startswith("|"):
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0] == "ID" or set(cells[0]) <= {"-", " "}:
            continue
        if not cells[0]:
            continue

        if in_disputed:
            disputed.add(cells[0])
        elif in_uncertain:
            uncertain.add(cells[0])

    return disputed, uncertain


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    disputed, uncertain = parse_report(REPORT_PATH)

    if not disputed:
        print("нічого прибирати")
        print("OK")
        return 0

    bank = load_json(BANK_PATH)
    total_before = bank.get("total", 0)
    sections_before = len(bank.get("sections", []))

    if not BACKUP_PATH.exists():
        save_json(BACKUP_PATH, bank)

    disputed_details = {}
    uncertain_details = {}

    for line in REPORT_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0] == "ID" or set(cells[0]) <= {"-", " "}:
            continue
        qid = cells[0]
        if qid in disputed:
            disputed_details[qid] = {
                "section": cells[1],
                "question": cells[2],
                "our_key": cells[3],
                "reviewer_says": cells[4],
                "norm": cells[5] if len(cells) > 5 else "",
            }
        elif qid in uncertain:
            uncertain_details[qid] = {
                "section": cells[1],
                "question": cells[2],
                "our_key": cells[3],
                "comment": cells[4] if len(cells) > 4 else "",
            }

    quarantine_questions = []
    new_sections = []
    disputed_count = 0
    uncertain_count = 0

    for section in bank.get("sections", []):
        section_id = section.get("section_id", "")
        section_title = section.get("section_title", "")
        questions = section.get("questions", [])
        kept = []
        for q in questions:
            qid = q.get("id", "")
            if qid in disputed:
                disputed_count += 1
                q_copy = dict(q)
                q_copy["section_id"] = section_id
                q_copy["section_title"] = section_title
                q_copy["reviewer_says"] = disputed_details.get(qid, {}).get("reviewer_says", "")
                q_copy["norm"] = disputed_details.get(qid, {}).get("norm", "")
                quarantine_questions.append(q_copy)
            else:
                if qid in uncertain:
                    q["disputed"] = True
                    uncertain_count += 1
                kept.append(q)

        if kept:
            section["questions"] = kept
            section["count"] = len(kept)
            new_sections.append(section)

    new_total = sum(s.get("count", 0) for s in new_sections)

    if new_total != sum(len(s.get("questions", [])) for s in new_sections):
        print("Помилка: сума count по секціях не дорівнює total")
        sys.exit(1)

    bank["sections"] = new_sections
    bank["total"] = new_total

    save_json(BANK_PATH, bank)

    quarantine_data = {
        "total": len(quarantine_questions),
        "questions": quarantine_questions,
    }
    save_json(QUARANTINE_PATH, quarantine_data)

    if MANIFEST_PATH.exists():
        manifest = load_json(MANIFEST_PATH)
        bank_name = BANK_PATH.name
        found = False
        for entry in manifest.get("banks", []):
            if entry.get("file") == bank_name:
                entry["total"] = new_total
                entry["sections"] = len(new_sections)
                found = True
                break
        if not found:
            manifest.setdefault("banks", []).append({
                "file": bank_name,
                "total": new_total,
                "sections": len(new_sections)
            })
        # Remove any top-level keys except "banks"
        manifest = {"banks": manifest.get("banks", [])}
        save_json(MANIFEST_PATH, manifest)

    lines = []
    lines.append(f"Прибрано з банку: {disputed_count} · позначено спірними: {uncertain_count} · лишилось у банку: {new_total}")
    lines.append("")
    lines.append("| ID | розділ | питання | наш ключ (хибний) | що каже рецензент | норма |")
    lines.append("|---|---|---|---|---|---|")
    for q in quarantine_questions:
        qid = q.get("id", "")
        info = disputed_details.get(qid, {})
        lines.append(
            f"| {qid} | {info.get('section', '')} | {info.get('question', '')} | "
            f"{info.get('our_key', '')} | {info.get('reviewer_says', '')} | {info.get('norm', '')} |"
        )
    QUARANTINE_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUARANTINE_REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Self-check: verify manifest matches bank
    if MANIFEST_PATH.exists():
        manifest_check = load_json(MANIFEST_PATH)
        bank_check = load_json(BANK_PATH)
        bank_entry = next((e for e in manifest_check.get("banks", []) if e.get("file") == BANK_PATH.name), None)
        if bank_entry is None:
            print("❌ РОЗСИНХРОН manifest ↔ банк: запис не знайдено")
            sys.exit(1)
        manifest_total = bank_entry.get("total")
        manifest_sections = bank_entry.get("sections")
        actual_total = bank_check.get("total")
        actual_sections = len(bank_check.get("sections", []))
        if manifest_total != actual_total or manifest_sections != actual_sections:
            print(f"❌ РОЗСИНХРОН manifest ↔ банк: manifest total={manifest_total} sections={manifest_sections}, bank total={actual_total} sections={actual_sections}")
            sys.exit(1)
        print(f"manifest: total={manifest_total} sections={manifest_sections} ✓")

    print(f"Банк до:        {total_before}")
    print(f"Спростованих:   {len(disputed)} (унікальних)")
    print(f"Невизначених:   {len(uncertain)} (позначено disputed, лишились)")
    print(f"Прибрано:       {disputed_count}")
    print(f"Банк після:     {new_total}")
    print(f"Секцій було/стало: {sections_before} / {len(new_sections)}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
