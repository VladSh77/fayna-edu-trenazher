#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Діагностика TEXT_MISMATCH (42) та REF_INVALID (99) питань.
Для кожного питання:
  1) знаходить файл закону за ref;
  2) витягує ВСІ статті/пункти/параграфи з файлу;
  3) скорить кожен проти correct-відповіді за ключовими словами;
  4) друкує найкращі кандидати (номер статті/пункту) — щоб оновити ref.
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
    """Витягує всі статті 'Стаття N' + заголовки (h3)."""
    out = []
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


def extract_all_points(html_text):
    """Витягує всі пункти 'N.' (прості) з тіла документа."""
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)
    out = []
    for m in re.finditer(r"(?<!\d)(\d{1,3})\s*\.\s*", plain):
        num = m.group(1)
        rest = plain[m.end() :]
        nxt = re.search(r"(?<!\d)(\d{1,3})\s*\.\s*", rest)
        end = m.end() + nxt.start() if nxt else len(plain)
        body = plain[m.end() : end].strip()
        out.append((f"Пункт {num}", body))
    return out


def extract_all_sections(html_text):
    """Витягує всі параграфи '§ N.' (Регламент КМУ)."""
    plain = re.sub(r"<[^>]+>", " ", html_text)
    plain = re.sub(r"\s+", " ", plain)
    out = []
    for m in re.finditer(r"§\s*(\d+)\s*\.\s*", plain):
        num = m.group(1)
        rest = plain[m.end() :]
        nxt = re.search(r"§\s*\d+\s*\.\s*", rest)
        end = m.end() + nxt.start() if nxt else len(plain)
        body = plain[m.end() : end].strip()
        out.append((f"§ {num}", body))
    return out


def main():
    statuses = sys.argv[1:] if len(sys.argv) > 1 else ["TEXT_MISMATCH", "REF_INVALID"]
    res = json.load(open(os.path.join(ROOT, "simulate/simulation_results.json")))
    results = res["results"]
    items = (
        list(results.items())
        if isinstance(results, dict)
        else [(r.get("id"), r) for r in results]
    )
    target = [r for _, r in items if r.get("status") in statuses]

    for r in target:
        ref = r.get("ref", "")
        correct = r.get("correct", "")
        law = sim.legislation_file(ref)
        law_path = os.path.join(ROOT, "laws", law) if law else ""
        print("=" * 90)
        print(f"ID: {r.get('id')} | status: {r.get('status')} | law: {law}")
        print(f"Q: {(r.get('question') or '')[:150]}")
        print(f"CORRECT: {correct[:150]}")
        print(f"REF: {ref[:120]}")
        if not law or not os.path.exists(law_path):
            print("   -> НЕМАЄ файлу закону")
            continue
        html = open(law_path, encoding="utf-8").read()
        cands = []
        for title, body in extract_all_articles(html):
            s, h = score(correct, body)
            if s > 0:
                cands.append((s, h, title, body))
        # також пункти та параграфи
        for title, body in extract_all_points(html):
            s, h = score(correct, body)
            if s > 0:
                cands.append((s, h, title, body))
        for title, body in extract_all_sections(html):
            s, h = score(correct, body)
            if s > 0:
                cands.append((s, h, title, body))
        cands.sort(key=lambda x: (-x[0], -x[1]))
        if cands:
            for s, h, t, b in cands[:4]:
                print(f"   -> {s:.2f} ({h}) | {t[:60]} | {b[:80]}")
        else:
            print("   -> НЕМАЄ збігів у файлі")
        print()


if __name__ == "__main__":
    main()
