import threading
import time
from typing import Optional

from app.core.logger import logger

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency for local debugging
    psutil = None


def _guess_cpu_reason(process_name: str, cmdline: str) -> str:
    cmd = (cmdline or "").lower()
    name = (process_name or "").lower()

    if "celery" in name or "celery" in cmd or "beat" in cmd:
        return "Celery worker/beat is processing scheduled jobs or retrying tasks"
    if "uvicorn" in name or "gunicorn" in name or "fastapi" in cmd:
        return "FastAPI application is handling requests or startup work"
    if "postgres" in name or "postgresql" in cmd or "psql" in cmd:
        return "PostgreSQL is running heavy queries or indexes"
    if "redis" in name or "redis-server" in cmd:
        return "Redis is handling queue or cache operations"
    if "python" in name and ("pytest" in cmd or "python" in cmd and "-m" in cmd):
        return "Python process is running a script, worker, or test workload"
    if "python" in name:
        return "Python worker is doing CPU-heavy application logic"
    if "node" in name or "npm" in cmd:
        return "Node.js process is compiling or serving assets"
    if "zip" in cmd or "tar" in cmd or "7z" in cmd:
        return "Archiving or backup process is compressing large data"
    if not cmd and name:
        return f"{process_name} appears to be active without a readable command line"
    return f"Process {process_name} is active with command line: {cmd[:120]}"


def build_cpu_alert(
    system_cpu: float,
    threshold: float,
    process_name: str,
    process_pid: int,
    process_cpu: float,
    memory_percent: float,
    state: str,
    threads: int,
    cmdline: str,
    reason: str,
) -> str:
    return (
        f"[CPU_ALERT] System CPU {system_cpu:.1f}% is above {threshold:.1f}% threshold. "
        f"Top process: {process_name} (pid={process_pid}) with CPU {process_cpu:.1f}%, "
        f"memory {memory_percent:.1f}%, state={state}, threads={threads}. "
        f"Command: {cmdline or 'n/a'}. Reason: {reason}."
    )


def get_top_cpu_process() -> Optional[dict]:
    if psutil is None:
        return None

    try:
        processes = []
        for proc in psutil.process_iter([
            "pid",
            "name",
            "cpu_percent",
            "memory_percent",
            "cmdline",
            "status",
            "num_threads",
        ]):
            try:
                data = proc.info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            if not data or data.get("cpu_percent") is None:
                continue

            processes.append({
                "pid": data.get("pid"),
                "name": data.get("name") or "unknown",
                "cpu_percent": float(data.get("cpu_percent") or 0.0),
                "memory_percent": float(data.get("memory_percent") or 0.0),
                "cmdline": " ".join(data.get("cmdline") or []),
                "state": data.get("status") or "unknown",
                "threads": int(data.get("num_threads") or 0),
            })

        if not processes:
            return None

        return max(processes, key=lambda item: item["cpu_percent"])
    except Exception:
        logger.exception("[CPU_MONITOR] Failed while collecting process list")
        return None


def check_cpu_usage(threshold_percent: float = 70.0) -> Optional[str]:
    if psutil is None:
        logger.warning("[CPU_MONITOR] psutil is not installed; CPU monitoring disabled.")
        return None

    try:
        system_cpu = float(psutil.cpu_percent(interval=1.0))
        if system_cpu < threshold_percent:
            return None

        top_process = get_top_cpu_process()
        if not top_process:
            return build_cpu_alert(
                system_cpu=system_cpu,
                threshold=threshold_percent,
                process_name="unknown",
                process_pid=0,
                process_cpu=0.0,
                memory_percent=0.0,
                state="unknown",
                threads=0,
                cmdline="n/a",
                reason="system is overloaded but no process list was available",
            )

        process_name = top_process["name"]
        process_pid = top_process["pid"]
        process_cpu = top_process["cpu_percent"]
        memory_percent = top_process["memory_percent"]
        state = top_process["state"]
        threads = top_process["threads"]
        cmdline = top_process["cmdline"]
        reason = _guess_cpu_reason(process_name, cmdline)

        return build_cpu_alert(
            system_cpu=system_cpu,
            threshold=threshold_percent,
            process_name=process_name,
            process_pid=process_pid,
            process_cpu=process_cpu,
            memory_percent=memory_percent,
            state=state,
            threads=threads,
            cmdline=cmdline,
            reason=reason,
        )
    except Exception:
        logger.exception("[CPU_MONITOR] Failed to evaluate CPU load")
        return None


def start_cpu_monitor(threshold_percent: float = 85.0, interval_seconds: int = 60) -> threading.Thread:
    """Start background CPU monitor.
    
    Args:
        threshold_percent: Alert only if CPU exceeds this (default 85% to reduce spam)
        interval_seconds: Check interval (default 60s to reduce log noise)
    """
    def _monitor_loop() -> None:
        while True:
            time.sleep(interval_seconds)
            try:
                alert = check_cpu_usage(threshold_percent)
                if alert:
                    logger.warning(alert)
            except Exception:
                logger.exception("[CPU_MONITOR] Background monitor loop crashed")

    thread = threading.Thread(target=_monitor_loop, name="cpu-monitor", daemon=True)
    thread.start()
    logger.info(
        f"[CPU_MONITOR] Started with threshold {threshold_percent}% and interval {interval_seconds}s"
    )
    return thread
