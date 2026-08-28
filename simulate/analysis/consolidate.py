import json
from collections import Counter

BASE = "/Users/kobzar/projects/firm/platforms/fayna-edu-trenazher/simulate/analysis"

all_elements = []
for i in range(1, 9):
    with open(f"{BASE}/resolved_discrepancies_batch{i}.json") as f:
        batch = json.load(f)
    all_elements.extend(batch)

# Sort by n
all_elements.sort(key=lambda e: e["n"])

# Verify completeness
ns = [e["n"] for e in all_elements]
assert ns == list(range(1, 111)), f"Missing elements: {set(range(1, 111)) - set(ns)}"


# Classify statuses into canonical categories
def classify(status):
    s = status.lower()
    if s.startswith("ok") or s.startswith("correct"):
        return "OK/CORRECT"
    if s.startswith("fixed"):
        return "FIXED"
    if s.startswith("by_law"):
        return "BY_LAW"
    if s.startswith("not_in_law"):
        return "NOT_IN_LAW"
    if s.startswith("wrong_question") or s.startswith("wrong question"):
        return "WRONG_QUESTION_OR_ANSWER"
    if s.startswith("header") or s.startswith("meta"):
        return "HEADER/META"
    return "OTHER"


stats = Counter()
for e in all_elements:
    e["category"] = classify(e["status"])
    stats[e["category"]] += 1

result = {
    "meta": {
        "total": len(all_elements),
        "batches": 8,
        "categories": dict(stats),
    },
    "elements": all_elements,
}

with open(f"{BASE}/all_resolved_110.json", "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("=== FINAL STATISTICS (110 elements) ===")
for cat in [
    "OK/CORRECT",
    "FIXED",
    "BY_LAW",
    "NOT_IN_LAW",
    "WRONG_QUESTION_OR_ANSWER",
    "HEADER/META",
    "OTHER",
]:
    print(f"  {cat}: {stats.get(cat, 0)}")
print(f"  TOTAL: {len(all_elements)}")

# Per-batch breakdown
print("\n=== PER-BATCH ===")
for i in range(1, 9):
    with open(f"{BASE}/resolved_discrepancies_batch{i}.json") as f:
        batch = json.load(f)
    c = Counter(classify(e["status"]) for e in batch)
    print(f"  batch{i} ({batch[0]['n']}-{batch[-1]['n']}): {dict(c)}")
