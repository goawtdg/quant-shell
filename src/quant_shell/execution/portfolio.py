"""读写 ``data/paper/portfolio.json`` 与成交日志。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from quant_shell.common.atomic_io import append_text, write_text_atomic
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import PaperPortfolio, PaperPosition
from quant_shell.config.settings import settings
from quant_shell.execution.constants import (
    PAPER_DATA_DIR,
    PORTFOLIO_FILENAME,
    TRADES_FILENAME,
)

logger = get_logger(__name__)


class PaperPortfolioStore:
    """读写模拟盘账户与成交日志。"""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir or PAPER_DATA_DIR
        self._portfolio_path = self._base_dir / PORTFOLIO_FILENAME
        self._trades_path = self._base_dir / TRADES_FILENAME

    @property
    def portfolio_path(self) -> Path:
        return self._portfolio_path

    def load(self) -> PaperPortfolio:
        """加载账户；不存在则按初始资金创建。缺 sleeve/opened_at 显式失败。"""
        if not self._portfolio_path.exists():
            return self._new_portfolio()
        try:
            raw = json.loads(self._portfolio_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"portfolio.json 损坏（可能写入中断）: {self._portfolio_path}: {exc}"
            ) from exc
        updated = datetime.fromisoformat(raw["updated_at"])
        positions: dict[str, PaperPosition] = {}
        for sym, item in raw.get("positions", {}).items():
            if "sleeve" not in item or not str(item.get("sleeve") or "").strip():
                raise ValueError(
                    f"portfolio 持仓 {sym} 缺少 sleeve；请手工补全合法袖套后重载"
                )
            opened_raw = item.get("opened_at")
            if not opened_raw:
                raise ValueError(
                    f"portfolio 持仓 {sym} 缺少 opened_at；请手工补全后重载"
                )
            opened_at = datetime.fromisoformat(str(opened_raw))
            positions[sym] = PaperPosition(
                symbol=sym,
                quantity=float(item["quantity"]),
                avg_cost=float(item.get("avg_cost", 0.0)),
                opened_at=opened_at,
                peak_price=float(item.get("peak_price", 0.0) or 0.0),
                sleeve=str(item["sleeve"]).strip(),
            )
        return PaperPortfolio(
            cash=float(raw["cash"]),
            initial_cash=float(raw.get("initial_cash", settings.paper_initial_cash)),
            positions=positions,
            updated_at=updated,
            high_water_mark=float(raw.get("high_water_mark", raw.get("initial_cash", 0))),
        )

    def save(self, portfolio: PaperPortfolio) -> None:
        """持久化账户快照。"""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "cash": portfolio.cash,
            "initial_cash": portfolio.initial_cash,
            "updated_at": portfolio.updated_at.isoformat(),
            "high_water_mark": portfolio.high_water_mark,
            "positions": {
                sym: {
                    "quantity": pos.quantity,
                    "avg_cost": pos.avg_cost,
                    "opened_at": pos.opened_at.isoformat() if pos.opened_at else None,
                    "peak_price": pos.peak_price,
                    "sleeve": pos.sleeve,
                }
                for sym, pos in portfolio.positions.items()
            },
        }
        write_text_atomic(
            self._portfolio_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def append_trade(self, record: dict[str, object]) -> None:
        """追加一条成交记录到 jsonl。"""
        self._base_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False)
        append_text(self._trades_path, line)

    def reset(self) -> PaperPortfolio:
        """重置为初始资金。"""
        portfolio = self._new_portfolio()
        self.save(portfolio)
        logger.info("paper portfolio reset cash=%.2f", portfolio.cash)
        return portfolio

    def _new_portfolio(self) -> PaperPortfolio:
        cash = settings.paper_initial_cash
        return PaperPortfolio(
            cash=cash,
            initial_cash=cash,
            positions={},
            updated_at=datetime.now(),
            high_water_mark=cash,
        )
