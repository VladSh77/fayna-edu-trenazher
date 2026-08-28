#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Діагностика: для 13 питань розділу 2 (файл є, стаття не витягується)
знайти, у якій статті/пункті наявного HTML-файлу міститься правильна відповідь.
Допомагає визначити коректний цільовий ref для реф-нормалізації.
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import importlib.util

spec = importlib.util.spec_from_file_location(
    "sim", os.path.join(ROOT, "simulate/simulate.py")
)
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

LAWS = os.path.join(ROOT, "laws")

# (qid, law_file, keywords_from_answer)
TARGETS = [
    # Положення про МЗС
    (
        "dodatok-4-519",
        "polozhennia-pro-mzs.html",
        ["Міністр закордонних справ", "повноваження", "міжнародних договорів"],
    ),
    (
        "dodatok-4-524",
        "polozhennia-pro-mzs.html",
        ["утворення", "реорганізації", "ліквідації", "представництв"],
    ),
    (
        "2019-11-26-dod2-1218",
        "polozhennia-pro-mzs.html",
        ["порушення", "двостороннього договору", "істотне"],
    ),
    (
        "bank_dodatok3-1780",
        "polozhennia-pro-mzs.html",
        ["функцій", "МЗС", "проживання"],
    ),
    # Консульський статут
    (
        "bank_dodatok3-1774",
        "konsulskyi-statut-ukrainy.html",
        ["госпіталізованих", "страхового полісу", "повернення"],
    ),
    (
        "bank_dodatok3-1776",
        "konsulskyi-statut-ukrainy.html",
        ["смерть", "померлого", "встановлення особи"],
    ),
    (
        "bank_dodatok3-1709",
        "konsulskyi-statut-ukrainy.html",
        ["кримінальної відповідальності", "довідка", "МВС"],
    ),
    (
        "bank_dodatok3-1710",
        "konsulskyi-statut-ukrainy.html",
        ["судимості", "заяву", "паспорта"],
    ),
    # Постанова № 118 / матеріальна допомога
    (
        "dodatok-4-126",
        "pravyla-oformlennia-viz.html",
        ["звільняються", "консульського збору", "короткострокових"],
    ),
    (
        "bank_dodatok3-1769",
        "pravyla-oformlennia-viz.html",
        ["матеріальної допомоги", "перевезення", "евакуації"],
    ),
    (
        "bank_dodatok3-1772",
        "pravyla-oformlennia-viz.html",
        ["ритуальних служб", "ДФМ", "фінансового менеджменту"],
    ),
    # Віденська конвенція про консульські зносини
    (
        "bank_dodatok3-1773",
        "videnska-konventsiia-konsulski-znosyny.html",
        ["поховання", "родичами", "померлого"],
    ),
    # Закон про правовий статус іноземців
    (
        "bank_dodatok3-1798",
        "zakon-pro-pravovyi-status-inozemtsiv.html",
        ["строк перебування", "візою", "міжнародним договором"],
    ),
]


def plain(html):
    t = re.sub(r"<[^>]+>", " ", html)
    t = re.sub(r"\s+", " ", t)
    return t


def main():
    bank = json.load(open(os.path.join(ROOT, "banks/mzs-2026.fixed2.json")))
    byid = {}
    for sec in bank["sections"]:
        for q in sec["questions"]:
            byid[q["id"]] = q

    for qid, law, kws in TARGETS:
        q = byid.get(qid)
        correct = (q or {}).get("correct", "")
        path = os.path.join(LAWS, law)
        html = open(path, encoding="utf-8").read()
        p = plain(html)
        print("=" * 90)
        print(f"QID: {qid}  FILE: {law}")
        print(f"  CORRECT: {correct[:120]}")
        # знайти всі статті, що містять ключові слова відповіді
        # спершу спробуємо extract_articles
        articles = sim.extract_articles(html)
        print(f"  Статей у файлі: {len(articles)}")
        # шукаємо статті, що містять хоча б 2 ключові слова
        for title, body in articles:
            b = plain(body)
            hits = sum(1 for k in kws if k.lower() in b.lower())
            if hits >= 2:
                print(f"    >> Стаття [{title}] hits={hits}: {b[:150]}")
        # також спробуємо знайти в plain тексті позицію відповіді
        idx = p.lower().find(correct[:40].lower())
        if idx >= 0:
            print(
                f"  Відповідь знайдено в plain на позиції {idx}: ...{p[max(0, idx - 80) : idx + 120]}..."
            )


if __name__ == "__main__":
    main()
