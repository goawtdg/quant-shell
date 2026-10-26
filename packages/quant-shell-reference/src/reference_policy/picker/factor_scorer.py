"""截面选股：按行业相对 63 日收益从高到低取前 N。

名次不用手写因子权重。价值、ROE、换手不参与排序。
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from quant_shell.common.exceptions import ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import ScoredStock, StockPickResult
from quant_shell.factors.registry import FactorRegistry
from quant_shell.factors.state_store import load_registry
from reference_policy.picker.constants import STRATEGY_MULTI_FACTOR
from reference_policy.policy.config import load_policy_config
from reference_policy.policy.playbooks import assess_pick_entry_eligibility
from reference_policy.picker.universe_filter import apply_universe_gates, summarize_universe_gates

logger = get_logger(__name__)


def industry_relative_return(frame: pd.DataFrame) -> pd.Series:
    """63 日收益减去同行业中位数。没有行业列时就是收益本身。"""
    if "symbol" not in frame.columns or "return_3m" not in frame.columns:
        raise ValidationError(
            message="选股表缺少 symbol 或 return_3m",
            suggestion="检查 build_universe_frame 的列",
        )
    working = frame.set_index("symbol")
    ret = pd.to_numeric(working["return_3m"], errors="coerce")
    if int(ret.notna().sum()) < 1:
        raise ValidationError(
            message="return_3m 全部缺失，无法排序",
            suggestion="检查日 K 长度是否覆盖 63 个交易日",
        )
    if "industry" not in working.columns:
        return ret
    industry = working["industry"].fillna("未知").astype(str)
    return ret - ret.groupby(industry).transform("median")


class FactorScorer:
    """按行业相对 63 日收益排序。"""

    def __init__(self, registry: FactorRegistry | None = None) -> None:
        self._registry = registry or load_registry(scope="stock")

    def score(
        self,
        universe: str,
        frame: pd.DataFrame,
        top_n: int,
    ) -> StockPickResult:
        """硬过滤之后，按行业相对收益取前 N。收益缺失的股票不进入名次。"""
        candidate_count = len(frame)
        filtered = apply_universe_gates(frame)
        diagnostics = summarize_universe_gates(frame)
        if filtered.empty:
            logger.warning("score universe=%s no candidates after gates", universe)
            return StockPickResult(
                universe=universe,
                strategy=STRATEGY_MULTI_FACTOR,
                picks=[],
                candidate_count=candidate_count,
                filtered_count=0,
                gate_diagnostics=diagnostics,
                timestamp=datetime.now(),
            )

        relative = industry_relative_return(filtered)
        missing = int(relative.isna().sum())
        diagnostics = {**diagnostics, "missing_return_3m": missing}
        ranking = relative.dropna().sort_values(ascending=False).head(top_n)
        raw_return = pd.to_numeric(filtered.set_index("symbol")["return_3m"], errors="coerce")

        picks: list[ScoredStock] = []
        name_map = dict(zip(filtered["symbol"], filtered.get("name", filtered["symbol"])))
        if "price" in filtered.columns:
            price_map = dict(zip(filtered["symbol"], filtered["price"]))
        else:
            price_map = {str(sym): 0.0 for sym in filtered["symbol"]}
        for rank_idx, (symbol, score) in enumerate(ranking.items(), start=1):
            row = filtered.loc[filtered["symbol"] == symbol].iloc[0]
            eligible, block_reason = assess_pick_entry_eligibility(row, load_policy_config())
            picks.append(
                ScoredStock(
                    symbol=str(symbol),
                    name=str(name_map.get(symbol, symbol)),
                    score=float(score),
                    rank=rank_idx,
                    price=float(price_map.get(symbol, 0) or 0),
                    factor_scores={
                        "return_3m": float(raw_return.loc[symbol]),
                        "industry_rel_momentum": float(score),
                    },
                    entry_eligible=eligible,
                    entry_block_reason=block_reason,
                )
            )

        logger.info(
            "FactorScorer universe=%s candidates=%d filtered=%d ranked=%d missing_return=%d",
            universe,
            candidate_count,
            len(filtered),
            len(picks),
            missing,
        )
        return StockPickResult(
            universe=universe,
            strategy=STRATEGY_MULTI_FACTOR,
            picks=picks,
            candidate_count=candidate_count,
            filtered_count=len(filtered),
            gate_diagnostics=diagnostics,
            timestamp=datetime.now(),
        )
