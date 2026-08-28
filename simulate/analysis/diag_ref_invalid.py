#!/usr/bin/env python3
"""Діагностика REF_INVALID: для кожного питання показує, який файл акта
знаходить legislation_file(ref) і чи знаходить extract_article_by_ref статтю."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from simulate import LAWS_DIR, extract_article_by_ref, legislation_file  # noqa: E402

with open(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "simulation_results.json"
    )
) as f:
    data = json.load(f)

items = data["results"]
ref_inv = [i for i in items if i.get("status") == "REF_INVALID"]
print(f"TOTAL REF_INVALID: {len(ref_inv)}")

for i in ref_inv:
    qid = i["id"]
    ref = i.get("ref") or ""
    fname = legislation_file(ref)
    status = "NO_ACT" if not fname else "ACT_OK"
    art = "?"
    if fname:
        path = LAWS_DIR / fname
        if path.exists():
            html = path.read_text(encoding="utf-8", errors="replace")
            title, body = extract_article_by_ref(html, ref)
            art = "FOUND" if body else "NO_ARTICLE"
        else:
            art = "NO_FILE"
    print(f"{qid} | {status} | {art} | {fname} | {ref[:80]}")
