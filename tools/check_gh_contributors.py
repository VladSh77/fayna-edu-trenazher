#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AI_PATTERNS = [
    re.compile(r'claude', re.I),
    re.compile(r'anthropic', re.I),
    re.compile(r'copilot', re.I),
    re.compile(r'gpt', re.I),
    re.compile(r'cursor', re.I),
]
AI_CONTRIBUTOR_LOGINS = {'claude', 'claude-bot', 'github-actions[bot]', 'copilot'}
AI_TRAILER_RE = re.compile(r'co-authored-by:.*(claude|anthropic|gpt|copilot|cursor)', re.I)

CACHE_DIR = Path('.gh_cache')
DEFAULT_OWNER = 'VladSh77'
DEFAULT_LOCAL_ROOT = Path.home() / 'Developer' / 'Fayna-Workspace' / 'Projects'
DEFAULT_OUT = Path('reports') / 'GH_CONTRIBUTORS.md'
REQUEST_DELAY = 0.2


def run_gh(args, cache_key=None, use_cache=True):
    if use_cache and cache_key:
        cache_file = CACHE_DIR / f'{cache_key}.json'
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    try:
        result = subprocess.run(
            ['gh'] + args,
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout.strip():
            return []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f'Помилка JSON для {args}: {e}', file=sys.stderr)
            print(f'Відповідь: {result.stdout[:200]}', file=sys.stderr)
            return []
    except subprocess.CalledProcessError as e:
        if e.returncode == 2 and 'gh' not in str(e):
            raise
        return []
    except FileNotFoundError:
        print('gh CLI недоступний', file=sys.stderr)
        sys.exit(2)
    if use_cache and cache_key:
        CACHE_DIR.mkdir(exist_ok=True)
        with open(CACHE_DIR / f'{cache_key}.json', 'w', encoding='utf-8') as f:
            json.dump(data, f)
    time.sleep(REQUEST_DELAY)
    return data


def get_repos(owner, use_cache):
    repos = []
    for o in owner.split(','):
        o = o.strip()
        if not o:
            continue
        data = run_gh(
            ['repo', 'list', o, '--limit', '200', '--json', 'name,isPrivate,pushedAt'],
            cache_key=f'repos_{o}',
            use_cache=use_cache,
        )
        if not data:
            print(f'Не вдалося отримати репозиторії для {o}', file=sys.stderr)
            continue
        for repo in data:
            repos.append({
                'owner': o,
                'name': repo['name'],
                'isPrivate': repo['isPrivate'],
                'pushedAt': repo['pushedAt'],
            })
    return repos


def get_contributors(owner, name, use_cache):
    data = run_gh(
        ['api', f'repos/{owner}/{name}/contributors'],
        cache_key=f'contributors_{owner}_{name}',
        use_cache=use_cache,
    )
    if not data:
        return []
    return [c['login'] for c in data]


def get_remote_commits(owner, name, use_cache):
    data = run_gh(
        ['api', f'repos/{owner}/{name}/commits?per_page=100'],
        cache_key=f'commits_{owner}_{name}',
        use_cache=use_cache,
    )
    if not data:
        return [], 0
    return [c['commit']['message'] for c in data], len(data)


def count_local_traces(repo_path):
    if not repo_path.exists():
        return None
    try:
        result = subprocess.run(
            ['git', '-C', str(repo_path), 'log', '--format=%B'],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return sum(1 for line in result.stdout.splitlines() if AI_TRAILER_RE.search(line))


def analyze_repo(repo, local_root, use_cache):
    owner, name = repo['owner'], repo['name']
    contributors = get_contributors(owner, name, use_cache)
    ai_contributors = [c for c in contributors if c in AI_CONTRIBUTOR_LOGINS or AI_PATTERNS[0].search(c) or AI_PATTERNS[1].search(c)]

    remote_messages, remote_count = get_remote_commits(owner, name, use_cache)
    remote_traces = sum(1 for msg in remote_messages if AI_TRAILER_RE.search(msg))
    remote_truncated = remote_count >= 100

    local_path = local_root / name
    local_traces = count_local_traces(local_path)

    if local_traces is None:
        conclusion = 'НЕМАЄ КЛОНУ'
    elif local_traces == 0 and remote_traces > 0:
        conclusion = 'ТРЕБА PUSH'
    elif local_traces > 0 and remote_traces > 0:
        conclusion = 'ТРЕБА ЧИСТИТИ'
    else:
        conclusion = 'ЧИСТО'

    return {
        'repo': f'{owner}/{name}',
        'isPrivate': repo['isPrivate'],
        'ai_contributors': ', '.join(ai_contributors) if ai_contributors else '-',
        'remote_traces': remote_traces,
        'remote_truncated': remote_truncated,
        'local_traces': local_traces if local_traces is not None else 'немає клону',
        'conclusion': conclusion,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--owner', default=DEFAULT_OWNER)
    parser.add_argument('--local-root', default=str(DEFAULT_LOCAL_ROOT))
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--no-cache', action='store_true')
    args = parser.parse_args()

    use_cache = not args.no_cache
    local_root = Path(args.local_root)

    repos = get_repos(args.owner, use_cache)
    print(f'Репозиторіїв у власника: {len(repos)}')

    results = []
    for repo in repos:
        results.append(analyze_repo(repo, local_root, use_cache))

    ai_repos = [r for r in results if r['ai_contributors'] != '-']
    clean_local = [r for r in ai_repos if r['conclusion'] == 'ТРЕБА PUSH']

    print(f'З AI серед контриб\'юторів: {len(ai_repos)}')
    print(f'З них уже чисті локально (треба лише push): {len(clean_local)}')

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('| репо | приватне | AI-контриб\'ютори | слідів на GitHub | слідів локально | висновок |\n')
        f.write('|---|---|---|---|---|---|\n')
        for r in results:
            if r['ai_contributors'] == '-':
                continue
            remote = str(r['remote_traces'])
            if r['remote_truncated']:
                remote += '*'
            f.write(f"| {r['repo']} | {'так' if r['isPrivate'] else 'ні'} | {r['ai_contributors']} | {remote} | {r['local_traces']} | {r['conclusion']} |\n")

    if any(r['conclusion'] in ('ТРЕБА PUSH', 'ТРЕБА ЧИСТИТИ') for r in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
