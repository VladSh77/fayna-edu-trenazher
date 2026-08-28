import json

BASE = "/Users/kobzar/projects/firm/platforms/fayna-edu-trenazher/simulate/analysis"

NEW_CORRECT = "не менше ніж у двох примірниках, один із яких залишається у справах"
NEW_WRONG = ["будь-яка кількість за бажанням довірителя", "лише один примірник"]
NEW_STATUS = "FIXED (ст.59: не менше ніж у двох примірниках)"
NEW_VERIF = (
    "Виправлено: ст.59 Закону про нотаріат вимагає виготовлення документів (довіреностей) "
    "не менше ніж у двох примірниках, один із яких залишається у справах. Попередня відповідь "
    "'будь-яка кількість за бажанням довірителя' суперечила ст.59 (довіритель не може замовити "
    "лише один примірник). correct оновлено, wrong переставлено, банк виправлено."
)

# Update manual_110.json
with open(f"{BASE}/manual_110.json") as f:
    manual = json.load(f)
for el in manual:
    if el["n"] == 69:
        el["correct"] = NEW_CORRECT
        el["wrong"] = NEW_WRONG
        el["status"] = NEW_STATUS
        print("manual_110 #69 updated")
with open(f"{BASE}/manual_110.json", "w") as f:
    json.dump(manual, f, ensure_ascii=False, indent=2)

# Update all_resolved_110.json
with open(f"{BASE}/all_resolved_110.json") as f:
    data = json.load(f)
for el in data["elements"]:
    if el["n"] == 69:
        el["correct"] = NEW_CORRECT
        el["wrong"] = NEW_WRONG
        el["status"] = NEW_STATUS
        el["verification"] = NEW_VERIF
        el["category"] = "FIXED"
        print("all_resolved_110 #69 updated")
# Recompute category stats
from collections import Counter

stats = Counter(e["category"] for e in data["elements"])
data["meta"]["categories"] = dict(stats)
with open(f"{BASE}/all_resolved_110.json", "w") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("all_resolved_110 categories:", dict(stats))
