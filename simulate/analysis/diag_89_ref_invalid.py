#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Діагностика 89 REF_INVALID питань.
Для кожного питання:
  - визначає legislation_file(ref) -> чи є файл у laws/
  - якщо файл є — чи витягується стаття/пункт (extract_article_by_ref)
  - якщо файлу немає — це ВІДСУТНІЙ АКТ (для MISSING_ACTS_LIST.md)
Виводить повний перелік ref для кожного питання.
"""

import importlib.util
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location(
    "sim", os.path.join(ROOT, "simulate/simulate.py")
)
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

LAWS = os.path.join(ROOT, "laws")


def get_ref(r):
    expl = r.get("explain")
    if isinstance(expl, dict):
        return expl.get("ref", "")
    return r.get("ref", "")


def main():
    res = json.load(open(os.path.join(ROOT, "simulate/simulation_results.json")))
    results = res["results"]
    items = (
        list(results.items())
        if isinstance(results, dict)
        else [(r.get("id"), r) for r in results]
    )
    ri = [r for _, r in items if r.get("status") == "REF_INVALID"]
    print(f"REF_INVALID total: {len(ri)}\n")

    missing = []  # немає файлу акта
    has_file = []  # файл є, але стаття не витягується

    for r in ri:
        ref = get_ref(r)
        law = sim.legislation_file(ref)
        law_path = os.path.join(LAWS, law) if law else ""
        if not law or not os.path.exists(law_path):
            missing.append((r, ref, law))
        else:
            html = open(law_path, encoding="utf-8").read()
            title, body = sim.extract_article_by_ref(html, ref)
            if body:
                has_file.append((r, ref, law, "EXTRACTED"))
            else:
                has_file.append((r, ref, law, "NOT_EXTRACTED"))

    print("=" * 80)
    print(f"### ВІДСУТНІ АКТИ (немає файлу в laws/): {len(missing)}")
    print("=" * 80)
    # групуємо за ref-префіксом (назва акта)
    by_act = defaultdict(list)
    for r, ref, law in missing:
        # нормалізуємо назву акта: беремо частину до коми/номера статті
        act = ref.split(",")[0].strip()
        by_act[act].append((r.get("id"), ref))
    for act, qs in sorted(by_act.items(), key=lambda x: -len(x[1])):
        print(f"\n### {act}  [{len(qs)}]")
        for qid, ref in qs:
            print(f"    {qid}: {ref}")

    print("\n" + "=" * 80)
    print(f"### ФАЙЛ Є, але стаття не витягується: {len(has_file)}")
    print("=" * 80)
    by_file = defaultdict(list)
    for r, ref, law, st in has_file:
        by_file[law].append((r.get("id"), ref, st))
    for law, qs in sorted(by_file.items(), key=lambda x: -len(x[1])):
        print(f"\n### {law}  [{len(qs)}]")
        for qid, ref, st in qs:
            print(f"    {qid} [{st}]: {ref}")

    # зберегти JSON для подальшого використання
    out = {
        "missing": [
            {"id": r.get("id"), "ref": ref, "law": law} for r, ref, law in missing
        ],
        "has_file": [
            {"id": r.get("id"), "ref": ref, "law": law, "status": st}
            for r, ref, law, st in has_file
        ],
    }
    with open(os.path.join(ROOT, "simulate/analysis/diag_89_out.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nSaved diag_89_out.json")


if __name__ == "__main__":
    main()
