#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Крок 2: LLM-семантичний аудит елементів категорій OK/CORRECT + FIXED.

Для кожного елемента:
  1) знаходимо файл акта в laws/ через legislation_file(ref);
  2) витягуємо текст статті через extract_article_by_ref(html_text, ref);
  3) викликаємо verify_with_llm(question, correct, article_text);
  4) записуємо результат (ТАК/НІ/None) у звіт llm_audit_55.json.

Результат аудиту — які елементи семантично підтверджені, які ні.
"""

import json
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parent
PROJECT = WORK.parent.parent
LAWS_DIR = PROJECT / "laws"

sys.path.insert(0, str(WORK.parent))  # simulate/
import simulate  # noqa: E402

sys.path.insert(0, str(WORK))  # analysis/
import robust_extract  # noqa: E402

ALL_RESOLVED = WORK / "all_resolved_110.json"
OUT = WORK / "llm_audit_55.json"

# Обрізання тексту статті, що передається LLM. Збільшено з 1500 до 6000,
# щоб довгі статті (напр. ст.1 громадянство, ст.25 дипслужба) не втрачали
# потрібний фрагмент (Крок 2e: #2, #13).
TRUNCATE = 6000

# Маркери питань типу «що НЕ...» — правильна відповідь навмисно ВІДСУТНЯ в статті
# (це й робить її правильною), тому звичайна перевірка «чи узгоджується відповідь
# з текстом» дає хибний False. Для таких питань логіку перевірки інвертуємо.
NEGATION_MARKERS = (
    "не відноситься",
    "не є",
    "не можуть",
    "не може",
    "не належить",
    "не входить",
    "не є підставою",
    "не є причиною",
    "не можуть бути",
    "не є обов",
    "не підляга",
    "не визна",
    "не застосову",
)


def _is_negation_question(q: str) -> bool:
    ql = q.lower()
    return any(m in ql for m in NEGATION_MARKERS)


def verify_which_not(q, correct, wrong, article_text, max_chars=12000):
    """Перевірка для питань типу «що НЕ...».

    Правильна відповідь має бути ВІДСУТНЯ в тексті статті, а неправильні
    варіанти — ПРИСУТНІ. Повертає (bool, provider).
    """
    wrong_text = "; ".join(wrong) if wrong else "(немає)"
    system = (
        "Ти — експерт з українського законодавства. Питання сформульоване як "
        "'що НЕ...' (що не відноситься / не є / не можуть тощо). У таких питаннях "
        "ПРАВИЛЬНА відповідь — це варіант, якого НЕМАЄ в тексті статті, а "
        "НЕПРАВИЛЬНІ варіанти — ті, що в тексті ПРИСУТНІ. "
        "Перевір, чи правильна відповідь дійсно ВІДСУТНЯ в тексті статті, "
        "а всі неправильні варіанти ПРИСУТНІ. Відповідай лише: ТАК або НІ."
    )
    user = (
        f"ПИТАННЯ:\n{q}\n\n"
        f"ПРАВИЛЬНА ВІДПОВІДЬ (має бути ВІДСУТНЯ в тексті):\n{correct}\n\n"
        f"НЕПРАВИЛЬНІ ВІДПОВІДІ (мають бути ПРИСУТНІ в тексті):\n{wrong_text}\n\n"
        f"ТЕКСТ СТАТТІ:\n{article_text[:max_chars]}\n\n"
        f"Чи підтверджує текст статті, що правильна відповідь ВІДСУТНЯ, "
        f"а неправильні ПРИСУТНІ? Відповідь: ТАК або НІ."
    )
    llm = simulate._load_llm()
    if llm is None:
        return None, None
    try:
        provider, output = llm.chat_fallback(
            system,
            user,
            chain=simulate.LLM_CHAIN,
            timeout=simulate.LLM_TIMEOUT,
            max_tokens=simulate.LLM_MAX_TOKENS,
        )
        if not output:
            return None, provider
        out = output.strip().upper()
        if out.startswith("ТАК") or out.startswith("YES"):
            return True, provider
        if out.startswith("НІ") or out.startswith("NO"):
            return False, provider
        return None, provider
    except Exception:
        return None, None


def main():
    data = json.loads(ALL_RESOLVED.read_text(encoding="utf-8"))
    elements = data["elements"]

    targets = [e for e in elements if e.get("category") in ("OK/CORRECT", "FIXED")]
    print(f"Цільових елементів для аудиту: {len(targets)}")

    results = []
    no_file = []
    no_article = []
    for e in targets:
        n = e["n"]
        ref = e.get("ref") or ""
        q = e.get("question", "")
        correct = e.get("correct", "")

        fname = simulate.legislation_file(ref)
        if not fname:
            no_file.append(n)
            results.append(
                {
                    "n": n,
                    "id": e.get("id"),
                    "category": e.get("category"),
                    "ref": ref,
                    "status": "NO_FILE",
                    "verdict": None,
                    "provider": None,
                    "article": None,
                }
            )
            continue

        html_path = LAWS_DIR / fname
        if not html_path.exists():
            no_file.append(n)
            results.append(
                {
                    "n": n,
                    "id": e.get("id"),
                    "category": e.get("category"),
                    "ref": ref,
                    "status": "NO_FILE",
                    "verdict": None,
                    "provider": None,
                    "article": None,
                }
            )
            continue

        html_text = html_path.read_text(encoding="utf-8")
        # Ключові слова для розв'язання неоднозначної нумерації пунктів
        # (консолідовані документи з кількома 'п. N').
        keywords = (q + " " + correct).split()
        title, body = robust_extract.robust_extract_article_by_ref_scored(
            html_text, ref, keywords
        )
        if not body:
            no_article.append(n)
            results.append(
                {
                    "n": n,
                    "id": e.get("id"),
                    "category": e.get("category"),
                    "ref": ref,
                    "status": "NO_ARTICLE",
                    "verdict": None,
                    "provider": None,
                    "article": None,
                }
            )
            continue

        article_text = simulate.strip_tags(body)
        # Передаємо LLM більше контексту статті (за замовчуванням 3000 символів),
        # щоб довгі статті (напр. ст.1 громадянство) не втрачали потрібний фрагмент.
        wrong = e.get("wrong") or []
        if _is_negation_question(q):
            # Питання типу «що НЕ...»: правильна відповідь навмисно ВІДСУТНЯ в статті,
            # тому використовуємо інвертовану перевірку (Крок 2f: #11, #12, #35).
            verdict, provider = verify_which_not(
                q, correct, wrong, article_text, max_chars=12000
            )
        else:
            verdict, provider = simulate.verify_with_llm(
                q, correct, article_text, max_chars=12000
            )
        results.append(
            {
                "n": n,
                "id": e.get("id"),
                "category": e.get("category"),
                "ref": ref,
                "status": "OK",
                "verdict": verdict,
                "provider": provider,
                "article_title": title,
                "article_text": article_text[:TRUNCATE],
            }
        )
        print(f"  #{n} [{e.get('category')}] verdict={verdict} provider={provider}")

    summary = {
        "total_targets": len(targets),
        "no_file": no_file,
        "no_article": no_article,
        "verified_yes": [r["n"] for r in results if r["verdict"] is True],
        "verified_no": [r["n"] for r in results if r["verdict"] is False],
        "llm_unavailable": [
            r["n"] for r in results if r["verdict"] is None and r["status"] == "OK"
        ],
    }
    out = {"summary": summary, "results": results}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== ПІДСУМОК ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\nЗвіт збережено: {OUT}")


if __name__ == "__main__":
    main()
