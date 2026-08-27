"""L7 LLM 响应解析 — 软旗 only；硬码一律剥离。"""
from __future__ import annotations

from quant_shell.common.types import AIDecision, Action
from quant_shell.common.hard_codes import strip_hard_codes

_VALID_ACTIONS = {a.value for a in Action}


def parse_llm_decision(
    raw: dict[str, object],
    *,
    fallback: AIDecision | None = None,
) -> AIDecision:
    """将 DeepSeek JSON 转为软叙述 AIDecision。

    非法 action 回落 fallback；硬码从 risk_flags 剥离（不得由 LLM 发明）。
    """
    action_str = str(raw.get("action", "")).upper()
    invalid_action = action_str not in _VALID_ACTIONS
    if invalid_action:
        if fallback is not None:
            return AIDecision(
                action=fallback.action,
                confidence=fallback.confidence,
                reasoning_chain=[
                    *fallback.reasoning_chain,
                    f"LLM 非法 action={action_str!r}，回落叙述",
                ],
                risk_flags=[
                    *strip_hard_codes(list(fallback.risk_flags)),
                    "LLM_INVALID_ACTION",
                ],
                suggested_position_change=0.0,
                human_review_required=True,
            )
        action_str = Action.HOLD.value

    chain_raw = raw.get("reasoning_chain", [])
    chain = [str(item) for item in chain_raw] if isinstance(chain_raw, list) else [str(chain_raw)]

    flags_raw = raw.get("risk_flags", [])
    flags = [str(item) for item in flags_raw] if isinstance(flags_raw, list) else []
    flags = strip_hard_codes(flags)
    if invalid_action:
        flags.append("LLM_INVALID_ACTION")

    soft_fallback = strip_hard_codes(list(fallback.risk_flags)) if fallback else []
    for f in soft_fallback:
        if f not in flags:
            flags.append(f)

    confidence = _clamp_float(raw.get("confidence"), 0.0, 1.0)
    human_review = bool(raw.get("human_review_required", False)) or invalid_action
    if fallback is not None:
        human_review = human_review or fallback.human_review_required

    return AIDecision(
        action=Action(action_str),
        confidence=confidence,
        reasoning_chain=chain or ["LLM 未提供推理链"],
        risk_flags=flags,
        suggested_position_change=0.0,
        human_review_required=human_review,
    )


def _clamp_float(value: object, low: float, high: float) -> float:
    if value is None:
        return low
    if isinstance(value, bool):
        return low
    if isinstance(value, (int, float)):
        return max(low, min(high, float(value)))
    if isinstance(value, str):
        try:
            num = float(value.strip())
        except ValueError:
            return low
        return max(low, min(high, num))
    return low
