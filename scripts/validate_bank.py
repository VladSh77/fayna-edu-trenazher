#!/usr/bin/env python3
import json
import sys
import pathlib
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('file', nargs='?', default='questions_bank.json',
                        help='Path to the JSON file')
    args = parser.parse_args()
    file_path = pathlib.Path(args.file)

    if not file_path.is_file():
        print(f"Error: File not found: {file_path}")
        print("EXIT: 1")
        sys.exit(1)

    try:
        with file_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}")
        print("EXIT: 1")
        sys.exit(1)
    except OSError as e:
        print(f"Error: Cannot read file {file_path}")
        print("EXIT: 1")
        sys.exit(1)

    if not isinstance(data, list):
        print(f"Error: JSON root is not an array in {file_path}")
        print("EXIT: 1")
        sys.exit(1)

    errors = []
    warnings = []

    for idx, question in enumerate(data, start=1):
        if not isinstance(question, dict):
            errors.append((idx, "Question is not an object"))
            continue

        text = question.get('text')
        qtype = question.get('type')
        correct = question.get('correct')
        explain = question.get('explain')

        # Text validation
        if text is None or not isinstance(text, str) or not text.strip():
            errors.append((idx, "Text is empty"))
        else:
            stripped = text.strip()
            if len(stripped) < 5:
                warnings.append((idx, f"Text too short ({len(stripped)} chars)"))

        # Type validation
        if qtype is None or not isinstance(qtype, str) or not qtype.strip():
            errors.append((idx, "Field 'type' missing"))
        else:
            qtype_str = qtype.strip()
            # Correct field for non-text
            if qtype_str != 'text' and 'correct' not in question:
                errors.append((idx, "Field 'correct' missing"))
            # Explain field for text
            if qtype_str == 'text' and 'explain' not in question:
                errors.append((idx, "Field 'explain' missing"))
            # Explain present but type not text
            if 'explain' in question and qtype_str != 'text':
                warnings.append((idx, "Explain field present but type is not 'text'"))

    print(f"Validating: {file_path} ({len(data)} questions)")

    if errors:
        print("\n🔴 ERRORS:")
        for idx, msg in errors:
            print(f"  [{idx}] {msg}")

    if warnings:
        print("\n⚠️  WARNINGS:")
        for idx, msg in warnings:
            print(f"  [{idx}] {msg}")

    print(f"\nRESULT: {len(errors)} errors, {len(warnings)} warnings")
    exit_code = 1 if errors else 0
    print(f"EXIT: {exit_code}")
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
