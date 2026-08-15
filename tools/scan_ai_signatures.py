#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AI_PATTERNS = {
    'A': [
        re.compile(r'Co-Authored-By:.*(Claude|Anthropic|GPT|Copilot|Cursor|deepseek|gemini|noreply@anthropic\.com)', re.I),
    ],
    'B': [
        re.compile(r'Generated with Claude', re.I),
        re.compile(r'🤖 Generated', re.I),
        re.compile(r'Created by Claude', re.I),
        re.compile(r'written by AI', re.I),
        re.compile(r'AI-generated', re.I),
        re.compile(r'Claude Code', re.I),
    ],
    'C': [
        re.compile(r'(claude|anthropic|bot@|noreply@anthropic\.com)', re.I),
    ],
}


def run_git(repo_path, args):
    try:
        result = subprocess.run(
            ['git', '-C', repo_path] + args,
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return None


def find_git_repos(root, max_depth=3):
    repos = []
    root = Path(root).expanduser().resolve()
    if not root.exists():
        return repos

    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        
        # Filter out excluded directories
        dirnames[:] = [d for d in dirnames if d not in ('.git', 'node_modules', '__pycache__', '.venv', 'venv', '.next', 'dist', 'build')]
        
        # Check if this directory is a repo (has .git as dir or file)
        git_path = os.path.join(dirpath, '.git')
        if os.path.isdir(git_path) or os.path.isfile(git_path):
            repos.append(Path(dirpath))
            # Don't descend into this repo further
            dirnames[:] = []
            continue
        
        # Remove symlinks to avoid cycles
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
    
    return repos


def get_remote(repo_path):
    remote = run_git(repo_path, ['remote', 'get-url', 'origin'])
    if not remote:
        return None, None
    remote = remote.strip()
    if 'github.com' in remote:
        match = re.search(r'(?:github\.com[/:])([^/]+)/([^/]+?)(?:\.git)?$', remote)
        if match:
            return remote, f"{match.group(1)}/{match.group(2)}"
    return remote, None


def check_visibility(owner_name, cache, use_gh):
    """Check if repo is public using gh api. Returns 'public', 'private', or 'unknown'."""
    if not use_gh or not owner_name:
        return 'unknown'
    
    if owner_name in cache:
        return cache[owner_name]
    
    try:
        result = subprocess.run(
            ['gh', 'api', f'repos/{owner_name}', '--jq', '.private'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            is_private = result.stdout.strip().lower() == 'true'
            visibility = 'private' if is_private else 'public'
        else:
            visibility = 'unknown'
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        visibility = 'unknown'
    
    cache[owner_name] = visibility
    return visibility


def scan_repo(repo_path, limit_commits=0):
    problems = []
    log_args = ['log', '--all', '--format=%H|%h|%ad|%an|%ae|%cn|%ce|%s|%B', '--date=short']
    if limit_commits > 0:
        log_args.append(f'-{limit_commits}')

    output = run_git(repo_path, log_args)
    if output is None:
        return problems, 'git log failed'

    for entry in output.split('\n---\n'):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split('|', 8)
        if len(parts) < 9:
            continue
        full_hash, short_hash, date, author_name, author_email, committer_name, committer_email, subject, body = parts

        categories = set()
        evidence = []

        for cat, patterns in AI_PATTERNS.items():
            for pattern in patterns:
                if cat == 'C':
                    match = pattern.search(f"{author_name} {author_email} {committer_name} {committer_email}")
                else:
                    match = pattern.search(body)
                if match:
                    categories.add(cat)
                    evidence.append(match.group(0)[:100])

        if categories:
            problems.append({
                'hash': short_hash,
                'full_hash': full_hash,
                'date': date,
                'author': f"{author_name} <{author_email}>",
                'categories': ','.join(sorted(categories)),
                'evidence': evidence[0] if evidence else subject[:100],
                'subject': subject[:100]
            })

    return problems, None


def generate_report(report_data, repos_count, github_count, public_count, private_count, unknown_count, date_str):
    """Generate markdown report from collected data."""
    lines = []
    lines.append("# AI-сліди в git-історії — звіт")
    lines.append(f"Просканованo: {repos_count} репо · з GitHub-remote: {github_count} · публічних: {public_count} · приватних: {private_count} · невідомо: {unknown_count}")
    lines.append("")
    
    # Public repos with problems
    public_repos = [e for e in report_data if e.get('visibility') == 'public' and e['problems']]
    lines.append("## 🔴 Публічні репо (сліди видно стороннім)")
    lines.append("| репо | owner/name | комітів | категорії | приклад |")
    lines.append("|---|---|---|---|---|")
    for entry in public_repos:
        cats = set()
        for p in entry['problems']:
            cats.update(p['categories'].split(','))
        lines.append(f"| {entry['repo']} | {entry['owner_name']} | {len(entry['problems'])} | {','.join(sorted(cats))} | {entry['problems'][0]['evidence']} |")
    lines.append("")
    
    # Private repos
    private_repos = [e for e in report_data if e.get('visibility') == 'private' and e['problems']]
    lines.append("## Приватні репо")
    lines.append("| репо | owner/name | комітів | категорії | приклад |")
    lines.append("|---|---|---|---|---|")
    for entry in private_repos:
        cats = set()
        for p in entry['problems']:
            cats.update(p['categories'].split(','))
        lines.append(f"| {entry['repo']} | {entry['owner_name']} | {len(entry['problems'])} | {','.join(sorted(cats))} | {entry['problems'][0]['evidence']} |")
    lines.append("")
    
    # Unknown visibility repos
    unknown_repos = [e for e in report_data if e.get('visibility') == 'unknown' and e['problems']]
    lines.append("## ⚠️ Видимість невідома")
    lines.append("| репо | remote | комітів | категорії |")
    lines.append("|---|---|---|---|")
    for entry in unknown_repos:
        cats = set()
        for p in entry['problems']:
            cats.update(p['categories'].split(','))
        lines.append(f"| {entry['repo']} | {entry['remote']} | {len(entry['problems'])} | {','.join(sorted(cats))} |")
    lines.append("")
    
    # Details for each repo
    lines.append("## Деталі по кожному репо")
    for entry in report_data:
        if not entry['problems']:
            continue
        lines.append(f"### {entry['repo']}")
        lines.append("| хеш | дата | автор | кат. | доказ |")
        lines.append("|---|---|---|---|---|")
        for p in entry['problems']:
            lines.append(f"| {p['hash']} | {p['date']} | {p['author']} | {p['categories']} | {p['evidence']} |")
        lines.append("")
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default='~/Developer/Fayna-Workspace/Projects')
    parser.add_argument('--out', default='reports/AI_SIGNATURES.md')
    parser.add_argument('--date', default='')
    parser.add_argument('--limit-commits', type=int, default=0)
    parser.add_argument('--no-gh', action='store_true', help='Skip GitHub visibility check')
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    repos = find_git_repos(root)
    
    print(f"знайдено репозиторіїв: {len(repos)} (корінь: {root})")
    
    if len(repos) == 0:
        print("❌ не знайдено жодного репозиторію — перевір --root")
        return 2

    report_data = []
    public_with_problems = []
    private_with_problems = []
    unknown_with_problems = []
    total_problem_commits = 0
    total_problem_repos = 0
    github_count = 0
    public_count = 0
    private_count = 0
    unknown_count = 0
    visibility_cache = {}

    for repo in repos:
        remote, owner_name = get_remote(repo)
        if remote and owner_name:
            github_count += 1

        problems, error = scan_repo(repo, args.limit_commits)
        
        # Determine visibility
        visibility = check_visibility(owner_name, visibility_cache, not args.no_gh)
        if visibility == 'public':
            public_count += 1
        elif visibility == 'private':
            private_count += 1
        else:
            unknown_count += 1
        
        entry = {
            'repo': repo.name,
            'path': str(repo),
            'remote': remote or '—',
            'owner_name': owner_name or '—',
            'visibility': visibility,
            'problems': problems,
            'error': error
        }
        
        if error:
            report_data.append(entry)
            continue

        if problems:
            total_problem_commits += len(problems)
            total_problem_repos += 1
            report_data.append(entry)
            if visibility == 'public':
                public_with_problems.append(entry)
            elif visibility == 'private':
                private_with_problems.append(entry)
            else:
                unknown_with_problems.append(entry)

    print(f"Просканованo репо: {len(repos)} (з них з remote на github: {github_count})")
    print(f"Комітів із AI-слідами: {total_problem_commits} у {total_problem_repos} репо")
    print(f"🔴 Публічних репо з проблемою: {len(public_with_problems)}")
    print(f"Приватних репо з проблемою: {len(private_with_problems)}")
    print(f"Невідомих репо з проблемою: {len(unknown_with_problems)}")

    # Generate and write report
    report = generate_report(report_data, len(repos), github_count, public_count, private_count, unknown_count, args.date)
    
    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(report)
        
        # Verify write
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"звіт: {out_path} ({out_path.stat().st_size} байт)")
        else:
            print("❌ звіт не записано")
            return 3
    except Exception as e:
        print(f"❌ звіт не записано: {e}")
        return 3

    # Exit code logic
    if public_with_problems:
        print("ЗНАЙДЕНО ПРОБЛЕМИ")
        return 1
    elif private_with_problems or unknown_with_problems:
        print("ЗНАЙДЕНО ПРОБЛЕМИ")
        return 2
    else:
        print("OK")
        return 0


if __name__ == '__main__':
    sys.exit(main())
