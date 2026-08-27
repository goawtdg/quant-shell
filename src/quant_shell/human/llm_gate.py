"""L7 DeepSeek 叙述门 — 无 Key 时降级 Sim；成交由 commit_decision 定稿。"""
from __future__ import annotations

from quant_shell.common.exceptions import DataFetchError
from quant_shell.common.interfaces import HumanReviewGate
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import AIDecision, DecisionContextPack
from quant_shell.config.settings import settings
from quant_shell.execution.portfolio import PaperPortfolioStore
from quant_shell.human.parser import parse_llm_decision
from quant_shell.human.prompt import build_decision_messages
from quant_shell.human.sim_gate import SimHumanReviewGate

logger = get_logger(__name__)


def _chat_json(messages: list[dict[str, str]]) -> dict[str, object]:
    try:
        from quant_shell.intelligence.analyst.deepseek_client import chat_json
    except ImportError as exc:
        raise DataFetchError(
            message="DeepSeek 客户端未安装",
            suggestion="pip install quant-shell[intel] 或配置可选 intel 包",
        ) from exc
    return chat_json(messages)


class LlmHumanReviewGate(HumanReviewGate):
    """DeepSeek 结构化软叙述；失败或无 Key 时走 Sim。"""

    def __init__(
        self,
        fallback: HumanReviewGate | None = None,
        portfolio_store: PaperPortfolioStore | None = None,
    ) -> None:
        self._fallback = fallback or SimHumanReviewGate()
        self._portfolio_store = portfolio_store or PaperPortfolioStore()

    def reason(self, pack: DecisionContextPack) -> AIDecision:
        """只产软叙述；action 会被 commit 丢弃。"""
        pre = self._fallback.reason(pack)
        if not settings.has_deepseek:
            logger.info("LlmHumanReviewGate fallback: no deepseek key")
            return pre

        try:
            messages = build_decision_messages(pack)
            raw = _chat_json(messages)
            decision = parse_llm_decision(raw, fallback=pre)
            logger.info(
                "LlmHumanReviewGate symbol=%s narrate_action=%s conf=%.2f soft_flags=%s",
                pack.symbol,
                decision.action.value,
                decision.confidence,
                decision.risk_flags,
            )
            return decision
        except (DataFetchError, ValueError, KeyError) as exc:
            logger.warning("LlmHumanReviewGate narrative fail: %s", exc)
            return AIDecision(
                action=pre.action,
                confidence=pre.confidence,
                reasoning_chain=[
                    *pre.reasoning_chain,
                    f"LLM 叙述失败回落 Sim：{exc}",
                ],
                risk_flags=[*pre.risk_flags, "LLM_NARRATIVE_FAIL"],
                suggested_position_change=0.0,
                human_review_required=True,
            )

    def confirm(self, decision: AIDecision, auto_approve: bool = False) -> bool:
        return self._fallback.confirm(decision, auto_approve=auto_approve)


def build_default_human_gate(
    portfolio_store: object | None = None,
) -> HumanReviewGate:
    """有 DeepSeek Key 时用 LLM 叙述门，否则 Sim。"""
    store = (
        portfolio_store
        if isinstance(portfolio_store, PaperPortfolioStore)
        else PaperPortfolioStore()
    )
    sim = SimHumanReviewGate()
    if settings.has_deepseek:
        return LlmHumanReviewGate(fallback=sim, portfolio_store=store)
    return sim
