from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class CrawlManager:

    def __init__(self, command: Optional[list[str]] = None):
        self.command                     = command or [sys.executable, "-u", "scripts/pipeline.py", "--crawl-only"]
        self._lock                       = threading.Lock()
        self._state                      = "idle"
        self._logs: list[str]            = []
        self._started_at: Optional[str]  = None
        self._finished_at: Optional[str] = None
        self._exit_code: Optional[int]   = None

    def start(self) -> bool:
        with self._lock:
            if self._state == "running": return False
            self._state       = "running"
            self._logs        = [f"$ {' '.join(self.command)}"]
            self._started_at  = timestamp()
            self._finished_at = None
            self._exit_code   = None
        threading.Thread(target=self._run, name="component-crawler", daemon=True).start()
        return True

    def snapshot(self, after: int = 0) -> dict:
        with self._lock:
            offset = max(0, min(after, len(self._logs)))
            return {
                "state": self._state,
                "logs": self._logs[offset:],
                "next_offset": len(self._logs),
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "exit_code": self._exit_code,
            }

    def _append(self, line: str) -> None:
        with self._lock:
            self._logs.append(line.rstrip("\r\n"))

    def _run(self) -> None:
        exit_code = 1
        try:
            process = subprocess.Popen(
                self.command,
                cwd=PROJECT_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            if process.stdout:
                for line in process.stdout:
                    self._append(line)
            exit_code = process.wait()
        except Exception as exc:
            self._append(f"Unable to start crawler: {type(exc).__name__}: {exc}")
        with self._lock:
            self._exit_code   = exit_code
            self._state       = "succeeded" if exit_code == 0 else "failed"
            self._finished_at = timestamp()
