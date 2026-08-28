#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Виправляє обрізані (… ) назви розділів у banks/mzs-2026.json,
замінюючи їх на повні назви з відповідних файлів законів (laws/*.html).

Використання:
    python3 tools/fix_section_titles.py
"""

import json
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK_PATH = os.path.join(BASE, "banks", "mzs-2026.json")


def law_title(path):
    """Дістає повну назву акта з <h1> файлу закону."""
    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
    except Exception:
        return None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if not m:
        return None
    return re.sub(r"<[^>]+>", "", m.group(1)).strip()


# Карта: id розділу -> повна назва (з файлу закону або вручну)
FIXES = {
    "uhoda-pro-asotsiatsiiu-mizh-ukrainoiu-z": "Угода про асоціацію між Україною та ЄС (2014)",
    "pravyla-oformlennia-viz-dlia-v-izdu-v": "Постанова КМУ № 118 «Про затвердження Правил оформлення віз для в'їзду в Україну і транзитного проїзду через її територію»",
    "postanova-kabinetu-ministriv-ukrainy-2": "Постанова КМУ № 55 «Деякі питання документування управлінської діяльності»",
    "postanova-kabinetu-ministriv-pro-2": "Постанова КМУ № 950 «Про затвердження Регламенту Кабінету Міністрів України»",
    "nakaz-derzhavnoho-kaznacheistva-ukrainy": "Наказ Держказначейства № 130 «Про затвердження типових форм обліку та списання запасів»",
    "nakaz-ministerstva-finansiv-ukrainy-vid": "Наказ Мінфіну № 879 «Про затвердження Положення про інвентаризацію»",
    "postanova-kabinetu-ministriv-ukrainy": "Постанова КМУ від 17.07.2019 № 645",
    "pryznachennia-diialnist-i-prypynennia": "Положення про нештатних (почесних) консулів України (Указ Президента України)",
}


def main():
    with open(BANK_PATH, encoding="utf-8") as f:
        bank = json.load(f)

    changed = 0
    for sec in bank["sections"]:
        old = sec["title"]
        if old.endswith("…") or "…" in old:
            new = FIXES.get(sec["id"])
            if not new:
                print(f"⚠️  НЕМАЄ виправлення для: {sec['id']} | {old}")
                continue
            sec["title"] = new
            changed += 1
            print(f"✅ {sec['id']}\n   {old}\n   → {new}\n")

    with open(BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"\nВиправлено розділів: {changed}")


if __name__ == "__main__":
    main()
