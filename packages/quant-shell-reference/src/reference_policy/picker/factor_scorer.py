"""截面多因子打分 — Sprint B 核心。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from quant_shell.common.exceptions import DataFetchError, ValidationError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import ScoredStock, StockPickResult
from quant_shell.data.stock_client import fetch_stock_daily_ohlcv
from quant_shell.signals.adapter import cross_section_adapt_dataframe
from quant_shell.factors.batch import compute_alpha_raws
from quant_shell.factors.registry import FactorRegistry
from quant_shell.factors.state_store import load_registry
from reference_policy.picker.constants import (
    STRATEGY_MULTI_FACTOR,
    WEIGHT_ALPHA_FACTORS,
    WEIGHT_FUNDAMENTAL,
    WEIGHT_INDUSTRY_REL_MOM,
    WEIGHT_LIQUIDITY,
    WEIGHT_MOMENTUM_3M,
    WEIGHT_QUALITY,
    WEIGHT_VALUE,
)
from reference_policy.policy.config import load_policy_config
from reference_policy.policy.playbooks import assess_pick_entry_eligibility
from reference_policy.picker.universe_filter import apply_universe_gates, summarize_universe_gates

logger = get_logger(__name__)

FUNDAMENTAL_COLS: tuple[str, ...] = (
    "value_ep",
    "quality_roe",
    "momentum_3m",
    "industry_rel_momentum",
    "liquidity",
)
FUNDAMENTAL_WEIGHTS: dict[str, float] = {
    "value_ep": WEIGHT_VALUE,
    "quality_roe": WEIGHT_QUALITY,
    "momentum_3m": WEIGHT_MOMENTUM_3M,
    "industry_rel_momentum": WEIGHT_INDUSTRY_REL_MOM,
    "liquidity": WEIGHT_LIQUIDITY,
}
INVERT_COLS: set[str] = set()


class FactorScorer:
    """截面 rank 多因子合成打分。"""

    def __init__(self, registry: FactorRegistry | None = None) -> None:
        self._registry = registry or load_registry(scope="stock")

    def score(
        self,
        universe: str,
        frame: pd.DataFrame,
        top_n: int,
    ) -> StockPickResult:
        """对候选池打分并返回 Top N。

        Args:
            universe: 指数池名称。
            frame: L1 基本面 DataFrame。
            top_n: 输出数量。

        Returns:
            StockPickResult。
        """
        candidate_count = len(frame)
        filtered = apply_universe_gates(frame)
        if filtered.empty:
            logger.warning("score universe=%s no candidates after gates", universe)
            return StockPickResult(
                universe=universe,
                strategy=STRATEGY_MULTI_FACTOR,
                picks=[],
                candidate_count=candidate_count,
                filtered_count=0,
                gate_diagnostics=summarize_universe_gates(frame),
                timestamp=datetime.now(),
            )

        alpha_frame = self._build_alpha_frame(filtered["symbol"].tolist())
        fund_frame = self._build_fundamental_frame(filtered)
        combined = pd.concat([alpha_frame, fund_frame], axis=1).fillna(0.0)
        industry_map = self._industry_map(filtered)
        adapted = cross_section_adapt_dataframe(
            combined,
            invert_cols=INVERT_COLS,
            industries=industry_map,
            industry_neutral=True,
        )

        alpha_cols = [c for c in alpha_frame.columns if c in adapted.columns]
        fund_cols = [c for c in FUNDAMENTAL_COLS if c in adapted.columns]

        alpha_composite = self._weighted_row_mean(adapted[alpha_cols], self._alpha_weights(alpha_cols))
        fund_composite = self._weighted_row_mean(adapted[fund_cols], FUNDAMENTAL_WEIGHTS)

        total = (
            WEIGHT_ALPHA_FACTORS * alpha_composite
            + WEIGHT_FUNDAMENTAL * fund_composite
        )
        ranking = total.sort_values(ascending=False).head(top_n)

        picks: list[ScoredStock] = []
        name_map = dict(zip(filtered["symbol"], filtered.get("name", filtered["symbol"])))
        if "price" in filtered.columns:
            price_map = dict(zip(filtered["symbol"], filtered["price"]))
        else:
            price_map = {str(sym): 0.0 for sym in filtered["symbol"]}
        for rank_idx, (symbol, score) in enumerate(ranking.items(), start=1):
            factor_scores = {
                col: float(adapted.loc[symbol, col])
                for col in adapted.columns
                if symbol in adapted.index
            }
            row = filtered.loc[filtered["symbol"] == symbol].iloc[0]
            eligible, block_reason = assess_pick_entry_eligibility(
                row, load_policy_config()
            )
            picks.append(
                ScoredStock(
                    symbol=str(symbol),
                    name=str(name_map.get(symbol, symbol)),
                    score=float(score),
                    rank=rank_idx,
                    price=float(price_map.get(symbol, 0) or 0),
                    factor_scores=factor_scores,
                    entry_eligible=eligible,
                    entry_block_reason=block_reason,
                )
            )

        logger.info(
            "FactorScorer universe=%s candidates=%d filtered=%d picks=%d",
            universe,
            candidate_count,
            len(filtered),
            len(picks),
        )
        return StockPickResult(
            universe=universe,
            strategy=STRATEGY_MULTI_FACTOR,
            picks=picks,
            candidate_count=candidate_count,
            filtered_count=len(filtered),
            timestamp=datetime.now(),
        )

    def _build_alpha_frame(self, symbols: list[str]) -> pd.DataFrame:
        """批量计算 alpha 原始值矩阵。"""
        rows: dict[str, dict[str, float]] = {}
        for symbol in symbols:
            try:
                ohlcv = fetch_stock_daily_ohlcv(symbol)
                rows[symbol] = compute_alpha_raws(ohlcv, self._registry)
            except (DataFetchError, ValidationError, OSError, TypeError, ValueError, KeyError) as exc:
                logger.warning("alpha skip symbol=%s err=%s", symbol, exc)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).T

    def _build_fundamental_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        """从基本面表构建因子原始值。"""
        working = frame.set_index("symbol")
        pe_positive = working["pe"].where(working["pe"] > 0)
        ep = 1.0 / pe_positive
        ep_median = float(ep.median() or 0.05)
        fund = pd.DataFrame(index=working.index)
        fund["value_ep"] = ep.fillna(ep_median)
        fund["quality_roe"] = working["roe"]
        fund["momentum_3m"] = working["return_3m"]
        if "industry" in working.columns:
            ind_median = working.groupby("industry")["return_3m"].transform("median")
            fund["industry_rel_momentum"] = working["return_3m"] - ind_median
        else:
            fund["industry_rel_momentum"] = 0.0
        if "turnover_rate" in working.columns:
            fund["liquidity"] = working["turnover_rate"].where(
                working["turnover_rate"] > 0,
                working["volume"] / working["volume_ma20"].replace(0, 1),
            )
        else:
            fund["liquidity"] = working["volume"] / working["volume_ma20"].replace(0, 1)
        return fund

    @staticmethod
    def _industry_map(frame: pd.DataFrame) -> dict[str, str]:
        """symbol -> 行业名称。"""
        if "industry" not in frame.columns:
            return {}
        return {
            str(row["symbol"]): str(row["industry"])
            for _, row in frame.iterrows()
            if str(row.get("industry", "")).strip()
        }

    def _alpha_weights(self, columns: list[str]) -> dict[str, float]:
        """从注册表取 alpha 列有效权重（含 DEGRADED 半权）。"""
        spec_map = {spec.name: spec for spec in self._registry.all_specs()}
        return {
            col: self._registry.effective_weight(spec_map[col])
            for col in columns
            if col in spec_map
        }

    @staticmethod
    def _weighted_row_mean(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
        """按列权重求行均值。"""
        if frame.empty:
            return pd.Series(dtype=float)
        total_weight = sum(weights.get(col, 0.0) for col in frame.columns)
        if total_weight == 0:
            return frame.mean(axis=1)
        weighted = sum(frame[col] * weights.get(col, 0.0) for col in frame.columns)
        return weighted / total_weight
