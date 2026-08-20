#!/usr/bin/env python3
"""
Tek School — Crash Investigator
Run this after a crash to instantly identify who caused it.

Usage:
    python scripts/who_crashed.py
"""

import subprocess
import re
from datetime import datetime

CONTAINERS = ["fastapi-app", "postgres-db", "celery-worker", "celery-beat", "redis"]

def run(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip()


def print_header(title):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)


def check_container_status():
    print_header("1. CONTAINER STATUS — Who crashed?")
    output = run("docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.RunningFor}}'")
    print(output)

    # Highlight crashed containers
    for line in output.splitlines():
        if "Exited (137)" in line:
            name = line.split()[0]
            print(f"\n  🔴 OOM-KILLED (out of memory): {name}")
            print(f"     → Docker killed it because it exceeded memory limit")
        elif "Exited (1)" in line:
            name = line.split()[0]
            print(f"\n  🔴 CODE CRASH: {name}")
            print(f"     → Application error, check its logs")
        elif "Restarting" in line:
            name = line.split()[0]
            print(f"\n  🔴 CRASH LOOP: {name}")
            print(f"     → Crashing repeatedly, fix immediately")


def check_memory():
    print_header("2. MEMORY USAGE — Who is using too much?")
    output = run("docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.CPUPerc}}'")
    print(output)


def check_recent_errors():
    print_header("3. RECENT ERRORS — Last 50 lines per container")
    for container in CONTAINERS:
        logs = run(f"docker logs {container} --tail=50 2>&1")
        errors = [
            line for line in logs.splitlines()
            if any(kw in line.lower() for kw in [
                "error", "fatal", "crash", "killed", "exception",
                "oom", "recovery mode", "out of memory", "traceback",
                "connection refused", "timeout"
            ])
        ]
        if errors:
            print(f"\n  🔴 [{container}] Found {len(errors)} error(s):")
            for e in errors[-10:]:  # show last 10 errors
                print(f"     {e.strip()}")
        else:
            print(f"\n  ✅ [{container}] No errors found")


def check_postgres_slow_queries():
    print_header("4. SLOW QUERIES — PostgreSQL (>1 second)")
    logs = run("docker logs postgres-db --tail=500 2>&1")
    slow = [
        line for line in logs.splitlines()
        if "duration:" in line.lower()
    ]
    if slow:
        print(f"  Found {len(slow)} slow query log(s):")
        for line in slow[-10:]:
            # Extract duration
            match = re.search(r"duration: ([\d.]+) ms", line)
            if match:
                ms = float(match.group(1))
                severity = "🔴" if ms > 5000 else "🟡" if ms > 2000 else "🟠"
                print(f"  {severity} {ms/1000:.1f}s — {line.strip()[:120]}")
    else:
        print("  ✅ No slow queries in recent logs")


def check_celery_tasks():
    print_header("5. CELERY TASKS — Recent task history")
    logs = run("docker logs celery-worker --tail=200 2>&1")
    task_lines = [
        line for line in logs.splitlines()
        if any(kw in line for kw in [
            "Task", "check_student_renewals", "send_monthly_followup",
            "CRASH", "✅", "❌", "started", "succeeded", "failed", "retry"
        ])
    ]
    if task_lines:
        for line in task_lines[-20:]:
            print(f"  {line.strip()}")
    else:
        print("  No recent Celery task logs found")


def check_app_error_log():
    print_header("6. APP ERROR LOG — logs/errors.log")
    try:
        with open("logs/errors.log", "r") as f:
            lines = f.readlines()
        if lines:
            print(f"  Found {len(lines)} error(s) in logs/errors.log")
            print("  Last 10 errors:")
            for line in lines[-10:]:
                print(f"  {line.strip()}")
        else:
            print("  ✅ errors.log is empty — no app errors recorded")
    except FileNotFoundError:
        print("  ℹ️  logs/errors.log not found yet (app hasn't crashed since logging was added)")


def summary():
    print_header("SUMMARY — What to check next")
    print("""
  If you saw "Exited (137)"  → OOM-kill. Check memory limits in docker-compose.yml
  If you saw "Exited (1)"    → Code error. Check that container's logs above.
  If you saw slow queries     → Check indexes. Run: scripts/add_performance_indexes.sql
  If you saw Celery CRASH     → Check logs/errors.log for full traceback
  If you saw "recovery mode"  → PostgreSQL was OOM-killed. Check postgres memory.

  Quick commands:
    docker logs postgres-db   --tail=200   # Full DB logs
    docker logs celery-worker --tail=200   # Full task logs
    docker logs fastapi-app   --tail=200   # Full API logs
    cat logs/errors.log                    # App error log
    docker stats --no-stream               # Live memory check
    """)


if __name__ == "__main__":
    print(f"\nTek School Crash Investigator — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    check_container_status()
    check_memory()
    check_recent_errors()
    check_postgres_slow_queries()
    check_celery_tasks()
    check_app_error_log()
    summary()
