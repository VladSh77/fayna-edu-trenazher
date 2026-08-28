#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Діагностика 47 REF_INVALID питань (файл закону є, але стаття не витягується).
Для кожного питання сканує файл закону, витягує ВСІ доступні статті/пункти
і оцінює їх за ключовими словами correct-відповіді, щоб знайти правильний ref.
"""

import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

spec = importlib.util.spec_from_file_location(
    "sim", os.path.join(ROOT, "simulate/simulate.py")
)
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

# --- keyword scoring ---
STOP = set(
    """і та або але не ні чи що як для до з у на за від по про при без між через під над
це той ця це ці його її їх який яка яке які якій якої яких яким якими
бути є був була було були мати має мають може можуть повинен повинна повинні
відповідно згідно порядок строк термін випадок випадках випадку особа особи осіб
україна україни україні україною держава держави державі державою орган органи органу
закон закону законом законодавство законодавства право прав праві правом""".split()
)


def sig_words(text):
    words = re.findall(r"[А-Яа-яІіЇїЄєҐґA-Za-z]{4,}", text.lower())
    return [w for w in words if w not in STOP]


def score(correct, article_text):
    cw = set(sig_words(correct))
    aw = set(sig_words(article_text))
    if not cw:
        return 0.0, 0
    hit = len(cw & aw)
    return hit / len(cw), hit


def extract_all_articles(html_text):
    """Витягує всі статті 'Стаття N' + заголовки."""
    out = []
    # h3 Стаття N
    for m in re.finditer(
        r"<h3[^>]*>\s*([СC]таття\s+[0-9]+[^<]*)</h3>(.*?)(?=<h3|$)",
        html_text,
        re.IGNORECASE | re.DOTALL,
    ):
        title = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
        body = re.sub(r"<[^>]+>", " ", m.group(2)).strip()
        body = re.sub(r"\s+", " ", body)
        out.append((title, body))
    return out


def main():
    res = json.load(open(os.path.join(ROOT, "simulate/simulation_results.json")))
    results = res["results"]
    items = (
        list(results.items())
        if isinstance(results, dict)
        else [(r.get("id"), r) for r in results]
    )
    ri = [r for _, r in items if r.get("status") == "REF_INVALID"]

    exists = []
    for r in ri:
        ref = (
            (r.get("explain") or {}).get("ref", "")
            if isinstance(r.get("explain"), dict)
            else r.get("ref")
        )
        law = sim.legislation_file(ref)
        law_path = os.path.join(ROOT, "laws", law) if law else ""
        if law and os.path.exists(law_path):
            exists.append((r, law, law_path))

    print(f"REF_INVALID with existing file: {len(exists)}\n")
    for r, law, law_path in exists:
        ref = (
            (r.get("explain") or {}).get("ref", "")
            if isinstance(r.get("explain"), dict)
            else r.get("ref")
        )
        correct = r.get("correct", "")
        html = open(law_path, encoding="utf-8").read()
        articles = extract_all_articles(html)
        # score each article
        scored = []
        for title, body in articles:
            s, hits = score(correct, body)
            if s > 0:
                scored.append((s, title, hits))
        scored.sort(reverse=True)
        print(f"=== {r.get('id')} | {law}")
        print(f"    Q: {(r.get('question') or '')[:80]}")
        print(f"    correct: {correct[:80]}")
        print(f"    ref: {ref[:80]}")
        if scored:
            for s, t, h in scored[:3]:
                print(f"    -> {s:.2f} ({h}) | {t[:70]}")
        else:
            print(f"    -> НЕМАЄ статей зі збігом у файлі ({len(articles)} статей)")
        print()


if __name__ == "__main__":
    main()
