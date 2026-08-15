#!/usr/bin/env python3
import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

OWNERS = ['VladSh77', 'fayna-digital', 'faynaagency']

_HERE = os.path.dirname(os.path.abspath(__file__))
STRIP_SCRIPT = os.path.join(_HERE, "strip_ai_signatures.py")

def load_scanner():
    """Load scan_ai_signatures.py module."""
    scanner_path = os.path.join(_HERE, 'scan_ai_signatures.py')
    if not os.path.exists(scanner_path):
        print("❌ не знайдено scan_ai_signatures.py поруч")
        sys.exit(2)
    
    spec = importlib.util.spec_from_file_location("scan_ai", scanner_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        return None
    return result

def get_remote_owner(repo):
    result = run(['git', 'remote', 'get-url', 'origin'], cwd=repo, check=False)
    if result and result.returncode == 0:
        url = result.stdout.strip()
        match = re.search(r'(?:github\.com[:/])([^/]+)/([^/]+?)(?:\.git)?$', url)
        if match:
            return match.group(1), match.group(2)
    return None, None

def get_repo_visibility(owner, name):
    if not owner or not name:
        return 'невідомо'
    result = run(['gh', 'api', f'repos/{owner}/{name}', '--jq', '.private'], check=False)
    if result and result.returncode == 0:
        return 'приватний' if result.stdout.strip() == 'true' else 'публічний'
    return 'невідомо'

def check_clean_tree(repo):
    result = run(['git', 'status', '--porcelain'], cwd=repo)
    if result and result.stdout.strip():
        return False
    return True

def check_rebase_merge(repo):
    git_dir = os.path.join(repo, '.git')
    if os.path.exists(os.path.join(git_dir, 'rebase-merge')) or os.path.exists(os.path.join(git_dir, 'MERGE_HEAD')):
        return True
    return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='~/Developer/Fayna-Workspace/Projects')
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--yes', action='store_true')
    parser.add_argument('--only-public', action='store_true')
    parser.add_argument('--skip', default='')
    parser.add_argument('--owners', default=','.join(OWNERS))
    parser.add_argument('--out', default='reports/STRIP_ALL.md')
    args = parser.parse_args()

    if not os.path.isfile(STRIP_SCRIPT):
        print("не знайдено strip_ai_signatures.py поруч зі скриптом")
        sys.exit(2)

    owners = set(args.owners.split(','))
    skip_repos = set(args.skip.split(',')) if args.skip else set()
    root = os.path.expanduser(args.root)

    if not os.path.isdir(root):
        print(f"ПОМИЛКА: коренева тека не існує: {root}")
        sys.exit(2)

    # Load scanner and get repos
    scan_ai = load_scanner()
    repos = scan_ai.find_git_repos(root)
    
    total_repos = len(repos)
    repos_with_ai = 0
    print(f"репозиторіїв усього: {total_repos} · зі слідами: {repos_with_ai}")
    
    if total_repos == 0:
        print("❌ сканер повернув 0 репозиторіїв")
        sys.exit(2)

    results = []
    errors = []
    foreign_repos = []
    total_found = 0
    processed = 0
    skipped_foreign = 0
    skipped_dirty = 0
    pushed = 0
    error_count = 0

    for repo in repos:
        repo_path = str(repo)
        repo_name = repo.name
        if repo_name in skip_repos:
            continue

        # Count AI signatures using scanner's logic
        problems, error = scan_ai.scan_repo(repo_path)
        if error:
            continue
        ai_count = len(problems)
        if ai_count == 0:
            continue

        repos_with_ai += 1
        total_found += 1
        owner, name = get_remote_owner(repo_path)
        visibility = get_repo_visibility(owner, name)

        if owner and owner not in owners:
            skipped_foreign += 1
            foreign_repos.append((repo_name, owner, visibility, ai_count))
            print(f"ПРОПУСК (ЧУЖЕ): {repo_name} (owner: {owner})")
            continue

        if args.only_public and visibility == 'приватний':
            print(f"ПРОПУСК (приватний): {repo_name}")
            continue

        if not check_clean_tree(repo_path):
            skipped_dirty += 1
            results.append((repo_name, owner or 'локальний', visibility, ai_count, '—', '—', 'пропущено (брудне дерево)'))
            print(f"ПРОПУСК (брудне дерево): {repo_name}")
            continue

        if check_rebase_merge(repo_path):
            skipped_dirty += 1
            results.append((repo_name, owner or 'локальний', visibility, ai_count, '—', '—', 'пропущено (rebase/merge)'))
            print(f"ПРОПУСК (rebase/merge): {repo_name}")
            continue

        if not args.yes:
            print(f"Буде оброблено {total_found} репозиторіїв")
            answer = input("Продовжити? (так/ні): ").strip().lower()
            if answer != 'так':
                print("Скасовано")
                sys.exit(0)
            args.yes = True

        cmd = [sys.executable, STRIP_SCRIPT, '--repo', repo_path, '--yes']
        if args.push and owner:
            cmd.append('--push')

        result = run(cmd, check=False)
        if result and result.returncode == 0:
            processed += 1
            if args.push and owner:
                pushed += 1
            results.append((repo_name, owner or 'локальний', visibility, ai_count, 0, 'так' if args.push and owner else 'ні', 'успішно'))
            print(f"✅ {repo_name}: оброблено")
        else:
            error_count += 1
            error_msg = result.stderr[:300] if result and result.stderr else 'невідома помилка'
            errors.append((repo_name, error_msg))
            results.append((repo_name, owner or 'локальний', visibility, ai_count, '—', '—', 'помилка'))
            print(f"❌ {repo_name}: помилка")

    # Update the count after processing
    print(f"репозиторіїв усього: {total_repos} · зі слідами: {repos_with_ai}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(f"# Звіт про видалення AI-підписів\n\n")
        f.write(f"Репозиторіїв зі слідами:  {total_found}\n")
        f.write(f"Оброблено успішно:        {processed}\n")
        f.write(f"Пропущено (чуже):         {skipped_foreign}\n")
        f.write(f"Пропущено (брудне дерево):{skipped_dirty}\n")
        f.write(f"Помилок:                  {error_count}\n")
        f.write(f"Запушено:                 {pushed}\n\n")
        f.write("| репо | owner | видимість | слідів було | стало | push | статус |\n")
        f.write("|------|-------|-----------|-------------|-------|------|--------|\n")
        for r in results:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |\n")
        
        if errors:
            f.write("\n## Помилки\n\n")
            for repo_name, err in errors:
                f.write(f"### {repo_name}\n```\n{err}\n```\n")
        
        if foreign_repos:
            f.write("\n## Пропущені чужі репо\n\n")
            for repo_name, owner, visibility, count in foreign_repos:
                f.write(f"- {repo_name} (owner: {owner}, видимість: {visibility}, слідів: {count})\n")

    print(f"\nЗвіт збережено: {args.out}")
    if error_count > 0:
        sys.exit(1)
    elif total_found == 0:
        sys.exit(2)
    else:
        sys.exit(0)

if __name__ == '__main__':
    main()
