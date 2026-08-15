#!/usr/bin/env python3
"""clean_loop.py — safe AI-signature cleanup loop with integrity verification."""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OWNERS = ["VladSh77", "fayna-digital", "faynaagency"]
PROTECTED = ["DevJournal", "fayna-core-configs"]

SIGNATURE_PATTERNS = [
    r"co-authored-by:.*(claude|anthropic|noreply@anthropic\.com|gpt|copilot|cursor)",
    r"generated with .*(claude|ai)",
    r"🤖 generated",
    r"created by claude",
]
SIGNATURE_RE = re.compile("|".join(SIGNATURE_PATTERNS), re.IGNORECASE)
AUTHOR_RE = re.compile(r"claude|anthropic|noreply@anthropic", re.IGNORECASE)


def run(args, cwd=None, check=True, capture=True):
    """Run a command with argument list, return stdout or raise."""
    try:
        result = subprocess.run(
            args, shell=False, cwd=cwd, capture_output=capture, text=True,
            encoding="utf-8", errors="replace"
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}")
        return result.stdout.strip() if capture else result
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Command error: {' '.join(args)}: {e}")


def get_owner(repo_path):
    """Get GitHub owner from remote URL."""
    try:
        remote = run(["git", "remote", "get-url", "origin"], cwd=repo_path, check=False)
        if not remote:
            return None
        # ssh: git@github.com:Owner/repo.git or https://github.com/Owner/repo.git
        m = re.search(r"(?:github\.com[:/])([^/]+)/", remote)
        return m.group(1) if m else None
    except Exception:
        return None


def count_signatures(repo_path):
    """Count AI signatures in commit messages (method 1: own parser)."""
    try:
        # Use --all to match git method, split by NUL separator
        log = run(["git", "log", "--all", "--format=%B%x00"], cwd=repo_path, check=False)
        if not log:
            return 0
        # Split by NUL and count signatures in each full message
        messages = log.split("\x00")
        count = 0
        for msg in messages:
            if msg.strip() and SIGNATURE_RE.search(msg):
                count += 1
        return count
    except Exception:
        return 0


def count_signatures_git(repo_path):
    """Count AI signatures via git grep (method 2: git's own search)."""
    try:
        # Use git log with grep for each pattern, --all to match parser
        total = 0
        for pattern in SIGNATURE_PATTERNS:
            # Escape for git grep
            git_pattern = pattern.replace("\\", "\\\\").replace("|", "\\|")
            out = run(["git", "log", "--all", "--format=%H", "--grep=" + git_pattern, "-i"], cwd=repo_path, check=False)
            if out:
                total += len(out.splitlines())
        return total
    except Exception:
        return 0


def get_snapshot(repo_path):
    """Capture integrity snapshot of current branch."""
    snap = {}
    snap["count"] = int(run(["git", "rev-list", "HEAD", "--count"], cwd=repo_path) or 0)
    snap["tree"] = run(["git", "rev-parse", "HEAD^{tree}"], cwd=repo_path)
    # Trees of all commits (limit 200)
    commits = run(["git", "rev-list", "HEAD"], cwd=repo_path).splitlines()
    snap["trees_all"] = []
    snap["trees_limited"] = False
    if len(commits) > 200:
        commits = commits[:200]
        snap["trees_limited"] = True
    for c in commits:
        snap["trees_all"].append(run(["git", "rev-parse", f"{c}^{{tree}}"], cwd=repo_path))
    snap["tags"] = run(["git", "tag"], cwd=repo_path).splitlines()
    snap["branches"] = run(["git", "branch", "--format=%(refname:short)"], cwd=repo_path).splitlines()
    return snap


def verify_integrity(before, after):
    """Compare snapshots, return (ok, message)."""
    issues = []
    if before["count"] != after["count"]:
        issues.append(f"комітів {before['count']}!={after['count']}")
    if before["tree"] != after["tree"]:
        issues.append(f"дерево HEAD {before['tree'][:8]}!={after['tree'][:8]}")
    if before["trees_all"] != after["trees_all"]:
        issues.append("послідовність дерев змінена")
    if set(before["tags"]) != set(after["tags"]):
        issues.append("теги зникли/змінились")
    if set(before["branches"]) != set(after["branches"]):
        issues.append("гілки зникли/змінились")
    if issues:
        return False, "; ".join(issues)
    return True, f"✓ комітів {before['count']}={after['count']}, дерев {len(before['trees_all'])}={len(after['trees_all'])}"


def rollback(repo_path, backup_branch):
    """Rollback to backup branch."""
    run(["git", "reset", "--hard", backup_branch], cwd=repo_path)
    run(["git", "for-each-ref", "--format=%(refname)", "refs/original/"], cwd=repo_path, check=False)


def write_filter_script(script_path):
    """Write msg-filter script to temp file."""
    script = '''#!/usr/bin/env python3
import sys, re

patterns = [
    r"co-authored-by:.*(claude|anthropic|noreply@anthropic\\.com|gpt|copilot|cursor)",
    r"generated with .*(claude|ai)",
    r"🤖 generated",
    r"created by claude",
]
re_combined = re.compile("|".join(patterns), re.IGNORECASE | re.DOTALL)

def clean(msg):
    # Apply regex to entire message, not line by line
    if re_combined.search(msg):
        # Remove matching lines
        lines = msg.split("\\n")
        out = []
        for line in lines:
            if re_combined.search(line):
                continue
            out.append(line)
        return "\\n".join(out)
    return msg

data = sys.stdin.buffer.read().decode("utf-8", errors="replace")
sys.stdout.write(clean(data))
'''
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)
    os.chmod(script_path, 0o755)


def clean_repo(repo_path, repo_name, max_attempts, log_path):
    """Clean a single repo. Returns (status, before_count, after_count, attempts, integrity_msg, push_result)."""
    status = "ЧИСТО"
    before_count = count_signatures(repo_path)
    after_count = before_count
    attempts = 0
    integrity_msg = ""
    push_result = "—"

    if before_count == 0:
        # Double-check with git method
        git_count = count_signatures_git(repo_path)
        if git_count != 0:
            return "РОЗБІЖНІСТЬ ПЕРЕВІРОК", before_count, git_count, 0, f"парсер={before_count}, git={git_count}", "—"
        return status, 0, 0, 0, "✓ комітів 0=0, дерев 0=0", "—"

    # Check for dirty tree or rebase/merge state
    dirty = run(["git", "status", "--porcelain"], cwd=repo_path, check=False)
    if dirty:
        return "ПРОПУСК (брудне)", before_count, before_count, 0, "робоче дерево не чисте", "—"
    rebase_merge = run(["git", "rev-parse", "--git-path", "rebase-merge"], cwd=repo_path, check=False)
    rebase_apply = run(["git", "rev-parse", "--git-path", "rebase-apply"], cwd=repo_path, check=False)
    if os.path.exists(rebase_merge) or os.path.exists(rebase_apply):
        return "ПРОПУСК (rebase/merge)", before_count, before_count, 0, "стан rebase/merge", "—"

    # Backup branch
    backup = f"backup/pre-clean-{int(time.time())}"
    run(["git", "branch", backup], cwd=repo_path)

    # Snapshot before
    before_snap = get_snapshot(repo_path)

    # Write filter script
    script_path = os.path.join(tempfile.gettempdir(), f"msg_filter_{repo_name}.py")
    write_filter_script(script_path)

    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        before_attempt = count_signatures(repo_path)

        # Run filter-branch
        try:
            run(
                ["git", "filter-branch", "-f", "--msg-filter", f"{sys.executable} {script_path}", "HEAD"],
                cwd=repo_path
            )
        except RuntimeError as e:
            rollback(repo_path, backup)
            return "ЗЛАМАНО-ВІДКАЧЕНО", before_count, before_attempt, attempts, f"filter-branch: {str(e)[:100]}", "—"

        after_snap = get_snapshot(repo_path)
        ok, msg = verify_integrity(before_snap, after_snap)
        if not ok:
            rollback(repo_path, backup)
            return "ЗЛАМАНО-ВІДКАЧЕНО", before_count, before_attempt, attempts, msg, "—"

        after_count = count_signatures(repo_path)
        git_count = count_signatures_git(repo_path)

        # Log attempt
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"прохід {attempts} | слідів до {before_attempt} | слідів після {after_count} | "
                    f"комітів {before_snap['count']}={after_snap['count']} | дерев збіг {'так' if ok else 'ні'} | "
                    f"вердикт {'чисто' if after_count == 0 else 'ще брудно'}\n")

        if after_count == 0 and git_count == 0:
            integrity_msg = msg
            status = "ОЧИЩЕНО"
            break
        elif after_count != git_count:
            # Diagnostic: show up to 3 SHAs found by one method but not the other
            parser_shas = set()
            git_shas = set()
            try:
                # Get SHAs from parser method
                log = run(["git", "log", "--all", "--format=%H%x00%B%x00"], cwd=repo_path, check=False)
                if log:
                    parts = log.split("\x00")
                    for i in range(0, len(parts)-1, 2):
                        sha = parts[i]
                        msg_text = parts[i+1] if i+1 < len(parts) else ""
                        if SIGNATURE_RE.search(msg_text):
                            parser_shas.add(sha)
                
                # Get SHAs from git method
                for pattern in SIGNATURE_PATTERNS:
                    git_pattern = pattern.replace("\\", "\\\\").replace("|", "\\|")
                    out = run(["git", "log", "--all", "--format=%H", "--grep=" + git_pattern, "-i"], cwd=repo_path, check=False)
                    if out:
                        git_shas.update(out.splitlines())
            except Exception:
                pass
            
            only_git = list(git_shas - parser_shas)[:3]
            only_parser = list(parser_shas - git_shas)[:3]
            
            diag_parts = [f"парсер={after_count}, git={git_count}"]
            if only_git:
                diag_parts.append(f"тільки-git: {', '.join(only_git)}")
            if only_parser:
                diag_parts.append(f"тільки-парсер: {', '.join(only_parser)}")
            
            status = "РОЗБІЖНІСТЬ ПЕРЕВІРОК"
            integrity_msg = "; ".join(diag_parts)
            break
        elif after_count == 0:
            # git method still finds something
            status = "РОЗБІЖНІСТЬ ПЕРЕВІРОК"
            integrity_msg = f"парсер=0, git={git_count}"
            break
    else:
        status = "НЕ ПІДДАЄТЬСЯ"
        integrity_msg = f"після {max_attempts} спроб слідів: {after_count}"

    # Cleanup temp script
    try:
        os.remove(script_path)
    except OSError:
        pass

    return status, before_count, after_count, attempts, integrity_msg, push_result


def write_audit_input(repo_results, out_dir):
    """Write machine-readable audit input file."""
    lines = []
    for r in repo_results:
        lines.append(f"РЕПО: {r['name']}")
        lines.append(f"СТАТУС: {r['status']}")
        lines.append(f"СЛІДІВ_ДО: {r['before']}")
        lines.append(f"СЛІДІВ_ПІСЛЯ_ПАРСЕР: {r['after']}")
        lines.append(f"СЛІДІВ_ПІСЛЯ_GIT: {r.get('after_git', '—')}")
        lines.append(f"КОМІТІВ_ДО: {r.get('commits_before', '—')}")
        lines.append(f"КОМІТІВ_ПІСЛЯ: {r.get('commits_after', '—')}")
        lines.append(f"ДЕРЕВА_ЗБІГ: {r.get('trees_match', '—')}")
        lines.append(f"PUSH: {r.get('push', '—')}")
        # Sample messages
        if r.get('status') == 'ОЧИЩЕНО':
            try:
                msgs = run(["git", "log", "--format=%B", "-5"], cwd=r['path'], check=False).split("\n\n")
                for m in msgs[:5]:
                    lines.append(f"ПРИКЛАД: {m[:200]}")
            except Exception:
                pass
        lines.append("---")
    with open(os.path.join(out_dir, "CLEAN_AUDIT_INPUT.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_audit_task(out_dir):
    """Write audit task file."""
    task = """Ти — незалежний аудитор. Нижче машинний зріз результатів масового очищення
git-історії від AI-підписів. Твоє завдання — не повірити на слово, а знайти
ознаки того, що очищення неповне або щось зламано.
Для кожного репо дай рядок: `<репо> | ЧИСТО | ПІДОЗРА | ЗЛАМАНО | <причина>`.
Особливо шукай: репо, де сліди «зникли» але кількість комітів змінилась;
репо зі статусом «чисто» без жодного проходу; розбіжності між двома способами
підрахунку; повідомлення комітів, у яких лишились згадки моделей у будь-якому
регістрі чи формі. Наприкінці — рядок `ПІДСУМОК: <скільки ЧИСТО> / <ПІДОЗРА> / <ЗЛАМАНО>`
і пряма відповідь так/ні на питання «чи можна вважати очищення завершеним».
Жодного тексту поза цим форматом."""
    with open(os.path.join(out_dir, "CLEAN_AUDIT_TASK.md"), "w", encoding="utf-8") as f:
        f.write(task)


def run_audit(root, out_dir):
    """Run external audit via research_cli.py."""
    # Find research_cli.py
    candidates = [
        os.path.join(root, "docs-sorter", "research_cli.py"),
        os.path.expanduser("~/Developer/Fayna-Workspace/Projects/docs-sorter/research_cli.py"),
    ]
    cli_path = None
    for c in candidates:
        if os.path.exists(c):
            cli_path = c
            break
    if not cli_path:
        return False, "research_cli.py не знайдено"

    cmd = [
        "python3", cli_path, "chat",
        "--task-file", os.path.join(out_dir, "CLEAN_AUDIT_TASK.md"),
        "--input-file", os.path.join(out_dir, "CLEAN_AUDIT_INPUT.txt"),
        "--out", os.path.join(out_dir, "CLEAN_AUDIT.md"),
        "--provider", "openrouter", "--model", "google/gemini-3.7-flash"
    ]
    try:
        result = subprocess.run(cmd, shell=False, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return False, result.stderr[:200]
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "таймаут аудиту"
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Clean AI signatures from git history")
    parser.add_argument("--root", default=os.path.expanduser("~/Developer/Fayna-Workspace/Projects"))
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--include-protected", action="store_true")
    parser.add_argument("--only", default="")
    parser.add_argument("--out", default="reports/CLEAN_LOOP.md")
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--no-audit", action="store_true")
    args = parser.parse_args()

    root = os.path.expanduser(args.root)
    if not os.path.isdir(root):
        print(f"❌ Корінь не знайдено: {root}")
        sys.exit(3)

    out_path = args.out
    if not os.path.isabs(out_path):
        out_path = os.path.join(root, out_path)
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    
    # Create .clean_loop directory relative to script root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    clean_loop_dir = os.path.join(script_dir, ".clean_loop")
    os.makedirs(clean_loop_dir, exist_ok=True)

    # Discover repos
    repos = []
    for item in sorted(os.listdir(root)):
        full = os.path.join(root, item)
        if os.path.isdir(full) and os.path.isdir(os.path.join(full, ".git")):
            repos.append((item, full))

    if args.only:
        only_set = set(args.only.split(","))
        repos = [(n, p) for n, p in repos if n in only_set]

    if not repos:
        print("❌ Репозиторіїв не знайдено")
        sys.exit(3)

    # Process repos
    results = []
    stats = {"ЧИСТО": 0, "ОЧИЩЕНО": 0, "ПРОПУСК (брудне)": 0, "ЗАХИЩЕНО": 0,
             "ЧУЖЕ": 0, "НЕ ПІДДАЄТЬСЯ": 0, "ЗЛАМАНО-ВІДКАЧЕНО": 0, "РОЗБІЖНІСТЬ ПЕРЕВІРОК": 0}
    pushed = 0

    for repo_name, repo_path in repos:
        # Protected check
        if repo_name in PROTECTED and not args.include_protected:
            results.append({"name": repo_name, "path": repo_path, "status": "ЗАХИЩЕНО",
                            "before": 0, "after": 0, "attempts": 0, "integrity": "—", "push": "—"})
            stats["ЗАХИЩЕНО"] += 1
            continue

        # Owner check
        owner = get_owner(repo_path)
        if owner and owner not in OWNERS:
            results.append({"name": repo_name, "path": repo_path, "status": "ЧУЖЕ",
                            "before": 0, "after": 0, "attempts": 0, "integrity": "—", "push": "—"})
            stats["ЧУЖЕ"] += 1
            continue

        log_path = os.path.join(clean_loop_dir, f"{repo_name}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Лог очищення: {repo_name}\n")

        status, before, after, attempts, integrity, push_result = clean_repo(
            repo_path, repo_name, args.max_attempts, log_path
        )

        # Push if requested and status is ОЧИЩЕНО
        if status == "ОЧИЩЕНО" and args.push and args.yes:
            try:
                run(["git", "push", "--force-with-lease"], cwd=repo_path)
                push_result = "✓ запушено"
                pushed += 1
            except RuntimeError as e:
                push_result = f"❌ {str(e)[:50]}"
        elif status == "ОЧИЩЕНО" and args.push and not args.yes:
            push_result = "пропущено (немає --yes)"

        results.append({"name": repo_name, "path": repo_path, "status": status,
                        "before": before, "after": after, "attempts": attempts,
                        "integrity": integrity, "push": push_result})
        stats[status] = stats.get(status, 0) + 1

    # Write audit input
    write_audit_input(results, out_dir)
    write_audit_task(out_dir)

    # Run external audit
    audit_summary = ""
    audit_ok = False
    if not args.no_audit:
        ok, err = run_audit(root, out_dir)
        if ok:
            audit_ok = True
            try:
                with open(os.path.join(out_dir, "CLEAN_AUDIT.md"), "r", encoding="utf-8") as f:
                    content = f.read()
                # Extract summary
                for line in content.splitlines():
                    if line.startswith("ПІДСУМОК:"):
                        audit_summary = line
                        break
                if not audit_summary:
                    audit_summary = "ПІДСУМОК не знайдено в аудиті"
            except Exception as e:
                audit_summary = f"помилка читання аудиту: {e}"
        else:
            audit_summary = f"аудит не виконано: {err}"
            print(f"❌ {audit_summary}")
            sys.exit(4)

    # Write report
    report_lines = []
    report_lines.append("# Звіт очищення AI-підписів\n")
    report_lines.append("| репо | слідів до | слідів після | спроб | цілісність | статус | push |")
    report_lines.append("|------|-----------|-------------|-------|------------|--------|------|")
    for r in results:
        report_lines.append(
            f"| {r['name']} | {r['before']} | {r['after']} | {r['attempts']} | "
            f"{r['integrity']} | {r['status']} | {r['push']} |"
        )
    report_lines.append("")
    report_lines.append("## Підсумок")
    report_lines.append(f"Репозиторіїв:      {len(results)}")
    report_lines.append(f"ЧИСТО одразу:      {stats.get('ЧИСТО', 0)}")
    report_lines.append(f"ОЧИЩЕНО:           {stats.get('ОЧИЩЕНО', 0)}")
    report_lines.append(f"ПРОПУСК (брудне):  {stats.get('ПРОПУСК (брудне)', 0)}")
    report_lines.append(f"ЗАХИЩЕНО:          {stats.get('ЗАХИЩЕНО', 0)}")
    report_lines.append(f"ЧУЖЕ:              {stats.get('ЧУЖЕ', 0)}")
    report_lines.append(f"НЕ ПІДДАЄТЬСЯ:     {stats.get('НЕ ПІДДАЄТЬСЯ', 0)}")
    report_lines.append(f"ЗЛАМАНО-ВІДКАЧЕНО: {stats.get('ЗЛАМАНО-ВІДКАЧЕНО', 0)}")
    report_lines.append(f"РОЗБІЖНІСТЬ ПЕРЕВІРОК: {stats.get('РОЗБІЖНІСТЬ ПЕРЕВІРОК', 0)}")
    report_lines.append(f"Запушено:          {pushed}")
    if audit_summary:
        report_lines.append(f"\n## Аудит\n{audit_summary}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    # Self-check: sum of counters must equal number of repos
    total_stats = sum(stats.values())
    if total_stats != len(results):
        print(f"❌ статистика не сходиться: сума {total_stats} ≠ репо {len(results)}")
        sys.exit(5)

    # Verify report was written correctly
    with open(out_path, "r", encoding="utf-8") as f:
        content = f.read()
    table_rows = [line for line in content.splitlines() if line.startswith("| ") and not line.startswith("|------")]
    # Subtract header row
    table_rows = table_rows[1:] if table_rows else []
    
    print(f"звіт: {out_path} ({os.path.getsize(out_path)} байт, {len(table_rows)} рядків таблиці)")
    
    if len(table_rows) < len(results):
        print(f"❌ у звіті {len(table_rows)} рядків замість {len(results)}")
        sys.exit(5)

    # Console output
    print(f"Репозиторіїв:      {len(results)}")
    print(f"ЧИСТО одразу:      {stats.get('ЧИСТО', 0)}")
    print(f"ОЧИЩЕНО:           {stats.get('ОЧИЩЕНО', 0)}")
    print(f"ПРОПУСК (брудне):  {stats.get('ПРОПУСК (брудне)', 0)}")
    print(f"ЗАХИЩЕНО:          {stats.get('ЗАХИЩЕНО', 0)}")
    print(f"ЧУЖЕ:              {stats.get('ЧУЖЕ', 0)}")
    print(f"НЕ ПІДДАЄТЬСЯ:     {stats.get('НЕ ПІДДАЄТЬСЯ', 0)}")
    print(f"ЗЛАМАНО-ВІДКАЧЕНО: {stats.get('ЗЛАМАНО-ВІДКАЧЕНО', 0)}")
    print(f"Запушено:          {pushed}")
    if audit_summary:
        print(f"\n{audit_summary}")

    # Exit code
    if stats.get("ЗЛАМАНО-ВІДКАЧЕНО", 0) > 0:
        sys.exit(2)
    if stats.get("НЕ ПІДДАЄТЬСЯ", 0) > 0:
        sys.exit(1)
    if stats.get("ЧИСТО", 0) == 0 and stats.get("ОЧИЩЕНО", 0) == 0:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
