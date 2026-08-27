"""DeepSeek 威胁情报分析师 Prompt。"""
from __future__ import annotations

import json

from quant_shell.common.types import IntelligenceBrief, MarketSnapshot


def build_analyst_messages(
    brief: IntelligenceBrief,
    market: MarketSnapshot,
) -> list[dict[str, str]]:
    """构建 DeepSeek chat messages。"""
    payload = _brief_payload(brief, market)
    system = (
        "你是金融威胁情报分析师（Threat Intelligence Analyst），不是交易员。"
        "任务：基于多源开源情报（OSINT）做交叉验证，输出结构化 JSON 评估。"
        "原则："
        "1) 区分「已证实事实」与「推测」；"
        "2) 多源印证才提高置信度；单源或未印证事件降权、降低 confidence，"
        "recommended_action 默认 MONITOR，不必因此 human_review_required=true；"
        "3) 模板外/地缘黑天鹅/叙事冲击标记 novelty=black_swan 或 uncertain；"
        "4) 不得假装精确预测涨跌；sentiment_score 仅表示新闻面对该标的的倾向 [-1,1]；"
        "5) human_review_required=true / HUMAN_ONLY 仅用于：black_swan、高政策风险、"
        "明确减仓建议，或情报严重矛盾需人工裁决；一般单源不足不属于此类。"
    )
    user = (
        "请分析以下 OSINT 情报包，以威胁情报分析师视角输出 JSON（不要 markdown）：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "JSON 字段（必须全部包含）：\n"
        "{\n"
        '  "executive_summary": "3-5句高管摘要",\n'
        '  "facts": ["已证实事实1", "..."],\n'
        '  "affected_assets": ["可能受影响资产/板块"],\n'
        '  "transmission_chain": ["事件传导链步骤"],\n'
        '  "corroboration_assessment": "多源印证评估文字",\n'
        '  "confidence": 0.0-1.0,\n'
        '  "sentiment_score": -1.0-1.0,\n'
        '  "policy_risk_score": 0.0-1.0,\n'
        '  "novelty": "known|uncertain|black_swan",\n'
        '  "recommended_action": "MONITOR|REDUCE|HUMAN_ONLY|NEUTRAL|INCREASE",\n'
        '  "uncertainties": ["不确定点"],\n'
        '  "human_review_required": true/false\n'
        "}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _brief_payload(brief: IntelligenceBrief, market: MarketSnapshot) -> dict[str, object]:
    items = [
        {
            "source": item.source,
            "title": item.title,
            "content": item.content[:400],
            "published_at": item.published_at.isoformat(),
            "entities": item.entities,
            "event_tags": item.event_tags,
        }
        for item in brief.items[:20]
    ]
    return {
        "symbol": brief.symbol,
        "market": {
            "price": market.price,
            "pe_percentile": market.pe_percentile,
            "index_name": market.extra.get("index_name", ""),
        },
        "source_count": brief.source_count,
        "corroboration_groups": brief.corroboration_count,
        "items": items,
    }
