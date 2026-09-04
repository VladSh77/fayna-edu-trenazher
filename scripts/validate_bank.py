#!/usr/bin/env python3
#ОК-САМ
import json
import sys
from pathlib import Path

def validate_bank(filepath):
    """Validate questions bank JSON."""
    errors = []
    warnings = []

    # Load JSON
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"🔴 Файл не знайдено: {filepath}")
        return 1
    except json.JSONDecodeError as e:
        print(f"🔴 Неправильний JSON: {e}")
        return 1

    # Ensure it's a list
    if not isinstance(data, list):
        print("🔴 Корінь JSON повинен бути списком")
        return 1

    # Validate each question
    for idx, question in enumerate(data, 1):
        if not isinstance(question, dict):
            errors.append((idx, "питання повинно бути об'єктом"))
            continue

        # Check text field
        text = question.get('text', '').strip() if isinstance(question.get('text'), str) else ''
        if not text:
            errors.append((idx, "text не може бути порожнім"))

        # Check type field
        q_type = question.get('type', '').strip() if isinstance(question.get('type'), str) else ''
        if not q_type:
            errors.append((idx, "type не заповнений"))
            continue

        # Check correct field (required for non-text questions)
        if q_type != 'text':
            correct = question.get('correct')
            if correct is None or (isinstance(correct, str) and not correct.strip()):
                errors.append((idx, f"correct не заповнений (type='{q_type}')"))

        # Check explain field for text questions
        if q_type == 'text':
            explain = question.get('explain', '').strip() if isinstance(question.get('explain'), str) else ''
            if not explain:
                warnings.append((idx, "explain не заповнений"))

    # Print results
    has_errors = False

    if errors:
        has_errors = True
        error_nums = [str(idx) for idx, _ in errors]
        print(f"🔴 Помилки: {', '.join(error_nums)}")
        for idx, msg in errors:
            print(f"   #{idx}: {msg}")

    if warnings:
        warning_nums = [str(idx) for idx, _ in warnings]
        print(f"⚠️  Попередження: {', '.join(warning_nums)}")
        for idx, msg in warnings:
            print(f"   #{idx}: {msg}")

    if not errors and not warnings:
        print(f"✅ OK ({len(data)} питань)")

    return 1 if has_errors else 0

if __name__ == '__main__':
    # Get filepath from argument or use default
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = str(Path(__file__).parent.parent / 'questions.json')

    sys.exit(validate_bank(filepath))
