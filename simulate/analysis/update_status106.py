import json

BASE = "/Users/kobzar/projects/firm/platforms/fayna-edu-trenazher/simulate/analysis"

with open(f"{BASE}/manual_110.json") as f:
    manual = json.load(f)

for el in manual:
    if el["n"] == 106:
        el["status"] = "BY_LAW (СК ст.135 не деталізує «дата народження» — Правила АЦС)"
        print("Updated #106 status:", el["status"])

with open(f"{BASE}/manual_110.json", "w") as f:
    json.dump(manual, f, ensure_ascii=False, indent=2)
