#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AI_RE = re.compile(
    r"co-authored-by.*(claude|anthropic|gpt|copilot|cursor)|generated with .*(claude|ai)|🤖 generated",
    re.IGNORECASE,
)

CACHE_DIR = Path(".pub_cache")


def run_gh(args, cache=True):
    cache_key = "_".join(args).replace("/", "_").replace(":", "_")
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache and cache_file.exists():
        with open(cache_file) as f:
            return json.load(f)
    try:
        result = subprocess.run(
            ["gh"] + args, capture_output=True, text=True, check=True
        )
        data = json.loads(result.stdout)
        if cache:
            CACHE_DIR.mkdir(exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(data, f)
        return data
    except subprocess.CalledProcessError as e:
        print(f"gh error: {e.stderr}", file=sys.stderr)
        return None


def get_commits(owner, repo, no_cache):
    commits = []
    page = 1
    incomplete = False
    while page <= 10:
        data = run_gh(
            ["api", f"repos/{owner}/{repo}/commits?per_page=100&page={page}"],
            cache=not no_cache,
        )
        if data is None:
            return None, True
        if not isinstance(data, list):
            return None, True
        commits.extend(data)
        if len(data) < 100:
            break
        page += 1
    else:
        incomplete = True
    return commits, incomplete


def get_unreachable(owner, repo, local_root, no_cache):
    repo_dir = Path(local_root) / repo
    if not repo_dir.exists():
        return []
    try:
        all_hashes = set(
            subprocess.check_output(
                ["git", "-C", str(repo_dir), "rev-list", "--all"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).split()
        )
        reflog = subprocess.check_output(
            ["git", "-C", str(repo_dir), "reflog", "--format=%H"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).split()
        all_hashes.update(reflog)
        reachable = set(
            subprocess.check_output(
                ["git", "-C", str(repo_dir), "rev-list", "--remotes"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).split()
        )
        unreachable = all_hashes - reachable
        dirty = []
        for sha in unreachable:
            data = run_gh(
                ["api", f"repos/{owner}/{repo}/commits/{sha}"],
                cache=not no_cache,
            )
            if data and isinstance(data, dict):
                msg = data.get("commit", {}).get("message", "")
                if AI_RE.search(msg):
                    dirty.append((sha, msg.strip()))
            time.sleep(0.2)
        return dirty
    except subprocess.CalledProcessError:
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default="VladSh77")
    parser.add_argument("--local-root", default=os.path.expanduser("~/Developer/Fayna-Workspace/Projects"))
    parser.add_argument("--out", default="reports/PUBLIC_REPOS.md")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit(2)

    owners = [o.strip() for o in args.owner.split(",") if o.strip()]
    repos = []
    for owner in owners:
        data = run_gh(
            ["repo", "list", owner, "--limit", "200", "--json", "name,isPrivate,description,stargazerCount,forkCount"],
            cache=not args.no_cache,
        )
        if data:
            repos.extend(data)
        time.sleep(0.2)

    public_repos = [r for r in repos if not r["isPrivate"]]
    total = len(public_repos)
    dirty_count = 0
    unreachable_count = 0
    clean_count = 0
    rows = []
    evidence = []

    for repo in public_repos:
        name = repo["name"]
        owner = next(o for o in owners if any(r["name"] == name for r in repos if not r["isPrivate"]))
        commits, incomplete = get_commits(owner, name, args.no_cache)
        if commits is None:
            rows.append((name, repo["stargazerCount"], repo["forkCount"], "?", "?", "?", "? помилка"))
            continue
        dirty = []
        for c in commits:
            msg = c.get("commit", {}).get("message", "")
            if AI_RE.search(msg):
                dirty.append((c.get("sha", ""), msg.strip()))
        unreachable = get_unreachable(owner, name, args.local_root, args.no_cache)
        status = "✅ ЧИСТЕ"
        if dirty:
            dirty_count += 1
            status = "🔴 БРУДНЕ"
        if unreachable:
            unreachable_count += 1
            status = "⚠️ НЕДОСЯЖНІ"
        if incomplete:
            status += " ? неповний прохід"
        if not dirty and not unreachable:
            clean_count += 1
        rows.append((name, repo["stargazerCount"], repo["forkCount"], len(commits), len(dirty), len(unreachable), status))
        if dirty or unreachable:
            evidence.append((name, dirty, unreachable))
        time.sleep(0.2)

    print(f"Публічних репозиторіїв: {total}")
    print(f"Зі слідами в історії:   {dirty_count}")
    print(f"З недосяжними брудними: {unreachable_count}")
    print(f"Чистих:                 {clean_count}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("| репо | зірки | форки | комітів перевірено | слідів у гілках | недосяжних брудних | статус |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for row in rows:
            f.write("| " + " | ".join(str(x) for x in row) + " |\n")
        if evidence:
            f.write("\n## Докази\n")
            for name, dirty, unreachable in evidence:
                f.write(f"\n### {name}\n")
                for sha, msg in dirty:
                    f.write(f"- `{sha}`: {msg}\n")
                for sha, msg in unreachable:
                    f.write(f"- (недосяжний) `{sha}`: {msg}\n")

    if dirty_count or unreachable_count:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
