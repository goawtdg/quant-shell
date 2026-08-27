"""把白话交易想法编译成 TradingModel。优先 DeepSeek，失败则用关键词规则。"""
from __future__ import annotations

import json
import re
from typing import Any

from quant_shell.studio.catalog import FACTOR_CATALOG, catalog_public
from quant_shell.studio.schema import TradingModel, empty_model, model_from_dict


_SYSTEM = """你是 A 股模拟盘交易模型编译器。用户用中文描述买卖想法。
你必须只输出一个 JSON 对象，字段严格如下：
{
  "name": "不超过12字的模型名",
  "summary": "用两句中文复述将如何开仓/风控",
  "symbol": "6位数字代码，默认510300",
  "factors": [{"id": "菜谱id", "enabled": true, "weight": 0.2}],
  "entry": {"moderate_threshold": 0.07, "strong_threshold": 0.10, "moderate_buy_scale": 0.5},
  "risk": {"max_drawdown": 0.15, "single_stock_limit": 0.10, "total_position_limit": 0.80},
  "notes": ["无法实现的部分，用中文说明"]
}
规则：
- factors.id 只能来自给定菜谱，不准发明新 id。
- 用户没提到的因子 enabled=false，提到的 enabled=true 并给合理权重（和约 1）。
- 阈值、回撤必须是 0~1 的小数（15% 写成 0.15）。
- 做不到的想法（例如高频、期权、跟庄、保证盈利）写入 notes，不要假装能做。
"""


def _pct_to_frac(text: str, keywords: tuple[str, ...], default: float) -> float:
    for key in keywords:
        m = re.search(rf"{key}[^\d%]{{0,8}}(\d+(?:\.\d+)?)\s*%", text)
        if m:
            return float(m.group(1)) / 100.0
    return default


def compile_heuristic(idea: str) -> TradingModel:
    """无 Key / LLM 失败时的关键词编译，保证页面总能给出可改卡片。"""
    text = (idea or "").strip()
    if not text:
        model = empty_model()
        model.notes = ["请先写一段交易想法，例如：追20日动量，回撤超过12%就别买。"]
        return model

    enabled: set[str] = set()
    if re.search(r"动量|追涨|趋势|惯性", text):
        enabled.add("momentum_20")
        if re.search(r"短|5日|一周", text):
            enabled.add("momentum_5")
    if re.search(r"低波|稳健|波动小|不爱折腾", text):
        enabled.add("low_vol")
    if re.search(r"放量|量能|成交量", text):
        enabled.add("volume_ratio")
    if re.search(r"均线|乖离|偏离", text):
        enabled.add("ma_deviation")
    if not enabled:
        enabled.add("momentum_20")

    n = max(1, len(enabled))
    w = round(1.0 / n, 2)
    factors = []
    for item in FACTOR_CATALOG:
        fid = str(item["id"])
        factors.append(
            {
                "id": fid,
                "enabled": fid in enabled,
                "weight": w if fid in enabled else float(item["default_weight"]),
            }
        )

    dd = _pct_to_frac(text, ("回撤", "止损", "最大亏损"), 0.15)
    if re.search(r"严|紧|保守", text) and "回撤" not in text:
        dd = min(dd, 0.12)

    moderate = 0.07
    if re.search(r"更容易买|松|多买", text):
        moderate = 0.05
    if re.search(r"更难买|严开仓|少买", text):
        moderate = 0.10

    raw: dict[str, Any] = {
        "name": "想法模型",
        "idea": text,
        "summary": f"按你的描述启用 { '、'.join(sorted(enabled)) }，组合回撤上限约 {dd:.0%}。",
        "symbol": "510300",
        "factors": factors,
        "entry": {
            "moderate_threshold": moderate,
            "strong_threshold": round(moderate + 0.03, 2),
            "moderate_buy_scale": 0.5,
        },
        "risk": {
            "max_drawdown": dd,
            "single_stock_limit": 0.10,
            "total_position_limit": 0.80,
        },
        "notes": [],
    }
    m = re.search(r"(\d{6})", text)
    if m:
        raw["symbol"] = m.group(1)
    model = model_from_dict(raw)
    model.idea = text
    return model


def _compile_llm(idea: str) -> TradingModel:
    from quant_shell.intelligence.analyst.deepseek_client import chat_json

    catalog = json.dumps(catalog_public(), ensure_ascii=False)
    messages = [
        {"role": "system", "content": _SYSTEM + "\n菜谱:\n" + catalog},
        {"role": "user", "content": idea.strip()},
    ]
    parsed = chat_json(messages)
    if not isinstance(parsed, dict):
        raise ValueError("compiler returned non-object")
    parsed["idea"] = idea.strip()
    return model_from_dict(parsed)


def compile_idea(idea: str) -> tuple[TradingModel, str]:
    """返回 (模型, 编译方式 llm|heuristic)。"""
    text = (idea or "").strip()
    if not text:
        return compile_heuristic(text), "heuristic"
    try:
        from quant_shell.config.settings import settings

        if settings.has_deepseek:
            return _compile_llm(text), "llm"
    except Exception:
        pass
    return compile_heuristic(text), "heuristic"
