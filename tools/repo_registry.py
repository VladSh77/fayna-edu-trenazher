#!/usr/bin/env python3
"""repo_registry.py — єдиний реєстр репозиторіїв VladSh77, fayna-digital і локальних клонів."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path(".registry_cache")
CACHE_DIR.mkdir(exist_ok=True)
API_PAUSE = 0.2

OWNER = "VladSh77"
ORG = "fayna-digital"
DEFAULT_ROOT = Path.home() / "Developer" / "Fayna-Workspace" / "Projects"
DEFAULT_OUT = Path("reports") / "REPO_REGISTRY.md"
DEFAULT_JSON_OUT = Path("reports") / "repo_registry.json"

CATEGORY_RULES = [
    ("camp", ["camp", "campscout", "kurs", "wychowawc", "vozhatyi", "instructor", "tabirnyi"]),
    ("odoo", ["odoo", "ksef", "l10n", "sendpulse", "zadarma", "meta-capi", "sms"]),
    ("ai", ["ai-", "rag", "agent", "brain", "voice", "kiosk", "sekretar", "inbox"]),
    ("iot", ["iot", "shopfloor", "dnj", "modbus"]),
    ("infra", ["core-configs", "security", "ci-", "docs-sorter", "dokumenty"]),
    ("edu", ["edu", "trenazher", "genius", "explorer"]),
    ("client", ["clients", "bonsens", "ovdrain", "aero", "celestix"]),
    ("personal", ["vladsh77", "devjournal", "home", "technical-resume", "dev-playground"]),
]

def g(d, *keys, default=None):
    """Безпечно дістає вкладене значення з dict."""
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current or current[key] is None:
            return default
        current = current[key]
    return current

def norm_topics(raw):
    """Нормалізує топіки до списку рядків."""
    if not raw:
        return []
    out = []
    for t in raw:
        if isinstance(t, str):
            out.append(t.lower())
        elif isinstance(t, dict):
            name = t.get("name")
            if not name and isinstance(t.get("topic"), dict):
                name = t["topic"].get("name")
            if name:
                out.append(str(name).lower())
    return out

def norm_language(raw):
    """Нормалізує мову до рядка або None."""
    if not raw:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return raw.get("name")
    return None

def run_cmd(cmd, check=True):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return ""

def gh_available():
    return run_cmd(["gh", "--version"], check=False) != ""

def gh_repos(owner):
    """Повертає список репозиторіїв власника з GitHub."""
    cache_file = CACHE_DIR / f"gh_{owner}.json"
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)
    cmd = [
        "gh", "repo", "list", owner, "--limit", "300",
        "--json", "name,isPrivate,description,pushedAt,primaryLanguage,repositoryTopics,stargazerCount,isArchived,isFork,diskUsage"
    ]
    try:
        out = run_cmd(cmd)
        data = json.loads(out)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        time.sleep(API_PAUSE)
        return data
    except Exception:
        return []

def local_repos(root):
    """Повертає список локальних клонів з інформацією."""
    repos = []
    if not root.exists():
        return repos
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__", ".venv")]
        if ".git" in dirnames:
            repo_path = Path(dirpath)
            git_dir = repo_path / ".git"
            if git_dir.is_dir():
                info = {}
                info["path"] = str(repo_path)
                info["remote"] = run_cmd(["git", "-C", str(repo_path), "remote", "get-url", "origin"], check=False)
                info["branch"] = run_cmd(["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"], check=False)
                info["commits"] = run_cmd(["git", "-C", str(repo_path), "rev-list", "HEAD", "--count"], check=False)
                info["last_commit"] = run_cmd(["git", "-C", str(repo_path), "log", "-1", "--format=%cI"], check=False)
                info["dirty"] = run_cmd(["git", "-C", str(repo_path), "status", "--porcelain"], check=False) != ""
                upstream = run_cmd(["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "@{u}"], check=False)
                if upstream:
                    unpushed = run_cmd(["git", "-C", str(repo_path), "rev-list", "@{u}..HEAD", "--count"], check=False)
                    info["unpushed"] = int(unpushed) if unpushed else 0
                else:
                    info["unpushed"] = None
                repos.append(info)
            dirnames.remove(".git")
    return repos

def parse_remote(remote_url):
    """Повертає (owner, name) з remote URL або None."""
    if not remote_url:
        return None
    remote_url = remote_url.replace("https://github.com/", "").replace("git@github.com:", "")
    remote_url = remote_url.replace(".git", "")
    parts = remote_url.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None

def categorize(name, topics):
    """Повертає категорію за назвою і топіками."""
    topics = topics or []
    name_lower = name.lower()
    for cat, keywords in CATEGORY_RULES:
        for kw in keywords:
            if kw in name_lower:
                return cat
    for topic in topics:
        topic_lower = topic.lower()
        for cat, keywords in CATEGORY_RULES:
            for kw in keywords:
                if kw in topic_lower:
                    return cat
    return "other"

def merge_data(gh_personal, gh_org, local):
    """Зводить дані з трьох джерел у єдиний реєстр."""
    registry = {}
    # GitHub дані
    for owner, repos in [(OWNER, gh_personal), (ORG, gh_org)]:
        for repo in repos:
            key = f"{owner}/{repo['name']}"
            registry[key] = {
                "name": repo["name"],
                "owner": owner,
                "is_private": repo.get("isPrivate"),
                "description": repo.get("description"),
                "pushed_at": repo.get("pushedAt"),
                "language": norm_language(repo.get("primaryLanguage")),
                "topics": norm_topics(repo.get("repositoryTopics")),
                "stars": repo.get("stargazerCount", 0),
                "is_archived": repo.get("isArchived", False),
                "is_fork": repo.get("isFork", False),
                "disk_usage": repo.get("diskUsage"),
                "local_path": None,
                "branch": None,
                "commits": None,
                "last_commit": None,
                "dirty": None,
                "unpushed": None,
                "source": f"github:{owner}",
            }
    # Локальні дані
    for repo in local:
        parsed = parse_remote(repo["remote"])
        if parsed:
            owner, name = parsed
            key = f"{owner}/{name}"
            if key in registry:
                registry[key]["local_path"] = repo["path"]
                registry[key]["branch"] = repo["branch"]
                registry[key]["commits"] = repo["commits"]
                registry[key]["last_commit"] = repo["last_commit"]
                registry[key]["dirty"] = repo["dirty"]
                registry[key]["unpushed"] = repo["unpushed"]
            else:
                # Локальний клон з remote, якого немає в GitHub списках
                registry[key] = {
                    "name": name,
                    "owner": owner,
                    "is_private": None,
                    "description": None,
                    "pushed_at": None,
                    "language": None,
                    "topics": [],
                    "stars": 0,
                    "is_archived": False,
                    "is_fork": False,
                    "disk_usage": None,
                    "local_path": repo["path"],
                    "branch": repo["branch"],
                    "commits": repo["commits"],
                    "last_commit": repo["last_commit"],
                    "dirty": repo["dirty"],
                    "unpushed": repo["unpushed"],
                    "source": "локально",
                }
        else:
            # Клон без remote
            key = f"local/{Path(repo['path']).name}"
            registry[key] = {
                "name": Path(repo["path"]).name,
                "owner": "local",
                "is_private": None,
                "description": None,
                "pushed_at": None,
                "language": None,
                "topics": [],
                "stars": 0,
                "is_archived": False,
                "is_fork": False,
                "disk_usage": None,
                "local_path": repo["path"],
                "branch": repo["branch"],
                "commits": repo["commits"],
                "last_commit": repo["last_commit"],
                "dirty": repo["dirty"],
                "unpushed": repo["unpushed"],
                "source": "локально",
            }
    return registry

def determine_state(entry):
    """Визначає стан репозиторію."""
    on_github = entry["source"].startswith("github:")
    has_local = entry["local_path"] is not None
    if on_github and has_local:
        if entry["unpushed"] and entry["unpushed"] > 0:
            return "НЕ ЗАПУШЕНО"
        return "СИНХРОН"
    if has_local and not on_github:
        return "ЛИШЕ ЛОКАЛЬНО"
    if on_github and not has_local:
        return "ЛИШЕ НА GITHUB"
    return "НЕВІДОМО"

def find_duplicates(registry):
    """Знаходить дублі між акаунтом і організацією."""
    names = {}
    for key, entry in registry.items():
        if entry["owner"] in (OWNER, ORG):
            name = entry["name"]
            if name not in names:
                names[name] = []
            names[name].append(entry["owner"])
    return {name: owners for name, owners in names.items() if len(owners) > 1}

def apply_topics(registry):
    """Проставляє topic категорії кожному репозиторію."""
    for key, entry in registry.items():
        if entry["owner"] in (OWNER, ORG):
            cat = categorize(entry["name"], entry["topics"])
            if cat == "other":
                continue
            repo_full = f"{entry['owner']}/{entry['name']}"
            # Читаємо поточні топіки
            cmd_get = ["gh", "api", f"repos/{repo_full}/topics", "--jq", ".names[]"]
            try:
                current = run_cmd(cmd_get).splitlines()
            except Exception:
                current = []
            if cat not in current:
                new_topics = current + [cat]
                topics_str = ",".join(new_topics)
                cmd_put = ["gh", "api", "-X", "PUT", f"repos/{repo_full}/topics", "-f", f"names={topics_str}"]
                try:
                    run_cmd(cmd_put)
                    time.sleep(API_PAUSE)
                except Exception:
                    pass

def generate_report(registry, out_path, json_out_path):
    """Генерує звіт Markdown і JSON."""
    # Спершу зберігаємо JSON
    json_data = []
    for key, entry in registry.items():
        item = dict(entry)
        item["key"] = key
        item["state"] = determine_state(entry)
        item["category"] = categorize(entry["name"], entry["topics"])
        json_data.append(item)
    json_out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    error_count = 0
    states = {}
    for key, entry in registry.items():
        states[key] = determine_state(entry)

    total = len(registry)
    gh_personal_count = sum(1 for e in registry.values() if e["owner"] == OWNER)
    gh_org_count = sum(1 for e in registry.values() if e["owner"] == ORG)
    local_count = sum(1 for e in registry.values() if e["local_path"] is not None)
    sync_count = sum(1 for s in states.values() if s == "СИНХРОН")
    unpushed_count = sum(1 for s in states.values() if s == "НЕ ЗАПУШЕНО")
    local_only_count = sum(1 for s in states.values() if s == "ЛИШЕ ЛОКАЛЬНО")
    github_only_count = sum(1 for s in states.values() if s == "ЛИШЕ НА GITHUB")
    duplicates = find_duplicates(registry)
    dup_count = len(duplicates)

    # Категорії
    categories = {}
    for key, entry in registry.items():
        cat = categorize(entry["name"], entry["topics"])
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((key, entry, states[key]))

    lines = []
    lines.append(f"Усього репозиторіїв: {total}")
    lines.append(f"На GitHub: особистих {gh_personal_count} · організації {gh_org_count}")
    lines.append(f"Локальних клонів: {local_count}")
    lines.append(f"СИНХРОН: {sync_count} · НЕ ЗАПУШЕНО: {unpushed_count} · ЛИШЕ ЛОКАЛЬНО: {local_only_count} · ЛИШЕ НА GITHUB: {github_only_count} · ДУБЛІВ: {dup_count}")
    lines.append("")

    for cat in sorted(categories.keys()):
        items = categories[cat]
        lines.append(f"### {cat} ({len(items)})")
        lines.append("| репо | де | приватне | локальний шлях | гілка | комітів | непушених | останній push | стан |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for key, entry, state in items:
            try:
                where = entry["source"]
                if entry["owner"] in (OWNER, ORG) and entry["local_path"]:
                    where = "обидва" if entry["name"] in duplicates else where
                private = "так" if entry["is_private"] else "ні" if entry["is_private"] is not None else "—"
                path = entry["local_path"] or "—"
                branch = entry["branch"] or "—"
                commits = entry["commits"] or "—"
                unpushed = entry["unpushed"] if entry["unpushed"] is not None else "—"
                pushed = entry["pushed_at"] or entry["last_commit"] or "—"
                lines.append(f"| {entry['name']} | {where} | {private} | {path} | {branch} | {commits} | {unpushed} | {pushed} | {state} |")
            except Exception as e:
                error_count += 1
                lines.append(f"| {key} | ПОМИЛКА РЯДКА: {e} |")
        lines.append("")

    # Секції
    lines.append("## 🔴 Не запушено")
    for key, entry in registry.items():
        try:
            if states[key] == "НЕ ЗАПУШЕНО":
                lines.append(f"- {key} — {entry['unpushed']} комітів")
        except Exception as e:
            error_count += 1
            lines.append(f"- {key} — ПОМИЛКА РЯДКА: {e}")
    lines.append("")

    lines.append("## ⚠️ Лише локально")
    for key, entry in registry.items():
        try:
            if states[key] == "ЛИШЕ ЛОКАЛЬНО":
                lines.append(f"- {key} — {entry['local_path']}")
        except Exception as e:
            error_count += 1
            lines.append(f"- {key} — ПОМИЛКА РЯДКА: {e}")
    lines.append("")

    lines.append("## Дублі між акаунтом і організацією")
    for name, owners in duplicates.items():
        lines.append(f"- {name}: {', '.join(owners)}")
    lines.append("")

    lines.append("## Архівні та форки")
    for key, entry in registry.items():
        try:
            if entry["is_archived"] or entry["is_fork"]:
                lines.append(f"- {key} — архів: {entry['is_archived']}, форк: {entry['is_fork']}")
        except Exception as e:
            error_count += 1
            lines.append(f"- {key} — ПОМИЛКА РЯДКА: {e}")

    lines.append("")
    lines.append(f"рядків з помилками: {error_count}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def main():
    parser = argparse.ArgumentParser(description="Реєстр репозиторіїв")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--apply-topics", action="store_true")
    args = parser.parse_args()

    if not gh_available():
        print("gh недоступний", file=sys.stderr)
        sys.exit(2)

    gh_personal = gh_repos(OWNER)
    gh_org = gh_repos(ORG)
    local = local_repos(args.root)

    registry = merge_data(gh_personal, gh_org, local)

    if args.apply_topics:
        apply_topics(registry)

    try:
        generate_report(registry, args.out, args.json_out)
    except Exception as e:
        print(f"⚠️ звіт не побудовано, але дані збережено у {args.json_out}")
        print(f"Помилка: {e}", file=sys.stderr)
        sys.exit(1)

    states = {key: determine_state(entry) for key, entry in registry.items()}
    has_unpushed = any(s == "НЕ ЗАПУШЕНО" for s in states.values())
    has_local_only = any(s == "ЛИШЕ ЛОКАЛЬНО" for s in states.values())
    if has_unpushed or has_local_only:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
