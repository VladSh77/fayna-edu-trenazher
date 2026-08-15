#!/usr/bin/env python3
"""feed_stars.py — collect GitHub links from vault, verify, classify, optionally star/watch."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_RE = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9._-]{0,38})/([A-Za-z0-9][A-Za-z0-9._-]{0,38})")
OWNER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,38}$")
REPO_SUFFIXES = (".pdf", ".png", ".jpg", ".zip", ".md", ".html")
PATH_SEGMENTS = {"blob", "tree", "raw", "releases", "issues", "pull", "commit", "wiki", "actions"}
OWN_OWNERS = {"VladSh77", "fayna-digital", "faynaagency"}
CACHE_DIR = Path(".stars_cache")
CACHE_DIR.mkdir(exist_ok=True)


def run_gh(args, timeout=30):
    """Run gh CLI, return (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except FileNotFoundError:
        print("Помилка: gh CLI не знайдено", file=sys.stderr)
        sys.exit(1)


def gh_api(path, method="GET", data=None, retries=3):
    """Call gh api with caching for GET, retries on 403."""
    cache_file = CACHE_DIR / (path.replace("/", "_") + ".json")
    if method == "GET" and cache_file.exists():
        try:
            return json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            pass

    args = ["api", path, "-H", "Accept: application/vnd.github+json"]
    if method != "GET":
        args = ["api", "-X", method, path]
        if data:
            for k, v in data.items():
                args += ["-f", f"{k}={v}"]

    for attempt in range(retries):
        rc, out, err = run_gh(args)
        if rc == 0:
            if method == "GET":
                cache_file.write_text(out)
            return json.loads(out)
        if rc == 1 and "404" in err:
            return {"status": 404}
        if rc == 1 and "403" in err:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return {"status": 403, "error": err}
        if rc == 1 and "204" in out:
            return {"status": 204}
        if attempt < retries - 1:
            time.sleep(0.5)
    return {"status": "error", "error": err}


def collect_candidates(root):
    """Walk root, extract candidate repos from text files."""
    candidates = defaultdict(lambda: {"count": 0, "files": []})
    files = []
    for ext in (".md", ".txt", ".json", ".py"):
        files.extend(root.rglob(f"*{ext}"))

    for filepath in files:
        try:
            text = filepath.read_text(errors="ignore")
        except OSError:
            continue
        for match in REPO_RE.finditer(text):
            owner, repo = match.group(1), match.group(2)
            if not OWNER_RE.match(owner) or not OWNER_RE.match(repo):
                continue
            if repo.endswith(REPO_SUFFIXES):
                continue
            if repo.endswith(".git"):
                repo = repo[:-4]
            if owner.lower() in {o.lower() for o in OWN_OWNERS}:
                continue
            # Check path segments
            full = match.group(0)
            after_domain = full.split("github.com/", 1)[1]
            segments = after_domain.split("/")
            if len(segments) > 2 and segments[1].lower() in PATH_SEGMENTS:
                continue
            key = f"{owner.lower()}/{repo.lower()}"
            entry = candidates[key]
            entry["count"] += 1
            if len(entry["files"]) < 3:
                entry["files"].append(str(filepath))
            entry["owner"] = owner
            entry["repo"] = repo
    return candidates


def check_repo(owner, repo):
    """Check repo existence via gh api, return dict with metadata."""
    data = gh_api(f"repos/{owner}/{repo}")
    if data.get("status") == 404:
        return {"status": "НЕ ІСНУЄ"}
    if data.get("status") == 403:
        return {"status": "ПОМИЛКА API", "error": data.get("error")}
    if data.get("status") == "error":
        return {"status": "ПОМИЛКА API", "error": data.get("error")}
    return {
        "status": "Є",
        "full_name": data.get("full_name", f"{owner}/{repo}"),
        "description": data.get("description", ""),
        "stargazers_count": data.get("stargazers_count", 0),
        "language": data.get("language", ""),
        "archived": data.get("archived", False),
        "pushed_at": data.get("pushed_at", ""),
        "fork": data.get("fork", False),
        "private": data.get("private", False),
    }


def classify(repo_info, now_str):
    """Classify repo status."""
    if repo_info.get("status") != "Є":
        return repo_info.get("status", "?")
    if repo_info.get("archived"):
        return "АРХІВ"
    if repo_info.get("fork"):
        return "ФОРК"
    if now_str:
        try:
            pushed = datetime.fromisoformat(repo_info.get("pushed_at", "").replace("Z", "+00:00"))
            now = datetime.fromisoformat(now_str + "T00:00:00+00:00")
            if (now - pushed).days > 730:
                return "ЗАКИНУТИЙ"
        except (ValueError, TypeError):
            pass
    return "ЖИВИЙ"


def is_starred(owner, repo):
    """Check if already starred."""
    data = gh_api(f"user/starred/{owner}/{repo}")
    return data.get("status") == 204


def main():
    parser = argparse.ArgumentParser(description="Collect GitHub links from vault and manage stars")
    parser.add_argument("--root", default=str(Path.home() / "Developer/Fayna-Workspace/Projects/DevJournal"))
    parser.add_argument("--now", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--star", action="store_true", help="Star repos")
    parser.add_argument("--watch", action="store_true", help="Watch repos")
    parser.add_argument("--only-alive", action="store_true")
    parser.add_argument("--min-stars", type=int, default=0)
    parser.add_argument("--exclude-forks", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", help="Comma-separated owner/repo list")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument("--out", default="reports/FEED_STARS.md")
    args = parser.parse_args()

    root = Path(args.root).expanduser()
    if not root.exists():
        print(f"Помилка: root {root} не існує", file=sys.stderr)
        sys.exit(2)

    candidates = collect_candidates(root)
    if not candidates:
        print("Кандидатів не знайдено", file=sys.stderr)
        sys.exit(2)

    # Filter by --only
    if args.only:
        only_set = {x.strip().lower() for x in args.only.split(",")}
        candidates = {k: v for k, v in candidates.items() if k in only_set}

    total_mentions = sum(v["count"] for v in candidates.values())
    unique_count = len(candidates)

    # Check existence
    repos = {}
    api_errors = 0
    for key, cand in candidates.items():
        info = check_repo(cand["owner"], cand["repo"])
        if info.get("status") == "ПОМИЛКА API":
            api_errors += 1
        info["candidate"] = cand
        repos[key] = info
        time.sleep(0.3)

    # Classify
    for key, info in repos.items():
        if info.get("status") == "Є":
            info["class"] = classify(info, args.now)
        else:
            info["class"] = info.get("status", "?")

    # Apply filters
    filtered = {}
    for key, info in repos.items():
        if info.get("status") != "Є":
            filtered[key] = info
            continue
        if args.only_alive and info["class"] != "ЖИВИЙ":
            continue
        if info.get("stargazers_count", 0) < args.min_stars:
            continue
        if args.exclude_forks and info.get("fork"):
            continue
        filtered[key] = info

    # Sort by stars desc
    sorted_repos = sorted(
        filtered.items(),
        key=lambda x: x[1].get("stargazers_count", 0),
        reverse=True,
    )
    if args.limit > 0:
        sorted_repos = sorted_repos[: args.limit]

    # Count stats
    alive = sum(1 for _, i in sorted_repos if i.get("class") == "ЖИВИЙ")
    archived = sum(1 for _, i in sorted_repos if i.get("class") == "АРХІВ")
    abandoned = sum(1 for _, i in sorted_repos if i.get("class") == "ЗАКИНУТИЙ")
    forks = sum(1 for _, i in sorted_repos if i.get("class") == "ФОРК")
    not_exist = sum(1 for _, i in sorted_repos if i.get("class") == "НЕ ІСНУЄ")

    # Actions
    already_starred = 0
    starred_now = 0
    watched_now = 0

    if args.star or args.watch:
        action_repos = [r for r in sorted_repos if r[1].get("status") == "Є"]
        if action_repos and not args.yes:
            print(f"Буде оброблено {len(action_repos)} репозиторіїв. Введіть число для підтвердження:")
            try:
                confirm = int(input().strip())
            except (EOFError, ValueError):
                print("Скасовано", file=sys.stderr)
                sys.exit(1)
            if confirm != len(action_repos):
                print("Число не збігається, скасовано", file=sys.stderr)
                sys.exit(1)

        for key, info in action_repos:
            owner, repo = key.split("/", 1)
            if args.star:
                if is_starred(owner, repo):
                    already_starred += 1
                else:
                    rc, out, err = run_gh(["api", "-X", "PUT", f"user/starred/{owner}/{repo}"])
                    if rc == 0:
                        starred_now += 1
                    else:
                        api_errors += 1
                    time.sleep(0.3)
            if args.watch:
                rc, out, err = run_gh(
                    ["api", "-X", "PUT", f"repos/{owner}/{repo}/subscription", "-f", "subscribed=true"]
                )
                if rc == 0:
                    watched_now += 1
                else:
                    api_errors += 1
                time.sleep(0.3)

    # Build report
    report_lines = []
    report_lines.append(f"Знайдено згадок:      {total_mentions}")
    report_lines.append(f"Унікальних кандидатів: {unique_count}")
    report_lines.append(f"Відкинуто як сміття:  {total_mentions - unique_count}")
    report_lines.append(f"Живих репозиторіїв:   {alive} · архівних: {archived} · закинутих: {abandoned} · форків: {forks} · не існує: {not_exist}")
    report_lines.append(f"Уже зірковано:        {already_starred}")
    report_lines.append(f"Поставлено зірок:     {starred_now}")
    if args.watch:
        report_lines.append(f"Додано стежень:       {watched_now} (стеження дає більше подій у стрічці, ніж зірка)")
    report_lines.append("")
    report_lines.append("| репо | зірок | мова | останній push | статус | згадок у базі | де згадано |")
    report_lines.append("|------|-------|------|---------------|--------|---------------|------------|")
    for key, info in sorted_repos:
        cand = info.get("candidate", {})
        pushed = info.get("pushed_at", "")[:10] if info.get("pushed_at") else ""
        files = ", ".join(cand.get("files", []))
        report_lines.append(
            f"| {key} | {info.get('stargazers_count', 0)} | {info.get('language', '')} | {pushed} | {info.get('class', '?')} | {cand.get('count', 0)} | {files} |"
        )

    # Sections
    not_exist_repos = [r for r in sorted_repos if r[1].get("class") == "НЕ ІСНУЄ"]
    if not_exist_repos:
        report_lines.append("")
        report_lines.append("## Не існує (посилання застаріли)")
        for key, info in not_exist_repos:
            report_lines.append(f"- {key}")

    old_repos = [r for r in sorted_repos if r[1].get("class") in ("АРХІВ", "ЗАКИНУТИЙ")]
    if old_repos:
        report_lines.append("")
        report_lines.append("## Архівні та закинуті")
        for key, info in old_repos:
            report_lines.append(f"- {key} ({info.get('class')})")

    report = "\n".join(report_lines) + "\n"

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(report)

    if api_errors > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
