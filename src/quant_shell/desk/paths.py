"""Desk 数据路径 — 一律相对 project_root()/data。"""
from __future__ import annotations

from pathlib import Path

from quant_shell.config.env_loader import project_root


def data_dir() -> Path:
    return project_root() / "data"


def paper_dir() -> Path:
    return data_dir() / "paper"


def linkage_dir() -> Path:
    return data_dir() / "linkage"


def desk_dir() -> Path:
    return data_dir() / "desk"


def jobs_dir() -> Path:
    return desk_dir() / "jobs"


def portfolio_path() -> Path:
    return paper_dir() / "portfolio.json"


def trades_path() -> Path:
    return paper_dir() / "trades.jsonl"


def equity_history_path() -> Path:
    return paper_dir() / "equity_history.jsonl"


def position_notes_path() -> Path:
    return paper_dir() / "position_notes.json"


def latest_linkage_path() -> Path:
    return linkage_dir() / "latest.json"


def factor_audit_path() -> Path:
    return desk_dir() / "factor_audit.jsonl"
