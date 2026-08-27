"""只读加载本仓 data/ 下的 linkage / portfolio / trades。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from quant_shell.common.atomic_io import write_text_atomic
from quant_shell.common.logging_config import get_logger
from quant_shell.config.settings import settings
from quant_shell.desk.paths import (
    equity_history_path,
    latest_linkage_path,
    linkage_dir,
    portfolio_path,
    position_notes_path,
    trades_path,
)

logger = get_logger(__name__)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("json unreadable path=%s err=%s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def load_latest_linkage() -> dict[str, Any]:
    return load_json(latest_linkage_path())


def load_linkage_by_run_id(run_id: str) -> dict[str, Any] | None:
    if not run_id:
        return None
    latest = load_latest_linkage()
    if latest.get("run_id") == run_id:
        return latest
    for path in sorted(linkage_dir().glob(f"*_{run_id}.json"), reverse=True):
        return load_json(path)
    return None


def empty_portfolio_dict() -> dict[str, Any]:
    cash = float(settings.paper_initial_cash)
    return {
        "cash": cash,
        "initial_cash": cash,
        "positions": {},
        "updated_at": datetime.now().isoformat(),
        "high_water_mark": cash,
    }


def load_portfolio_raw() -> dict[str, Any]:
    raw = load_json(portfolio_path())
    if not raw:
        return empty_portfolio_dict()
    return raw


def load_trades(limit: int | None = None) -> list[dict[str, Any]]:
    path = trades_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if limit is not None:
        return rows[-limit:]
    return rows


def load_position_notes() -> dict[str, str]:
    raw = load_json(position_notes_path())
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items()}


def save_position_notes(notes: dict[str, str]) -> None:
    path = position_notes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps(notes, ensure_ascii=False, indent=2))


def load_equity_history(limit: int = 60) -> list[dict[str, Any]]:
    path = equity_history_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows[-limit:]


def list_linkage_runs(limit: int = 40) -> list[dict[str, Any]]:
    root = linkage_dir()
    if not root.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"), reverse=True):
        if path.name == "latest.json":
            continue
        data = load_json(path)
        if not data:
            continue
        runs.append(
            {
                "run_id": str(data.get("run_id") or path.stem),
                "timestamp": str(data.get("timestamp") or ""),
                "path": path.name,
            }
        )
        if len(runs) >= limit:
            break
    return runs


def all_decision_items(linkage: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key, tab in (
        ("etf_runs", "etf"),
        ("hold_runs", "hold"),
        ("stock_runs", "stock"),
    ):
        for row in linkage.get(key) or []:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            item.setdefault("tab", tab)
            item.setdefault("symbol", str(row.get("symbol") or "").zfill(6))
            items.append(item)
    return items


def pick_name_map(linkage: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for p in ((linkage.get("stock_pick") or {}).get("picks") or []):
        if isinstance(p, dict) and p.get("symbol"):
            names[str(p["symbol"]).zfill(6)] = str(p.get("name") or "")
    for item in all_decision_items(linkage):
        sym = str(item.get("symbol") or "").zfill(6)
        if sym and item.get("name"):
            names.setdefault(sym, str(item["name"]))
    return names


def parse_iso(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
