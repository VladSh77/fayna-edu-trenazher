#!/usr/bin/env python3
"""chystka.py — радикальне видалення й перестворення репозиторіїв GitHub."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROTECTED = ["DevJournal", "fayna-core-configs"]
OWNERS = ["VladSh77", "fayna-digital", "faynaagency"]
AI_RE = re.compile(r"co-authored-by.*(claude|anthropic|gpt|copilot|cursor)", re.I)
BACKUP_DIR = Path(".chystka_backup")
REPORT_DIR = Path("reports")


def run(cmd, check=True, capture=True):
    """Виконати команду, повернути (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd, capture_output=capture, text=True, check=False
        )
        if check and proc.returncode != 0:
            raise RuntimeError(f"Команда {' '.join(cmd)} завершилась з кодом {proc.returncode}: {proc.stderr}")
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        raise RuntimeError(f"Команда {cmd[0]} не знайдена")


def gh_api(path, method="GET", data=None, allow_missing=True):
    """Виклик gh api, повертає JSON або None при 404/422."""
    cmd = ["gh", "api", path, "--method", method]
    if data is not None:
        cmd += ["--input", "-"]
    proc = subprocess.run(cmd, input=json.dumps(data) if data is not None else None,
                          capture_output=True, text=True)
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    if allow_missing and (proc.returncode == 404 or 
                          "HTTP 404" in proc.stderr or 
                          "HTTP 422" in proc.stderr or 
                          "No commit found" in proc.stderr):
        return None
    raise RuntimeError(f"gh api {path} failed: {proc.stderr}")


def check_gh():
    """Перевірка наявності gh."""
    try:
        run(["gh", "--version"], check=False)
    except RuntimeError:
        return False
    return True


def get_repos(owner):
    """Список репозиторіїв власника."""
    repos = gh_api(f"users/{owner}/repos?per_page=100")
    return [r["name"] for r in repos] if repos else []


def get_repo_meta(owner, name):
    """Метадані репозиторію."""
    return gh_api(f"repos/{owner}/{name}")


def count_issues(owner, name):
    """Кількість issues+PR."""
    issues = gh_api(f"repos/{owner}/{name}/issues?state=all&per_page=100")
    return len(issues) if issues else 0


def count_releases(owner, name):
    releases = gh_api(f"repos/{owner}/{name}/releases")
    return len(releases) if releases else 0


def count_branches(owner, name):
    branches = gh_api(f"repos/{owner}/{name}/branches")
    return len(branches) if branches else 0


def count_tags(owner, name):
    tags = gh_api(f"repos/{owner}/{name}/tags")
    return len(tags) if tags else 0


def get_local_commits(repo_path):
    """Усі локальні хеші (rev-list --all + reflog)."""
    hashes = set()
    for cmd in [
        ["git", "-C", repo_path, "rev-list", "--all"],
        ["git", "-C", repo_path, "reflog", "--all"],
    ]:
        rc, out, _ = run(cmd, check=False)
        if rc == 0:
            hashes.update(out.split())
    return hashes


def get_remote_branches(owner, name):
    """Хеші комітів віддалених гілок."""
    branches = gh_api(f"repos/{owner}/{name}/branches")
    return {b["commit"]["sha"] for b in branches} if branches else set()


def find_dirty_commits(owner, name, repo_path):
    """Пошук недосяжних комітів з AI-слідами."""
    if not repo_path or not Path(repo_path).exists():
        return [], 0
    local = get_local_commits(repo_path)
    remote = get_remote_branches(owner, name)
    unreachable = local - remote
    dirty = []
    local_only = 0
    for sha in unreachable:
        commit = gh_api(f"repos/{owner}/{name}/commits/{sha}")
        if commit is None:
            local_only += 1
            continue
        if AI_RE.search(commit.get("commit", {}).get("message", "")):
            dirty.append((sha, commit["commit"]["message"].splitlines()[0]))
    return dirty, local_only


def classify(meta, issues, releases, branches, tags, dirty, has_clone):
    """Класифікація репозиторію."""
    if meta.get("archived"):
        return "РИЗИК"
    if not has_clone:
        return "НЕМАЄ КЛОНУ"
    if dirty:
        if (meta.get("stargazers_count", 0) == 0 and
            meta.get("forks_count", 0) == 0 and
            issues == 0 and releases == 0):
            return "БЕЗПЕЧНО"
        return "РИЗИК"
    return "ЧИСТЕ"


def build_plan(owners, only=None):
    """Фаза 1: інвентаризація."""
    plan = []
    error_count = 0
    for owner in owners:
        for name in get_repos(owner):
            if only and name not in only:
                continue
            if name in PROTECTED:
                plan.append({
                    "owner": owner, "name": name, "class": "ЗАХИЩЕНО",
                    "meta": {}, "issues": 0, "releases": 0,
                    "branches": 0, "tags": 0, "dirty": [], "has_clone": False,
                    "local_only": 0
                })
                continue
            try:
                meta = get_repo_meta(owner, name)
                issues = count_issues(owner, name)
                releases = count_releases(owner, name)
                branches = count_branches(owner, name)
                tags = count_tags(owner, name)
                repo_path = Path(f"../{name}") if Path(f"../{name}").exists() else None
                has_clone = repo_path is not None
                dirty, local_only = find_dirty_commits(owner, name, repo_path) if has_clone else ([], 0)
                cls = classify(meta, issues, releases, branches, tags, dirty, has_clone)
                plan.append({
                    "owner": owner, "name": name, "class": cls,
                    "meta": meta, "issues": issues, "releases": releases,
                    "branches": branches, "tags": tags, "dirty": dirty,
                    "has_clone": has_clone, "local_only": local_only
                })
            except Exception as e:
                error_count += 1
                plan.append({
                    "owner": owner, "name": name, "class": "ПОМИЛКА ІНВЕНТАРИЗАЦІЇ",
                    "meta": {}, "issues": 0, "releases": 0,
                    "branches": 0, "tags": 0, "dirty": [], "has_clone": False,
                    "local_only": 0, "error": str(e)
                })
    return plan, error_count


def write_report(plan, out_path):
    """Запис звіту."""
    REPORT_DIR.mkdir(exist_ok=True)
    lines = ["# CHYSTKA_PLAN\n"]
    lines.append("| репо | приватне | зірки | форки | issues+PR | релізи | гілок | брудних комітів | лише локально | клас |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for p in plan:
        m = p["meta"]
        lines.append(
            f"| {p['owner']}/{p['name']} | {m.get('private', '?')} | "
            f"{m.get('stargazers_count', 0)} | {m.get('forks_count', 0)} | "
            f"{p['issues']} | {p['releases']} | {p['branches']} | "
            f"{len(p['dirty'])} | {p.get('local_only', 0)} | {p['class']} |"
        )
    lines.append("\n## 🔴 ЩО БУДЕ ВТРАЧЕНО\n")
    for p in plan:
        if p["class"] == "РИЗИК":
            m = p["meta"]
            lines.append(f"- **{p['owner']}/{p['name']}**: "
                         f"{m.get('stargazers_count', 0)} зірок, "
                         f"{m.get('forks_count', 0)} форків, "
                         f"{p['issues']} issues+PR, {p['releases']} релізів")
    lines.append("\n## Готові до чистки (БЕЗПЕЧНО)\n")
    for p in plan:
        if p["class"] == "БЕЗПЕЧНО":
            lines.append(f"- {p['owner']}/{p['name']}")
    lines.append("\n## ЗАХИЩЕНО\n")
    for p in plan:
        if p["class"] == "ЗАХИЩЕНО":
            lines.append(f"- {p['owner']}/{p['name']}")
    lines.append("\n## ПОМИЛКИ ІНВЕНТАРИЗАЦІЇ\n")
    for p in plan:
        if p["class"] == "ПОМИЛКА ІНВЕНТАРИЗАЦІЇ":
            lines.append(f"- {p['owner']}/{p['name']}: {p.get('error', 'невідома помилка')}")
    Path(out_path).write_text("\n".join(lines) + "\n")


def backup_repo(p):
    """Дзеркальний бекап."""
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"{p['name']}.git"
    if target.exists():
        return True
    rc, _, _ = run(["git", "clone", "--mirror", p["meta"]["clone_url"], str(target)], check=False)
    return rc == 0


def save_meta(p):
    """Збереження метаданих."""
    BACKUP_DIR.mkdir(exist_ok=True)
    path = BACKUP_DIR / f"{p['name']}.json"
    path.write_text(json.dumps(p, indent=2, default=str))


def verify_clean_local(p):
    """Перевірка локального клону."""
    repo_path = Path(f"../{p['name']}")
    if not repo_path.exists():
        return False
    rc, out, _ = run(["git", "-C", str(repo_path), "status", "--porcelain"], check=False)
    if rc != 0 or out.strip():
        return False
    rc, out, _ = run(["git", "-C", str(repo_path), "log", "--all", "--format=%B"], check=False)
    if rc != 0:
        return False
    return not AI_RE.search(out)


def execute_phase(plan, args):
    """Фаза 2: виконання."""
    safe = [p for p in plan if p["class"] == "БЕЗПЕЧНО"]
    if args.only:
        safe = [p for p in safe if p["name"] in args.only]
    if not safe:
        print("Немає репозиторіїв для чистки.")
        return 3
    if not args.yes:
        print("Буде видалено та перестворено:")
        for p in safe:
            print(f"  {p['owner']}/{p['name']}")
        try:
            count = input(f"Введіть кількість репозиторіїв ({len(safe)}): ").strip()
            if count != str(len(safe)):
                print("Невірна кількість. Скасовано.")
                return 3
        except (EOFError, KeyboardInterrupt):
            print("\nСкасовано.")
            return 3
    errors = []
    for p in safe:
        print(f"Обробка {p['owner']}/{p['name']}...")
        if not backup_repo(p):
            print(f"  Пропущено: бекап не вдався")
            continue
        save_meta(p)
        if not verify_clean_local(p):
            print(f"  Пропущено: локальний клон не чистий")
            continue
        # Видалення
        rc, _, err = run(["gh", "repo", "delete", f"{p['owner']}/{p['name']}", "--yes"], check=False)
        if rc != 0:
            print(f"  Помилка видалення: {err}")
            errors.append(p["name"])
            continue
        time.sleep(2)
        # Створення
        vis = "public" if not p["meta"].get("private") else "private"
        desc = p["meta"].get("description") or ""
        home = p["meta"].get("homepage") or ""
        cmd = ["gh", "repo", "create", f"{p['owner']}/{p['name']}", f"--{vis}"]
        if desc:
            cmd += ["--description", desc]
        if home:
            cmd += ["--homepage", home]
        rc, _, err = run(cmd, check=False)
        if rc != 0:
            print(f"  Помилка створення: {err}")
            errors.append(p["name"])
            continue
        # Пуш
        repo_path = Path(f"../{p['name']}")
        default_branch = p["meta"].get("default_branch", "main")
        new_url = f"https://github.com/{p['owner']}/{p['name']}.git"
        run(["git", "-C", str(repo_path), "remote", "set-url", "origin", new_url])
        rc, _, err = run(["git", "-C", str(repo_path), "push", "origin", default_branch], check=False)
        if rc != 0:
            print(f"  Помилка push: {err}")
            errors.append(p["name"])
            continue
        run(["git", "-C", str(repo_path), "push", "--tags"], check=False)
        # Налаштування
        patch = {
            "has_issues": p["meta"].get("has_issues", True),
            "has_wiki": p["meta"].get("has_wiki", True),
            "has_projects": p["meta"].get("has_projects", True),
        }
        gh_api(f"repos/{p['owner']}/{p['name']}", method="PATCH", data=patch)
        topics = p["meta"].get("topics", [])
        if topics:
            gh_api(f"repos/{p['owner']}/{p['name']}/topics", method="PUT",
                   data={"names": topics})
        # Верифікація
        ok = True
        if p["dirty"]:
            old_sha = p["dirty"][0][0]
            commit = gh_api(f"repos/{p['owner']}/{p['name']}/commits/{old_sha}")
            if commit is not None:
                print(f"  ПОТРЕБУЄ УВАГИ: старий коміт {old_sha} доступний")
                ok = False
        contrib = gh_api(f"repos/{p['owner']}/{p['name']}/contributors")
        if contrib and len(contrib) > 1:
            print(f"  ПОТРЕБУЄ УВАГИ: contributors > 1")
            ok = False
        if not ok:
            errors.append(p["name"])
            if args.stop_on_error:
                break
        time.sleep(2)
    if errors:
        print(f"ПОТРЕБУЄ УВАГИ: {errors}")
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Чистка репозиторіїв GitHub")
    parser.add_argument("--execute", action="store_true", help="Виконати фазу 2")
    parser.add_argument("--out", default="reports/CHYSTKA_PLAN.md")
    parser.add_argument("--only", help="Тільки вказані репо (через кому)")
    parser.add_argument("--include-risky", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if not check_gh():
        print("Немає доступу до gh")
        return 2

    only = set(args.only.split(",")) if args.only else None
    plan, error_count = build_plan(OWNERS, only)

    if not args.execute:
        write_report(plan, args.out)
        classes = {}
        for p in plan:
            classes[p["class"]] = classes.get(p["class"], 0) + 1
        print("Підсумок по класах:")
        for cls, cnt in classes.items():
            print(f"  {cls}: {cnt}")
        if error_count > 0:
            print(f"\nрепозиторіїв з помилками: {error_count}")
        print("\nЦе план. Нічого не змінено. Для виконання: --execute")
        return 0

    # Фаза 2
    if args.include_risky:
        risky = [p for p in plan if p["class"] == "РИЗИК"]
        for p in risky:
            confirm = input(f"Підтвердіть видалення {p['owner']}/{p['name']} (введіть 'видаляю'): ")
            if confirm != "видаляю":
                print(f"Пропущено {p['name']}")
                plan.remove(p)
    return execute_phase(plan, args)


if __name__ == "__main__":
    sys.exit(main())
