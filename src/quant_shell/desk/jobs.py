"""精简任务队列 — 仅 shell_paper / linkage。"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from quant_shell.common.atomic_io import write_text_atomic
from quant_shell.config.env_loader import project_root
from quant_shell.desk.paths import jobs_dir

logger = logging.getLogger("quant_shell.desk.jobs")

_ACTIVE = frozenset({"starting", "running"})
_lock = threading.Lock()
_running_by_lane: dict[str, str] = {}
_processes: dict[str, subprocess.Popen[str]] = {}
_log_handles: dict[str, TextIO[str]] = {}

ALLOWED_TYPES = frozenset({"shell_paper", "linkage"})
_TYPE_LANE = {"shell_paper": "trade", "linkage": "trade"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _job_json(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def _job_log(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.log"


def _write_job(meta: dict[str, Any]) -> None:
    jobs_dir().mkdir(parents=True, exist_ok=True)
    write_text_atomic(_job_json(str(meta["id"])), json.dumps(meta, ensure_ascii=False, indent=2))


def _read_job(job_id: str) -> dict[str, Any] | None:
    path = _job_json(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _tail_log(job_id: str, lines: int = 120) -> str:
    path = _job_log(job_id)
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _build_command(job_type: str, params: dict[str, Any]) -> list[str]:
    py = sys.executable
    root = project_root()
    if job_type == "shell_paper":
        symbol = str(params.get("symbol") or "510300").strip() or "510300"
        return [py, "-m", "quant_shell.cli", "run", "--symbol", symbol]
    if job_type == "linkage":
        cmd = [py, "-m", "quant_shell.cli", "linkage"]
        if params.get("skip_intel"):
            cmd.append("--skip-intel")
        if params.get("skip_stocks"):
            cmd.append("--skip-stocks")
        if params.get("skip_hold_review"):
            cmd.append("--skip-hold-review")
        symbol = str(params.get("symbol") or "").strip()
        if symbol:
            cmd.extend(["--symbol", symbol])
        return cmd
    raise ValueError(f"unsupported job type: {job_type}")


def _watch(job_id: str, lane: str) -> None:
    proc = _processes.get(job_id)
    if proc is None:
        return
    code = proc.wait()
    with _lock:
        meta = _read_job(job_id) or {"id": job_id, "type": "?", "lane": lane}
        meta["status"] = "succeeded" if code == 0 else "failed"
        meta["finished_at"] = _now()
        meta["returncode"] = code
        _write_job(meta)
        fh = _log_handles.pop(job_id, None)
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
        _processes.pop(job_id, None)
        if _running_by_lane.get(lane) == job_id:
            _running_by_lane.pop(lane, None)


def list_jobs(limit: int = 10) -> dict[str, Any]:
    root = jobs_dir()
    recent: list[dict[str, Any]] = []
    if root.is_dir():
        for path in sorted(root.glob("*.json"), reverse=True):
            try:
                meta = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(meta, dict):
                recent.append(meta)
            if len(recent) >= limit:
                break
    lanes: dict[str, dict[str, Any] | None] = {"trade": None, "eval": None}
    for job_id in list(_running_by_lane.values()):
        meta = _read_job(job_id)
        if meta and meta.get("status") in _ACTIVE:
            lane = str(meta.get("lane") or "trade")
            lanes[lane] = meta
    return {"lanes": lanes, "recent": recent}


def get_job(job_id: str, log_lines: int = 120) -> dict[str, Any] | None:
    meta = _read_job(job_id)
    if not meta:
        return None
    return {**meta, "log_tail": _tail_log(job_id, log_lines)}


def start_job(job_type: str, params: dict[str, Any] | None, *, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise PermissionError("confirm must be true")
    if job_type not in ALLOWED_TYPES:
        raise ValueError(f"unsupported type: {job_type} (allowed: shell_paper|linkage)")

    lane = _TYPE_LANE[job_type]
    with _lock:
        existing_id = _running_by_lane.get(lane)
        if existing_id:
            existing = _read_job(existing_id)
            if existing and existing.get("status") in _ACTIVE:
                raise RuntimeError(
                    f"{lane} 轨已有任务运行中: {existing.get('id')} ({existing.get('type')})"
                )

        job_id = uuid.uuid4().hex[:10]
        cmd = _build_command(job_type, params or {})
        jobs_dir().mkdir(parents=True, exist_ok=True)
        log_path = _job_log(job_id)
        meta: dict[str, Any] = {
            "id": job_id,
            "type": job_type,
            "lane": lane,
            "params": params or {},
            "command": cmd,
            "status": "starting",
            "created_at": _now(),
            "finished_at": None,
            "returncode": None,
            "pid": None,
        }
        _write_job(meta)

        log_fh = open(log_path, "w", encoding="utf-8")
        log_fh.write(f"$ {' '.join(cmd)}\n")
        log_fh.flush()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["QUANT_SHELL_ROOT"] = str(project_root())
        src = str(project_root() / "src")
        prev = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src if not prev else f"{src}{os.pathsep}{prev}"

        popen_kwargs: dict[str, Any] = {
            "cwd": str(project_root()),
            "stdout": log_fh,
            "stderr": subprocess.STDOUT,
            "text": True,
            "env": env,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(cmd, **popen_kwargs)
        meta["status"] = "running"
        meta["pid"] = proc.pid
        _write_job(meta)
        _processes[job_id] = proc
        _log_handles[job_id] = log_fh
        _running_by_lane[lane] = job_id
        threading.Thread(target=_watch, args=(job_id, lane), daemon=True).start()
        return meta


def cancel_job(job_id: str) -> dict[str, Any]:
    with _lock:
        meta = _read_job(job_id)
        if not meta:
            raise KeyError(job_id)
        proc = _processes.get(job_id)
        if proc and proc.poll() is None:
            proc.terminate()
        meta["status"] = "cancelled"
        meta["finished_at"] = _now()
        _write_job(meta)
        lane = str(meta.get("lane") or "trade")
        if _running_by_lane.get(lane) == job_id:
            _running_by_lane.pop(lane, None)
        return meta
