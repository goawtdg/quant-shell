"""L6 执行层常量。"""
from __future__ import annotations

from pathlib import Path
from typing import Final

LOT_SIZE: Final[int] = 100

PAPER_DATA_DIR: Final[Path] = Path("data/paper")
PORTFOLIO_FILENAME: Final[str] = "portfolio.json"
TRADES_FILENAME: Final[str] = "trades.jsonl"

EXECUTION_STATUS_FILLED: Final[str] = "filled"
EXECUTION_STATUS_SKIPPED: Final[str] = "skipped"
EXECUTION_STATUS_DISABLED: Final[str] = "disabled"
