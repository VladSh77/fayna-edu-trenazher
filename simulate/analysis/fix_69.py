import json

BANK = "/Users/kobzar/projects/firm/platforms/fayna-edu-trenazher/banks/mzs-2026.fixed2.json"

with open(BANK, encoding="utf-8") as f:
    bank = json.load(f)

target_id = "bank_dodatok3-1684"
found = False
for sec in bank["sections"]:
    for q in sec["questions"]:
        if q.get("id") == target_id:
            q["correct"] = (
                "не менше ніж у двох примірниках, один із яких залишається у справах"
            )
            q["wrong"] = [
                "будь-яка кількість за бажанням довірителя",
                "лише один примірник",
            ]
            q["explain"]["text"] = (
                "Відповідно до ст. 59 Закону України «Про нотаріат», документи, в яких "
                "викладено зміст правочинів (договори, заповіти, довіреності тощо), "
                "виготовляються нотаріусом не менше ніж у двох примірниках, один із яких "
                "залишається у справах державної нотаріальної контори, приватного нотаріуса "
                "або у виконавчому комітеті органу місцевого самоврядування."
            )
            q["explain"]["ref"] = "Закон України «Про нотаріат», ст. 59"
            # Remove disputed flag since it's now resolved
            q.pop("disputed", None)
            found = True
            break
    if found:
        break

if not found:
    print("ERROR: question not found")
else:
    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)
    print("Fixed #69 (bank_dodatok3-1684) in bank")
