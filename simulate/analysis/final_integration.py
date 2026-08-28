#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Крок 4: Фінальна інтеграція.

Об'єднує результати LLM-аудиту (llm_audit_55.json) у підсумковий файл
all_resolved_110.json:
  1) для кожного елемента, що пройшов аудит, додає audit_verdict / audit_provider / audit_note;
  2) перераховує категорії з фактичних елементів;
  3) оновлює meta з фінальним зведенням.
"""

import json
from collections import Counter
from pathlib import Path

WORK = Path(__file__).resolve().parent
ALL_RESOLVED = WORK / "all_resolved_110.json"
AUDIT = WORK / "llm_audit_55.json"


def main():
    data = json.loads(ALL_RESOLVED.read_text(encoding="utf-8"))
    elements = data["elements"]

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_by_n = {r["n"]: r for r in audit["results"]}

    # 1) Зливаємо результати аудиту в елементи
    for e in elements:
        n = e["n"]
        r = audit_by_n.get(n)
        if r is None:
            e["audit"] = None
            continue
        e["audit"] = {
            "status": r.get("status"),
            "verdict": r.get("verdict"),
            "provider": r.get("provider"),
            "article_title": r.get("article_title"),
            "note": r.get("note"),
        }

    # 2) Перераховуємо категорії
    cats = Counter(e.get("category") for e in elements)

    # 3) Зведення аудиту
    audited = [
        e for e in elements if e.get("audit") and e["audit"].get("status") == "OK"
    ]
    verified_yes = [e["n"] for e in audited if e["audit"]["verdict"] is True]
    verified_no = [e["n"] for e in audited if e["audit"]["verdict"] is False]
    llm_unavailable = [e["n"] for e in audited if e["audit"]["verdict"] is None]

    data["meta"] = {
        "total": len(elements),
        "batches": data["meta"].get("batches", 8),
        "categories": dict(cats),
        "audit": {
            "total_audited": len(audited),
            "verified_yes": len(verified_yes),
            "verified_no": len(verified_no),
            "llm_unavailable": len(llm_unavailable),
            "verified_no_list": verified_no,
            "llm_unavailable_list": llm_unavailable,
        },
    }

    ALL_RESOLVED.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=== ФІНАЛЬНЕ ЗВЕДЕННЯ ===")
    print(f"Всього елементів: {len(elements)}")
    print("Категорії:")
    for cat, cnt in cats.items():
        print(f"  {cat}: {cnt}")
    print("\nАудит:")
    print(f"  Пройшло аудит: {len(audited)}")
    print(f"  Підтверджено (verified_yes): {len(verified_yes)}")
    print(f"  Не підтверджено (verified_no): {len(verified_no)} {verified_no}")
    print(f"  LLM недоступний: {len(llm_unavailable)} {llm_unavailable}")
    print(f"\nЗбережено: {ALL_RESOLVED}")


if __name__ == "__main__":
    main()
