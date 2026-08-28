#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт-заглушка для 49 питань розділу 1 MISSING_ACTS_LIST.md.

Ці 49 питань залежать від 20 актів, файлів яких НЕМАЄ в laws/.
ВАЖЛИВО: ref у banks/mzs-2026.fixed2.json для цих 49 питань УЖЕ є
цільовими (вони вже записані так, як мають бути після нормалізації).
Тому цей скрипт НЕ переписує ref — він:

  1) Додає 20 нових ключів LEGISLATION у simulate.py (щоб
     legislation_file() розпізнавав нові файли за ref). Ідемпотентно.
  2) Перевіряє, які з 20 файлів актів уже завантажено в laws/.
  3) Для наявних файлів — перевіряє, що ref витягується (FOUND)
     через legislation_file() + extract_article_by_ref().
  4) Звітує, які акти ще НЕ завантажено (PENDING) — їх треба
     завантажити, після чого повторно запустити скрипт.

Запуск (з кореня проєкту):
    # додати ключі LEGISLATION у simulate.py (ідемпотентно):
    python3 simulate/analysis/refactor_section1_stub.py --apply-legislation

    # перевірити, які акти є / які ref витягуються:
    python3 simulate/analysis/refactor_section1_stub.py --verify

    # (необов'язково) примусово переписати ref для 49 питань:
    python3 simulate/analysis/refactor_section1_stub.py --apply-refs
"""

import argparse
import json
import os
import sys

# Корінь проєкту (два рівні вгору від simulate/analysis/).
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAWS_DIR = os.path.join(ROOT, "laws")
BANK = os.path.join(ROOT, "banks", "mzs-2026.fixed2.json")
SIMULATE_PY = os.path.join(ROOT, "simulate", "simulate.py")

# =====================================================================
# 20 нових актів: (ключі LEGISLATION, цільовий файл у laws/)
# Порядок має значення: специфічніші ключі — раніше.
# =====================================================================
NEW_LEGISLATION = [
    (["Договір про Європейський Союз"], "dohovir-pro-yevropeiskyi-soiuz.html"),
    (
        ["Договір про функціонування Європейського Союзу"],
        "dohovir-pro-funktsionuvannia-yes.html",
    ),
    (
        [
            "Гаазька конвенція",
            "легалізації іноземних офіційних документів",
            "апостиль",
        ],
        "haazka-konventsiia-apostyl.html",
    ),
    (
        ["Порядок провадження за заявами і поданнями з питань громадянства"],
        "poriadok-provadzhennia-hromadianstvo.html",
    ),
    (
        ["Інструкція про витребування документів"],
        "instruktsiia-vytrebuvannia-dokumentiv.html",
    ),
    (
        ["Правила державної реєстрації актів цивільного стану"],
        "pravyla-derzhavnoi-reiestratsii-aktiv.html",
    ),
    (
        ["Порядок ведення Державного реєстру виборців"],
        "poriadok-vedennia-reiestru-vyborciv.html",
    ),
    (["№ 368"], "postanova-kmu-368-vizy.html"),
    (["№ 954"], "postanova-kmu-954.html"),
    (["№ 776"], "postanova-kmu-776.html"),
    (
        ["взаємну допомогу у кримінальних справах"],
        "yevropeiska-konventsiia-vzaiemna-dopomoha.html",
    ),
    (["приймання в експлуатацію"], "poriadok-pryimannia-ekspluatatsiiu.html"),
    (["№ 651"], "postanova-kmu-651-zakhyst-hromadian.html"),
    (
        ["надзвичайного стану", "надзвичайних ситуацій"],
        "zakon-pro-nadzvychaini-sytuatsii.html",
    ),
    (
        ["основи соціальної захищеності"],
        "zakon-pro-osnovy-sotsialnoi-zakhyshchenosti.html",
    ),
    (["№ 750"], "postanova-kmu-750-apostyl.html"),
    (
        ["нештатних (почесних) консулів", "почесних консулів"],
        "polozhennia-pro-pochesnykh-konsuliv.html",
    ),
    (["Копенгагенські критерії"], "kopenhahenski-kryterii.html"),
    (["Шенгенська угода"], "shenhenska-uhoda.html"),
    (
        ["засідань окремих двосторонніх органів асоціації"],
        "postanova-kmu-zasidannia-orhaniv-asotsiatsii.html",
    ),
]

# =====================================================================
# 49 питань розділу 1: (id, цільовий ref)
# ref УЖЕ є цільовим у банку — тут він для перевірки/примусового запису.
# =====================================================================
SECTION1_FIXES = [
    # Договір про ЄС (7) — загальні знання про ЄС, не конкретна норма права.
    # Перекласифіковано в KRAJOZNAWSTWO (ключове слово "Загальні знання про ЄС").
    ("2019-11-26-dod2-1271", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1272", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1278", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1279", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1300", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1301", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1281", "Загальні знання про ЄС"),
    # Апостильна конвенція (7)
    ("bank_dodatok3-1693", "Гаазька конвенція 1961 року, ст. 1"),
    ("bank_dodatok3-1694", "Гаазька конвенція 1961 року, ст. 1"),
    (
        "bank_dodatok3-1696",
        "Гаазька конвенція про скасування вимоги легалізації іноземних офіційних документів, ст. 1",
    ),
    # 1699: відповідь — дата набуття чинності (метадані документа), а не норма
    #   статті → KRAJOZNAWSTWO.
    ("bank_dodatok3-1699", "Загальні знання про консульську діяльність"),
    (
        "bank_dodatok3-1701",
        "Гаазька конвенція про скасування вимоги легалізації іноземних офіційних документів, ст. 1",
    ),
    (
        "bank_dodatok3-1702",
        "Гаазька конвенція про скасування вимоги легалізації іноземних офіційних документів, ст. 1",
    ),
    (
        "bank_dodatok3-1703",
        "Гаазька конвенція про скасування вимоги легалізації іноземних офіційних документів, ст. 1",
    ),
    # Порядок громадянства (4)
    # 1722: п. 12 розділу ІІІ — хибний збіг (п. 12 про належність до громадянства,
    #   а не про залишення на постійне проживання). Джерело норми (Порядок
    #   оформлення документів для залишення на постійне проживання за кордоном)
    #   недоступне → KRAJOZNAWSTWO.
    ("bank_dodatok3-1722", "Загальні знання про консульську діяльність"),
    # 1727: відповідь «Керівник ЗДУ» підтверджується п. 132 Порядку
    #   (консульська посадова особа посольства/консульської установи).
    (
        "bank_dodatok3-1727",
        "Порядок провадження за заявами і поданнями з питань громадянства (постанова КМУ), п. 132",
    ),
    # 1730, 1731: норми про залишення на постійне проживання за кордоном
    #   (ЗДУ, СБУ, 16-річний вік) НЕ містяться в Порядку провадження — вони
    #   належать до недоступного Порядку оформлення документів для залишення
    #   на постійне проживання за кордоном → KRAJOZNAWSTWO.
    ("bank_dodatok3-1730", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1731", "Загальні знання про консульську діяльність"),
    # Інструкція витребування (5) — файл завантажено неправильно (Наказ про
    #   втрату чинності), правильний документ недоступний → KRAJOZNAWSTWO.
    ("bank_dodatok3-1705", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1706", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1711", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1712", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1714", "Загальні знання про консульську діяльність"),
    # Правила реєстрації актів (4) — завантажено стару редакцію (Наказ № 52/5
    #   від 18.10.2000), норми питань (нумерація, звітування, ст. 135 СК,
    #   30 календарних днів) у ній відсутні → KRAJOZNAWSTWO.
    ("bank_dodatok3-1662", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1663", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1666", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1667", "Загальні знання про консульську діяльність"),
    # Порядок реєстру виборців (3) — файл завантажено неправильно (Постанова
    #   про внесення змін), правильний документ недоступний → KRAJOZNAWSTWO.
    ("bank_dodatok3-1744", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1746", "Загальні знання про консульську діяльність"),
    ("bank_dodatok3-1747", "Загальні знання про консульську діяльність"),
    # Договір про функціонування ЄС (2) — загальні знання про ЄС (KRAJOZNAWSTWO)
    ("2019-11-26-dod2-1243", "Загальні знання про ЄС"),
    ("2019-11-26-dod2-1302", "Загальні знання про ЄС"),
    # Постанова № 368 / № 954 — це постанови-зміни до Правил оформлення віз.
    # Норми (п. 5, п. 19, п. 20) реально витягуються з базового акта
    # pravyla-oformlennia-viz.html (Постанова КМУ № 118 від 01.03.2017).
    ("bank_dodatok3-1804", "Правила оформлення віз, п. 5"),
    ("bank_dodatok3-1808", "Правила оформлення віз, п. 19"),
    ("bank_dodatok3-1805", "Правила оформлення віз, п. 20"),
    # Постанова № 776 (1)
    ("bank_dodatok3-1806", "Постанова КМ № 776 від 28.07.2021, п. 4"),
    # Європейська конвенція (1)
    (
        "bank_dodatok3-1789",
        "Європейська конвенція про взаємну допомогу у кримінальних справах, ст. 10",
    ),
    # Приймання в експлуатацію (1) — ref не збігається з джерелом норми
    #   (відповідь «2 примірники» походить з Положення про інвентаризацію,
    #   а не з Порядку приймання в експлуатацію) → KRAJOZNAWSTWO.
    ("dodatok-4-564", "Загальні знання про консульську діяльність"),
    # Постанова № 651 (1)
    ("bank_dodatok3-1766", "Постанова КМУ від 11.07.2012 № 651, п. 2"),
    # Надзвичайний стан (1)
    (
        "bank_dodatok3-1768",
        "Закон України «Про забезпечення прав і свобод громадян України під час надзвичайних ситуацій», ст. 10",
    ),
    # Соц. захищеність (1)
    (
        "bank_dodatok3-1770",
        "Закон України «Про основи соціальної захищеності громадян», ст. 12",
    ),
    # Постанова № 750 (1) — файл завантажено неправильно (Порядок прийняття
    #   в експлуатацію, а не постанова про апостиль) → KRAJOZNAWSTWO.
    ("bank_dodatok3-1700", "Загальні знання про консульську діяльність"),
    # Почесні консули (1) — файл завантажено неправильно (ДПА Наказ про
    #   акцизний збір), правильний документ недоступний → KRAJOZNAWSTWO.
    ("bank_dodatok3-1811", "Загальні знання про консульську діяльність"),
    # Копенгагенські критерії (1) — загальні знання про ЄС (KRAJOZNAWSTWO)
    ("2019-11-26-dod2-1252", "Загальні знання про ЄС"),
    # Шенгенська угода (1)
    ("2019-11-26-dod2-1291", "Шенгенська угода, стаття 1"),
    # Засідання органів асоціації (1)
    (
        "2019-11-26-dod2-1306",
        "Постанова Кабінету Міністрів України «Питання підготовки та проведення засідань окремих двосторонніх органів асоціації між Україною та ЄС», п. 1",
    ),
]

# =====================================================================
# Реф-нормалізація для питань, що НЕ залежать від відсутніх актів,
# але були помилково віднесені до розділу 1. Їх можна виправити ЗАРАЗ,
# без завантаження файлів (файл акта вже є в laws/).
#
# dodatok-4-031/042/102: ref був коротким «ст. N» (не зіставлявся з
# LEGISLATION). Розширюємо до повного «Закон України «Про громадянство
# України», ст. N» — витягується з наявного zakon-pro-hromadianstvo.html.
# =====================================================================
SECTION1_REF_FIXES = [
    ("dodatok-4-031", "ст. 25", "Закон України «Про громадянство України», ст. 25"),
    ("dodatok-4-042", "ст. 18", "Закон України «Про громадянство України», ст. 18"),
    ("dodatok-4-102", "ст. 7", "Закон України «Про громадянство України», ст. 7"),
]


# =====================================================================
# Додавання ключів LEGISLATION у simulate.py (ідемпотентно)
# =====================================================================
def apply_legislation():
    if not os.path.exists(SIMULATE_PY):
        print(f"ПОМИЛКА: не знайдено {SIMULATE_PY}")
        sys.exit(1)

    with open(SIMULATE_PY, encoding="utf-8") as f:
        src = f.read()

    # Знаходимо кінець списку LEGISLATION: рядок "]" на тому ж рівні.
    # Шукаємо останній "]" після "LEGISLATION = [".
    start = src.find("LEGISLATION = [")
    if start == -1:
        print("ПОМИЛКА: не знайдено 'LEGISLATION = [' у simulate.py")
        sys.exit(1)

    # Знаходимо закривну дужку списку (перший "]" на нульовому рівні вкладеності).
    depth = 0
    end = -1
    i = src.find("[", start)
    for j in range(i, len(src)):
        if src[j] == "[":
            depth += 1
        elif src[j] == "]":
            depth -= 1
            if depth == 0:
                end = j
                break
    if end == -1:
        print("ПОМИЛКА: не вдалося знайти кінець списку LEGISLATION")
        sys.exit(1)

    # Перевіряємо, які ключі вже додано (щоб не дублювати).
    existing = src[start:end]
    to_add = []
    for keys, fname in NEW_LEGISLATION:
        # Вважаємо акт уже доданим, якщо його файл згадується в LEGISLATION.
        if fname in existing:
            continue
        to_add.append((keys, fname))

    if not to_add:
        print("Усі 20 ключів LEGISLATION уже присутні в simulate.py. Нічого не додаю.")
        return

    # Формуємо блок нових записів перед закривною дужкою.
    lines = []
    for keys, fname in to_add:
        if len(keys) == 1:
            lines.append(f'    (["{keys[0]}"], "{fname}"),')
        else:
            lines.append("    (")
            lines.append("        [")
            for k in keys:
                lines.append(f'            "{k}",')
            lines.append("        ],")
            lines.append(f'        "{fname}",')
            lines.append("    ),")

    block = "\n".join(lines)
    new_src = (
        src[:end]
        + "\n    # --- Розділ 1: відсутні акти (додано refactor_section1_stub.py) ---\n"
        + block
        + "\n"
        + src[end:]
    )

    with open(SIMULATE_PY, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"Додано {len(to_add)} ключів LEGISLATION у simulate.py:")
    for keys, fname in to_add:
        print(f"  {keys} -> {fname}")


# =====================================================================
# Перевірка наявності файлів і витягуваності ref
# =====================================================================
def load_legislation():
    """Повертає (keys, fname) список з simulate.py (імпортуємо функцію)."""
    # Імпортуємо legislation_file з simulate.py.
    sys.path.insert(0, os.path.join(ROOT, "simulate"))
    import simulate as sim

    return sim


def verify():
    # Файли, які вже є в laws/.
    present = set(os.listdir(LAWS_DIR)) if os.path.isdir(LAWS_DIR) else set()

    # Групуємо 46 питань відсутніх актів за цільовим файлом.
    by_file = {}
    for qid, ref in SECTION1_FIXES:
        fname = None
        for keys, f in NEW_LEGISLATION:
            rl = ref.lower()
            if any(k.lower() in rl for k in keys):
                fname = f
                break
        by_file.setdefault(fname, []).append((qid, ref))

    print("=== СТАН АКТІВ РОЗДІЛУ 1 (20 актів / 46 питань) ===\n")
    total_present = 0
    total_pending = 0
    for fname, items in by_file.items():
        if fname is None:
            print(f"  [??] {len(items)} питань без зіставленого файлу:")
            for qid, ref in items:
                print(f"        {qid}: {ref}")
            continue
        exists = fname in present
        if exists:
            total_present += 1
            status = "OK (файл є)"
        else:
            total_pending += 1
            status = "PENDING (файлу НЕМАЄ)"
        print(f"  [{status}] {fname} — {len(items)} питань")
        for qid, ref in items:
            print(f"        {qid}")

    print(
        f"\nРазом: {total_present} актів завантажено, {total_pending} ще НЕ завантажено."
    )

    # --- 3 питання громадянства: реф-нормалізація проти наявного файлу ---
    print("\n=== РЕФ-НОРМАЛІЗАЦІЯ (не залежить від завантаження) ===")
    sim = load_legislation()
    for qid, old_sub, new_ref in SECTION1_REF_FIXES:
        lf = sim.legislation_file(new_ref)
        if lf and lf in present:
            path = os.path.join(LAWS_DIR, lf)
            with open(path, encoding="utf-8", errors="replace") as f:
                html_text = f.read()
            art = sim.extract_article_by_ref(html_text, new_ref)
            if art and art[0]:
                print(f"  [FOUND] {qid} -> {lf} :: {art[0][:80]}")
            else:
                print(f"  [NO_ARTICLE] {qid} -> {lf} :: ref='{new_ref}'")
        else:
            print(f"  [PENDING] {qid} -> файл '{lf}' не знайдено")

    # Для наявних файлів — перевіряємо витягуваність ref.
    if total_present:
        print("\n=== ПЕРЕВІРКА ВИТЯГУВАННЯ REF ДЛЯ НАЯВНИХ ФАЙЛІВ ===")
        for fname, items in by_file.items():
            if fname is None or fname not in present:
                continue
            path = os.path.join(LAWS_DIR, fname)
            with open(path, encoding="utf-8", errors="replace") as f:
                html_text = f.read()
            for qid, ref in items:
                lf = sim.legislation_file(ref)
                art = sim.extract_article_by_ref(html_text, ref) if lf else None
                if art and art[0]:
                    print(f"  [FOUND] {qid} -> {fname} :: {art[0][:80]}")
                else:
                    print(f"  [NO_ARTICLE] {qid} -> {fname} :: ref='{ref}'")


# =====================================================================
# Примусовий перезапис ref для 49 питань (безпечна сітка)
# =====================================================================
def apply_refs():
    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)

    by_id = {}
    for sec in bank["sections"]:
        for q in sec.get("questions", []):
            by_id[q["id"]] = q

    applied = []
    not_found = []

    # --- SECTION1_FIXES: цільові ref для 46 питань відсутніх актів ---
    for qid, new_ref in SECTION1_FIXES:
        q = by_id.get(qid)
        if q is None:
            not_found.append((qid, "question id not found"))
            continue
        old = q.get("explain", {}).get("ref", "")
        if old == new_ref:
            continue  # уже цільовий
        q["explain"]["ref"] = new_ref
        applied.append((qid, old, new_ref))

    # --- SECTION1_REF_FIXES: реф-нормалізація 3 питань громадянства ---
    for qid, old_sub, new_ref in SECTION1_REF_FIXES:
        q = by_id.get(qid)
        if q is None:
            not_found.append((qid, "question id not found"))
            continue
        old = q.get("explain", {}).get("ref", "")
        if old_sub not in old:
            not_found.append((qid, f"ref value mismatch (очікувано '{old_sub}')", old))
            continue
        q["explain"]["ref"] = new_ref
        applied.append((qid, old, new_ref))

    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

    print(f"Перезаписано ref: {len(applied)}")
    for a in applied:
        print(f"  [{a[0]}] '{a[1]}' -> '{a[2]}'")
    if not_found:
        print("НЕ ЗНАЙДЕНО питань:")
        for nf in not_found:
            print(f"  {nf}")


def main():
    parser = argparse.ArgumentParser(
        description="Скрипт-заглушка для 49 питань розділу 1"
    )
    parser.add_argument(
        "--apply-legislation",
        action="store_true",
        help="Додати 20 ключів LEGISLATION у simulate.py (ідемпотентно)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Перевірити наявність файлів і витягуваність ref",
    )
    parser.add_argument(
        "--apply-refs",
        action="store_true",
        help="Примусово переписати ref для 49 питань (безпечна сітка)",
    )
    args = parser.parse_args()

    if args.apply_legislation:
        apply_legislation()
    if args.apply_refs:
        apply_refs()
    if args.verify or not (args.apply_legislation or args.apply_refs):
        verify()


if __name__ == "__main__":
    main()
