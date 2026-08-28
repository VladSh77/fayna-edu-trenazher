#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Перевірка мапи LEGISLATION в index.html: синтаксис, наявність файлів, покриття ref."""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # корінь проєкту (tools/ -> ../)
INDEX = os.path.join(ROOT, "index.html")
BANK = os.path.join(ROOT, "banks", "mzs-2026.json")

with open(INDEX, encoding="utf-8") as f:
    html = f.read()

# --- 1. Знайти LEGISLATION array ---
m = re.search(r"const LEGISLATION = \[(.*?)\];", html, re.DOTALL)
if not m:
    print("ERROR: LEGISLATION array not found")
    sys.exit(1)
block = m.group(1)

# --- 2. Парсити записи [['k1','k2'], 'path'] ---
entries = re.findall(r"\[\s*\[(.*?)\]\s*,\s*'([^']+)'\s*\]", block, re.DOTALL)
print(f"Parsed {len(entries)} LEGISLATION entries")

# --- 3. Перевірити, що всі файли існують ---
missing = [p for _, p in entries if not os.path.exists(os.path.join(ROOT, p))]
print("Referenced law files:", len(entries))
print("Missing files:", missing if missing else "NONE - all exist")

# --- 4. Побудувати keyword->path map ---
# Обробляємо екрановані апострофи (\') у JS-джерелі: замінюємо їх на звичайний
# апостроф, щоб regex коректно витягував ключі.
kw_map = []
for keys_str, path in entries:
    keys_str = keys_str.replace("\\'", "'")
    keys = re.findall(r"'([^']+)'", keys_str)
    for k in keys:
        kw_map.append((k.lower(), path))

# --- 5. Перевірити покриття всіх ref у банку ---
with open(BANK, encoding="utf-8") as f:
    bank = json.load(f)

KRAJ = [
    "конспект країнознавства",
    "конституція республіки польща",
    "карта поляка",
    "карту поляка",
    "діловодство в польщі",
    "історія польщі",
    "гадяцький договір",
    "загальні знання про єс",
    "загальні знання про консульську діяльність",
    "законодавство польщі",
    "історія україни",
    "закон про громадянство польщі",
    "договір про добросусідство",
    "люблінського трикутника",
    "статут організації об",
    "зовнішню трудову міграцію",
    "про інформацію",
    "стратегія інформаційної безпеки",
    "закон про адвокатуру",
    "закон про діловодство в польщі",
    "закон про вибори до органів місцевого",
    "національні символи",
    "державні свята",
    "воєнний стан",
    "національні меншини",
    "адміністративний поділ",
    "валюту",
    "міжнародну допомогу",
    "про консульську службу",
]

unmapped = []
mapped_count = 0
kraj_count = 0
for s in bank["sections"]:
    for q in s.get("questions", []):
        ref = (q.get("explain") or {}).get("ref", "")
        if not ref:
            continue
        r = ref.lower()
        if any(k in r for k in KRAJ):
            kraj_count += 1
            continue
        if any(k in r for k, _ in kw_map):
            mapped_count += 1
        else:
            unmapped.append((q["id"], ref))

print()
print(f"KRAJ refs skipped: {kraj_count}")
print(f"Mapped refs: {mapped_count}")
print(f"Unmapped non-KRAJ refs: {len(unmapped)}")
for qid, ref in unmapped[:60]:
    print(f"  {qid}: {ref}")
