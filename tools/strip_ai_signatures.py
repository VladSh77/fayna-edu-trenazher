#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys

AI_PATTERNS = [
    r'Co-Authored-By:.*(?:Claude|Anthropic|noreply@anthropic\.com|GPT|Copilot|Cursor)',
    r'🤖 Generated with .*',
    r'Generated with Claude .*',
    r'Created by Claude .*',
]

def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ПОМИЛКА: команда {' '.join(cmd)} завершилась з кодом {result.returncode}")
        print(result.stderr)
        sys.exit(2)
    return result

def count_ai_signatures(repo):
    result = run(['git', 'log', '--format=%B'], cwd=repo)
    count = 0
    for commit_msg in result.stdout.split('\n\n'):
        for line in commit_msg.splitlines():
            for pattern in AI_PATTERNS:
                if re.search(pattern, line):
                    count += 1
                    break
    return count

def count_commits(repo):
    result = run(['git', 'rev-list', '--count', 'HEAD'], cwd=repo)
    return int(result.stdout.strip())

def create_backup_branch(repo, label):
    base = f"backup/pre-strip-{label}"
    branch = base
    suffix = 2
    while True:
        result = run(['git', 'rev-parse', '--verify', '--quiet', branch], cwd=repo, check=False)
        if result.returncode != 0:
            break
        branch = f"{base}-{suffix}"
        suffix += 1
    run(['git', 'branch', branch], cwd=repo)
    print(f"Бекап-гілка: {branch}")
    return branch

def filter_msg(msg):
    lines = msg.splitlines()
    filtered = []
    for line in lines:
        if any(re.search(pattern, line) for pattern in AI_PATTERNS):
            continue
        filtered.append(line)
    while filtered and filtered[-1] == '':
        filtered.pop()
    return '\n'.join(filtered) + ('\n' if filtered else '')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--label', default='ai-sig')
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    if not os.path.isdir(os.path.join(repo, '.git')):
        print(f"ПОМИЛКА: {repo} не є git-репозиторієм")
        sys.exit(2)

    status = run(['git', 'status', '--porcelain'], cwd=repo)
    if status.stdout.strip():
        print("ПОМИЛКА: робоче дерево не чисте")
        sys.exit(2)

    if os.path.exists(os.path.join(repo, '.git', 'rebase-merge')) or os.path.exists(os.path.join(repo, '.git', 'MERGE_HEAD')):
        print("ПОМИЛКА: репо в стані rebase/merge")
        sys.exit(2)

    initial_count = count_ai_signatures(repo)
    if initial_count == 0:
        print("нічого прибирати")
        sys.exit(0)

    initial_commits = count_commits(repo)
    print(f"Знайдено AI-слідів: {initial_count}")
    print(f"Комітів усього: {initial_commits}")

    if not args.yes:
        print("Буде створено бекап-гілку та переписано історію поточної гілки.")
        answer = input("Продовжити? (так/ні): ").strip().lower()
        if answer != 'так':
            print("Скасовано")
            sys.exit(0)

    backup_branch = create_backup_branch(repo, args.label)

    env = os.environ.copy()
    env['FILTER_BRANCH_SQUELCH_WARNING'] = '1'

    filter_script = (
        "import sys, re;"
        "patterns = [" + ','.join(f"r'{p}'" for p in AI_PATTERNS) + "];"
        "msg = sys.stdin.read();"
        "lines = msg.splitlines();"
        "filtered = [l for l in lines if not any(re.search(p, l) for p in patterns)];"
        "while filtered and filtered[-1] == '': filtered.pop();"
        "sys.stdout.write('\\n'.join(filtered) + ('\\n' if filtered else ''))"
    )

    result = run(
        ['git', 'filter-branch', '--msg-filter', f"python3 -c \"{filter_script}\"", 'HEAD'],
        cwd=repo,
        check=False
    )
    if result.returncode != 0:
        print("ПОМИЛКА: filter-branch завершилась з помилкою")
        print(result.stderr)
        sys.exit(1)

    final_count = count_ai_signatures(repo)
    final_commits = count_commits(repo)

    if final_count != 0:
        print(f"❌ лишилось {final_count} слідів — НЕ пушу")
        sys.exit(1)

    if final_commits != initial_commits:
        print(f"ПОМИЛКА: кількість комітів змінилась: було {initial_commits}, стало {final_commits}")
        sys.exit(1)

    print(f"✅ сліди прибрано: було {initial_count}, стало 0")

    push_status = "пропущено"
    if args.push:
        push_result = run(['git', 'push', '--force-with-lease'], cwd=repo, check=False)
        if push_result.returncode == 0:
            push_status = "виконано"
        else:
            push_status = "відхилено"
        print(f"Push вивід: {push_result.stdout}")
        print(f"Push код виходу: {push_result.returncode}")

    print(f"Репо:            {repo}")
    print(f"Комітів усього:  {final_commits} (було {initial_commits})")
    print(f"AI-слідів було:  {initial_count} → стало 0")
    print(f"Бекап-гілка:     {backup_branch}")
    print(f"Push:            {push_status}")
    print("OK" if push_status != "відхилено" else "ПОМИЛКА")

if __name__ == '__main__':
    main()
