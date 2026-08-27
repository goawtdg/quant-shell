"""全量审计钩子 — 唯一观测面；关不掉，写失败必须抛错。"""
from __future__ import annotations

import json
import os
from contextvars import ContextVar
from datetime import date, datetime
from pathlib import Path
from typing import Any

from quant_shell.common.atomic_io import append_text
from quant_shell.common.logging_config import get_logger

logger = get_logger(__name__)

AUDIT_DIR = Path("data/audit")
JOB_ID_ENV = "QUANT_JOB_ID"
_SEVERITIES = frozenset({"INFO", "WARN", "ERROR"})

_run_id: ContextVar[str] = ContextVar("audit_run_id", default="")
_job_id: ContextVar[str] = ContextVar("audit_job_id", default="")


def reset() -> None:
    """新一轮编排入口：清空 run_id；job_id 从环境继承（Desk 子进程）。"""
    _run_id.set("")
    _job_id.set(os.environ.get(JOB_ID_ENV, "").strip())


def bind(*, run_id: str = "", job_id: str = "") -> None:
    """绑定当前协程/线程的 run_id / job_id，emit 时自动带上。"""
    if run_id:
        _run_id.set(run_id)
    if job_id:
        _job_id.set(job_id)


def current_run_id() -> str:
    return _run_id.get()


def current_job_id() -> str:
    return _job_id.get() or os.environ.get(JOB_ID_ENV, "").strip()


def emit(
    *,
    layer: str,
    event: str,
    severity: str = "INFO",
    run_id: str = "",
    job_id: str = "",
    symbol: str = "",
    error_code: str = "",
    message: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    """记录一条审计事件：logger + 当日 jsonl。append 失败抛 OSError。"""
    sev = severity.upper()
    if sev not in _SEVERITIES:
        raise ValueError(f"invalid audit severity: {severity}")
    payload: dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "run_id": run_id or current_run_id(),
        "job_id": job_id or current_job_id(),
        "symbol": symbol,
        "layer": layer,
        "event": event,
        "severity": sev,
        "error_code": error_code,
        "message": message,
        "data": data or {},
    }
    line = (
        f"audit layer={layer} event={event} code={error_code or '-'} "
        f"symbol={symbol or '-'} {message}"
    )
    if sev == "ERROR":
        logger.error("%s", line)
    elif sev == "WARN":
        logger.warning("%s", line)
    else:
        logger.info("%s", line)
    path = AUDIT_DIR / f"{date.today().isoformat()}.jsonl"
    append_text(path, json.dumps(payload, ensure_ascii=False, default=str))


def tail(max_lines: int = 80) -> list[dict[str, Any]]:
    """读取今日审计尾部；文件不存在返回空列表。"""
    path = AUDIT_DIR / f"{date.today().isoformat()}.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    for raw in lines[-max_lines:]:
        raw = raw.strip()
        if not raw:
            continue
        rows.append(json.loads(raw))
    return rows
