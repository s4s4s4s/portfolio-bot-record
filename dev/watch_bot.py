#!/usr/bin/env python3
"""Watchdog: перезапуск bot.main при протухшем heartbeat или дубликатах процесса.

Запуск из корня проекта:
  python dev/watch_bot.py

Логи: logs/watchdog.log
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import get_settings  # noqa: E402
from core.logging import configure_logging, get_logger  # noqa: E402

HEARTBEAT = ROOT / "logs" / "heartbeat.json"
WATCHDOG_LOG = ROOT / "logs" / "watchdog.log"
PID_FILE = ROOT / "bot" / "main.pid"
POLL_SEC = 15


def _append_watchdog(msg: str) -> None:
    WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    with WATCHDOG_LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"{ts} | {msg}\n")


def _bot_pids() -> list[int]:
    pids: list[int] = []
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmd = proc.info.get("cmdline") or []
            line = " ".join(str(x) for x in cmd)
            if "bot.main" in line or "-m bot.main" in line:
                pids.append(int(proc.info["pid"]))
    except ImportError:
        if sys.platform == "win32":
            out = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'bot\\.main' } | "
                    "Select-Object -ExpandProperty ProcessId",
                ],
                capture_output=True,
                text=True,
                cwd=ROOT,
            )
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
    return pids


def _kill_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
            else:
                os.kill(pid, 9)
            _append_watchdog(f"killed pid={pid}")
        except OSError as exc:
            _append_watchdog(f"kill_failed pid={pid} err={exc}")


def _read_heartbeat_age_sec() -> float | None:
    if not HEARTBEAT.is_file():
        return None
    try:
        payload = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        ts = float(payload.get("ts", 0))
        return time.time() - ts
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def _start_bot(log: object) -> subprocess.Popen[bytes] | None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "bot.main"],
            cwd=ROOT,
            env=env,
        )
        _append_watchdog(f"started bot pid={proc.pid}")
        log.info("watchdog started bot pid={pid}", pid=proc.pid)  # type: ignore[attr-defined]
        return proc
    except OSError as exc:
        _append_watchdog(f"start_failed err={exc}")
        log.error("watchdog start_failed err={err}", err=exc)  # type: ignore[attr-defined]
        return None


def main() -> None:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        json_output=settings.log_json,
        log_dir=settings.log_dir,
        log_file_enabled=settings.log_file_enabled,
        log_file_max_mb=settings.log_file_max_mb,
    )
    log = get_logger()
    log.info(
        "watchdog started poll_sec={poll} max_stale_sec={max_stale}",
        poll=POLL_SEC,
        max_stale=settings.watchdog_max_stale_sec,
    )

    child: subprocess.Popen[bytes] | None = None
    while True:
        pids = _bot_pids()
        if len(pids) > 1:
            msg = f"duplicate_bot_processes count={len(pids)} pids={pids}"
            log.warning(msg)
            _append_watchdog(msg)
            _kill_pids(pids)
            if PID_FILE.is_file():
                PID_FILE.unlink(missing_ok=True)
            child = _start_bot(log)
            time.sleep(POLL_SEC)
            continue

        age = _read_heartbeat_age_sec()
        stale_limit = float(settings.watchdog_max_stale_sec)
        needs_restart = False
        reason = ""

        if child is not None and child.poll() is not None:
            needs_restart = True
            reason = f"child_exit code={child.returncode}"
        elif not pids and child is None:
            needs_restart = True
            reason = "no_bot_process"
        elif age is None:
            if pids:
                needs_restart = False
            else:
                needs_restart = True
                reason = "no_heartbeat_no_process"
        elif age > stale_limit:
            needs_restart = True
            reason = f"heartbeat_stale age_sec={age:.0f} limit={stale_limit:.0f}"

        if needs_restart:
            log.warning("watchdog_restart reason={reason}", reason=reason)
            _append_watchdog(f"restart reason={reason}")
            if pids:
                _kill_pids(pids)
            if PID_FILE.is_file():
                PID_FILE.unlink(missing_ok=True)
            if child is not None and child.poll() is None:
                child.terminate()
            child = _start_bot(log)
        else:
            log.debug(
                "watchdog_ok pids={pids} heartbeat_age_sec={age}",
                pids=pids,
                age=round(age, 1) if age is not None else None,
            )

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("watchdog stopped")
