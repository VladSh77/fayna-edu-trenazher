#!/usr/bin/env python3
# #ОК-САМ
"""
Валідатор банку питань для fayna-edu-trenazher

Перевіряє структуру JSON-файлу, наявність обов'язкових полів,
непорожність критичних полів, та видає звіт з помилками (🔴) і попередженнями (⚠️).

Використання:
    python3 scripts/validate_bank.py <path-to-json>
    python3 scripts/validate_bank.py banks/mzs-2026.json
    python3 scripts/validate_bank.py banks/it-admin-interview.json
"""

import json
import sys
import os
from typing import List, Dict, Any


class BankValidator:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.data: Dict[str, Any] = {}
        self.total_questions = 0

    def load_json(self) -> bool:
        """Завантажує JSON-файл."""
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            return True
        except FileNotFoundError:
            self.errors.append(f"🔴 Файл не знайдений: {self.filepath}")
            return False
        except json.JSONDecodeError as e:
            self.errors.append(f"🔴 Помилка парсингу JSON: {e}")
            return False
        except Exception as e:
            self.errors.append(f"🔴 Помилка завантаження файлу: {e}")
            return False

    def validate_structure(self) -> bool:
        """Перевіряє базову структуру файлу."""
        if not isinstance(self.data, dict):
            self.errors.append("🔴 Коренева структура повинна бути об'єктом JSON")
            return False

        required_fields = ['title', 'sections']
        for field in required_fields:
            if field not in self.data:
                self.errors.append(f"🔴 Відсутнє обов'язкове поле: '{field}'")
                return False

        if not isinstance(self.data.get('title'), str):
            self.errors.append("🔴 Поле 'title' повинно бути рядком")
            return False

        if not self.data['title'].strip():
            self.errors.append("🔴 Поле 'title' порожнє")
            return False

        if not isinstance(self.data.get('sections'), list):
            self.errors.append("🔴 Поле 'sections' повинно бути масивом")
            return False

        if len(self.data['sections']) == 0:
            self.errors.append("🔴 Масив 'sections' порожній")
            return False

        return True

    def validate_questions(self) -> bool:
        """Перевіряє структуру питань."""
        has_errors = False

        for section_idx, section in enumerate(self.data.get('sections', [])):
            if not isinstance(section, dict):
                self.errors.append(f"🔴 [Розділ {section_idx}] Розділ повинен бути об'єктом")
                has_errors = True
                continue

            section_id = section.get('id', f'unknown_{section_idx}')

            section_fields = ['id', 'title', 'questions']
            for field in section_fields:
                if field not in section:
                    self.errors.append(f"🔴 [Розділ '{section_id}'] Відсутнє поле '{field}'")
                    has_errors = True

            if not isinstance(section.get('questions'), list):
                self.errors.append(f"🔴 [Розділ '{section_id}'] Поле 'questions' повинно бути масивом")
                has_errors = True
                continue

            for q_idx, question in enumerate(section.get('questions', [])):
                if not isinstance(question, dict):
                    self.errors.append(
                        f"🔴 [Розділ '{section_id}', питання {q_idx + 1}] Питання повинно бути об'єктом"
                    )
                    has_errors = True
                    continue

                question_id = question.get('id', f'unknown_{q_idx}')
                self.total_questions += 1

                required_q_fields = ['id', 'question', 'correct']
                for field in required_q_fields:
                    if field not in question:
                        self.errors.append(
                            f"🔴 [{question_id}] Відсутнє обов'язкове поле '{field}'"
                        )
                        has_errors = True

                question_text = question.get('question', '')
                if isinstance(question_text, str):
                    if not question_text.strip():
                        self.errors.append(f"🔴 [{question_id}] Текст питання порожній")
                        has_errors = True
                else:
                    self.errors.append(f"🔴 [{question_id}] Текст питання не є рядком")
                    has_errors = True

                correct = question.get('correct')
                if correct is None:
                    self.errors.append(f"🔴 [{question_id}] Поле 'correct' не визначено")
                    has_errors = True
                elif isinstance(correct, str):
                    if not correct.strip():
                        self.errors.append(f"🔴 [{question_id}] Поле 'correct' порожнє")
                        has_errors = True
                elif isinstance(correct, list):
                    if not correct or any(not str(c).strip() for c in correct if c):
                        self.errors.append(f"🔴 [{question_id}] Поле 'correct' містить порожні значення")
                        has_errors = True
                else:
                    self.errors.append(f"🔴 [{question_id}] Поле 'correct' має некоректний тип")
                    has_errors = True

                if 'wrong' in question:
                    wrong = question.get('wrong')
                    if not isinstance(wrong, list):
                        self.warnings.append(
                            f"⚠️ [{question_id}] Поле 'wrong' повинно бути масивом"
                        )
                    elif len(wrong) == 0:
                        self.warnings.append(f"⚠️ [{question_id}] Масив 'wrong' порожній")
                    else:
                        for w_idx, wrong_answer in enumerate(wrong):
                            if isinstance(wrong_answer, str):
                                if not wrong_answer.strip():
                                    self.errors.append(
                                        f"🔴 [{question_id}] Неправильна відповідь #{w_idx + 1} порожня"
                                    )
                                    has_errors = True
                            else:
                                self.errors.append(
                                    f"🔴 [{question_id}] Неправильна відповідь #{w_idx + 1} не є рядком"
                                )
                                has_errors = True

                if 'explain' in question:
                    explain = question.get('explain')
                    if isinstance(explain, dict):
                        if 'text' in explain:
                            if isinstance(explain['text'], str):
                                if not explain['text'].strip():
                                    self.warnings.append(
                                        f"⚠️ [{question_id}] Пояснення містить порожний текст"
                                    )
                            else:
                                self.warnings.append(
                                    f"⚠️ [{question_id}] Текст пояснення не є рядком"
                                )
                    else:
                        self.warnings.append(
                            f"⚠️ [{question_id}] Поле 'explain' повинно бути об'єктом"
                        )

        return not has_errors

    def validate_meta(self) -> None:
        """Перевіряє метаполя (total, count)."""
        if 'total' in self.data:
            declared_total = self.data['total']
            if not isinstance(declared_total, int):
                self.warnings.append("⚠️ Поле 'total' не є числом")
            elif declared_total != self.total_questions:
                self.warnings.append(
                    f"⚠️ Поле 'total' ({declared_total}) не збігається з фактичною "
                    f"кількістю питань ({self.total_questions})"
                )

        for section in self.data.get('sections', []):
            section_id = section.get('id', 'unknown')
            if 'count' in section:
                declared_count = section.get('count')
                actual_count = len(section.get('questions', []))
                if not isinstance(declared_count, int):
                    self.warnings.append(f"⚠️ [Розділ '{section_id}'] Поле 'count' не є числом")
                elif declared_count != actual_count:
                    self.warnings.append(
                        f"⚠️ [Розділ '{section_id}'] Поле 'count' ({declared_count}) "
                        f"не збігається з фактичною кількістю питань ({actual_count})"
                    )

    def print_report(self) -> None:
        """Видає звіт валідації."""
        print("\n" + "=" * 70)
        print(f"ВАЛІДАЦІЯ БАНКУ ПИТАНЬ: {os.path.basename(self.filepath)}")
        print("=" * 70)

        if self.data:
            print(f"\n📋 Файл: {self.filepath}")
            print(f"📚 Назва: {self.data.get('title', 'N/A')}")
            print(f"📊 Загалом питань: {self.total_questions}")
            print(f"📑 Розділів: {len(self.data.get('sections', []))}")

        if self.errors:
            print(f"\n🔴 ПОМИЛОК: {len(self.errors)}")
            for error in self.errors:
                print(f"   {error}")

        if self.warnings:
            print(f"\n⚠️  ПОПЕРЕДЖЕНЬ: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"   {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ ВАЛІДАЦІЯ УСПІШНА — немає помилок і попереджень!")

        print("\n" + "=" * 70 + "\n")

    def run(self) -> int:
        """Запускає повну валідацію."""
        if not self.load_json():
            self.print_report()
            return 1

        if not self.validate_structure():
            self.print_report()
            return 1

        self.validate_questions()
        self.validate_meta()
        self.print_report()

        return 1 if self.errors else 0


def main():
    if len(sys.argv) < 2:
        print("Використання: python3 scripts/validate_bank.py <path-to-json>")
        print("Приклад: python3 scripts/validate_bank.py banks/mzs-2026.json")
        sys.exit(1)

    filepath = sys.argv[1]
    validator = BankValidator(filepath)
    exit_code = validator.run()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
