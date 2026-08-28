#!/usr/bin/env python3
"""Класифікація решти 110 розбіжностей за першопричиною."""
import json
import sys
from collections import Counter

PROJECT = "/Users/kobzar/projects/firm/platforms/fayna-edu-trenazher"
sys.path.insert(0, f"{PROJECT}/simulate")

from simulate import (
    LAWS_DIR, META_ANSWER_RE, answer_matches_article,
    extract_article_by_ref, legislation_file, significant_words, stem_ratio,
)

FIXED_THIS_SESSION = {"dodatok-4-307", "bank_dodatok3-1697"}

def classify(q):
    ref = q.get("ref", "")
    correct = q.get("correct", "")

    if META_ANSWER_RE.search(correct):
        return "META"

    sig = significant_words(correct)
    if len(sig) < 3:
        return "SHORT_ANSWER"

    law_file = legislation_file(ref)
    if law_file is None:
        return "NO_LAW_FILE"

    try:
        with open(LAWS_DIR / law_file, encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return "NO_LAW_FILE"

    title, art = extract_article_by_ref(html, ref)
    if art is None:
        return "NO_ARTICLE"

    if "Угода про асоціацію" in ref:
        return "EU_GENERAL"

    if "консульськ" in ref.lower() and any(
        k in correct.lower() for k in ["померл", "загибл", "смерт", "особи померлого"]
    ):
        return "CONSULAR_SRC"

    matched, ratio, words = answer_matches_article(correct, art)
    if matched:
        return "PARAPHRASE_VERIFIED"
    sratio = stem_ratio(correct, art)
    if sratio >= 0.5:
        return "PARAPHRASE_STEM"
    return "PARAPHRASE_UNVERIFIED"

def main():
    with open(f"{PROJECT}/simulate/analysis/remaining_112.json", encoding="utf-8") as f:
        data = json.load(f)
    data = [d for d in data if d["id"] not in FIXED_THIS_SESSION]
    print(f"Аналізую {len(data)} розбіжностей\n")

    results = []
    for d in data:
        cat = classify(d)
        results.append((cat, d))
        print(f"[{cat:22s}] {d['id']:22s} ans={d['correct'][:45]!r}")

    print("\n=== ПІДСУМОК ===")
    c = Counter(cat for cat, _ in results)
    for cat, n in c.most_common():
        print(f"  {cat:22s}: {n}")

if __name__ == "__main__":
    main()
