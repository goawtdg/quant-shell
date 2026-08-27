"""情报监控快照序列化。"""
from __future__ import annotations

from datetime import datetime

from quant_shell.common.types import AnalystReport, IntelligenceBrief, SentimentFactors


def sentiment_to_dict(result: SentimentFactors) -> dict[str, object]:
    """SentimentFactors → JSON 可序列化 dict。"""
    payload: dict[str, object] = {
        "symbol": result.symbol,
        "timestamp": result.timestamp.isoformat(),
        "nlp_score": result.nlp_score,
        "social_buzz": result.social_buzz,
        "policy_risk": result.policy_risk,
        "fund_sentiment": result.fund_sentiment,
        "composite": result.composite,
        "cross_validation": result.cross_validation,
        "key_events": result.key_events,
    }
    if result.intelligence_brief is not None:
        payload["brief"] = brief_to_dict(result.intelligence_brief)
    if result.analyst_report is not None:
        payload["analyst_report"] = analyst_to_dict(result.analyst_report)
    return payload


def brief_to_dict(brief: IntelligenceBrief) -> dict[str, object]:
    """IntelligenceBrief 摘要。"""
    return {
        "symbol": brief.symbol,
        "timestamp": brief.timestamp.isoformat(),
        "source_count": brief.source_count,
        "corroboration_count": brief.corroboration_count,
        "headline": brief.headline,
        "items": [
            {
                "source": item.source,
                "title": item.title,
                "published_at": item.published_at.isoformat(),
                "event_tags": item.event_tags,
            }
            for item in brief.items[:15]
        ],
    }


def dict_to_sentiment(payload: dict[str, object]) -> SentimentFactors:
    """JSON dict → SentimentFactors（P6 历史快照回放）。"""
    from datetime import datetime as dt

    from quant_shell.common.types import IntelligenceItem

    ts_raw = payload.get("timestamp")
    ts = dt.fromisoformat(str(ts_raw)) if ts_raw else dt.now()
    brief = None
    raw_brief = payload.get("brief")
    if isinstance(raw_brief, dict):
        items = []
        for item in raw_brief.get("items") or []:
            if not isinstance(item, dict):
                continue
            pub = item.get("published_at")
            items.append(
                IntelligenceItem(
                    item_id=str(item.get("item_id") or f"{payload.get('symbol')}-{len(items)}"),
                    source=str(item.get("source") or ""),
                    source_tier=int(item.get("source_tier") or 2),
                    title=str(item.get("title") or ""),
                    content=str(item.get("content") or item.get("title") or ""),
                    published_at=dt.fromisoformat(str(pub)) if pub else ts,
                    event_tags=list(item.get("event_tags") or []),
                )
            )
        brief = IntelligenceBrief(
            symbol=str(raw_brief.get("symbol") or payload.get("symbol") or ""),
            timestamp=dt.fromisoformat(str(raw_brief.get("timestamp")))
            if raw_brief.get("timestamp")
            else ts,
            items=items,
            source_count=int(raw_brief.get("source_count") or 0),
            corroboration_count=int(raw_brief.get("corroboration_count") or 0),
            headline=str(raw_brief.get("headline") or ""),
        )
    analyst = None
    raw_analyst = payload.get("analyst_report")
    if isinstance(raw_analyst, dict):
        analyst = AnalystReport(
            symbol=str(raw_analyst.get("symbol") or payload.get("symbol") or ""),
            timestamp=dt.fromisoformat(str(raw_analyst.get("timestamp")))
            if raw_analyst.get("timestamp")
            else ts,
            executive_summary=str(raw_analyst.get("executive_summary") or ""),
            facts=list(raw_analyst.get("facts") or []),
            affected_assets=list(raw_analyst.get("affected_assets") or []),
            transmission_chain=list(raw_analyst.get("transmission_chain") or []),
            corroboration_assessment=str(raw_analyst.get("corroboration_assessment") or ""),
            confidence=float(raw_analyst.get("confidence") or 0.0),
            sentiment_score=float(raw_analyst.get("sentiment_score") or 0.0),
            policy_risk_score=float(raw_analyst.get("policy_risk_score") or 0.0),
            novelty=str(raw_analyst.get("novelty") or ""),
            recommended_action=str(raw_analyst.get("recommended_action") or ""),
            uncertainties=list(raw_analyst.get("uncertainties") or []),
            human_review_required=bool(raw_analyst.get("human_review_required")),
        )
    return SentimentFactors(
        symbol=str(payload.get("symbol") or "").zfill(6),
        timestamp=ts,
        nlp_score=float(payload.get("nlp_score") or 0.0),
        social_buzz=float(payload.get("social_buzz") or 0.0),
        policy_risk=float(payload.get("policy_risk") or 0.0),
        fund_sentiment=float(payload.get("fund_sentiment") or 0.0),
        composite=float(payload.get("composite") or 0.0),
        cross_validation=float(payload.get("cross_validation") or 0.5),
        key_events=list(payload.get("key_events") or []),
        intelligence_brief=brief,
        analyst_report=analyst,
    )


def analyst_to_dict(report: AnalystReport) -> dict[str, object]:
    """AnalystReport 完整字段。"""
    return {
        "symbol": report.symbol,
        "timestamp": report.timestamp.isoformat(),
        "executive_summary": report.executive_summary,
        "facts": report.facts,
        "affected_assets": report.affected_assets,
        "transmission_chain": report.transmission_chain,
        "corroboration_assessment": report.corroboration_assessment,
        "confidence": report.confidence,
        "sentiment_score": report.sentiment_score,
        "policy_risk_score": report.policy_risk_score,
        "novelty": report.novelty,
        "recommended_action": report.recommended_action,
        "uncertainties": report.uncertainties,
        "human_review_required": report.human_review_required,
    }
