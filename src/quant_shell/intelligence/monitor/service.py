"""定时情报监控 — 采集 + 唯一 fusion 工厂 + 持久化（不触发交易）。"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from quant_shell.common.atomic_io import write_text_atomic
from quant_shell.common.logging_config import get_logger
from quant_shell.common.types import MarketSnapshot, MonitorAlert, SentimentFactors
from quant_shell.data.constants import SYMBOL_TO_INDEX_NAME
from quant_shell.config.env_loader import project_root
from quant_shell.intelligence.collector import IntelligenceCollector
from quant_shell.intelligence.deepseek_fusion import build_default_intelligence_fusion
from quant_shell.intelligence.monitor.serializer import sentiment_to_dict
from quant_shell.intelligence.osint_fusion import OsintIntelligenceFusion

logger = get_logger(__name__)


def _default_monitor_dir() -> Path:
    return project_root() / "data" / "monitor"


@dataclass
class MonitorRunResult:
    """单次监控运行结果。"""

    run_id: str
    timestamp: datetime
    symbols: list[str]
    results: dict[str, SentimentFactors]
    alerts: list[MonitorAlert] = field(default_factory=list)
    intel_source_failures: list[dict[str, str]] = field(default_factory=list)
    latest_path: Path | None = None
    archive_path: Path | None = None


class IntelligenceMonitor:
    """定时 OSINT + DeepSeek 监控（只读，不下单）。"""

    def __init__(
        self,
        symbols: list[str] | None = None,
        *,
        output_dir: Path | None = None,
        fusion: OsintIntelligenceFusion | None = None,
        collector: IntelligenceCollector | None = None,
    ) -> None:
        self._symbols = symbols or ["510300"]
        self._output_dir = output_dir or _default_monitor_dir()
        self._collector = collector or IntelligenceCollector()
        self._fusion = fusion or build_default_intelligence_fusion(
            collector=self._collector
        )
        if getattr(self._fusion, "_collector", None) is None:
            self._fusion._collector = self._collector  # noqa: SLF001 — 共享采集器
        else:
            self._collector = self._fusion._collector  # noqa: SLF001

    def run_once(self) -> MonitorRunResult:
        """执行一轮监控：市场源一次 → 按标的补个股新闻 → 分析 → 保存。"""
        run_id = str(uuid.uuid4())[:8]
        now = datetime.now()
        results: dict[str, SentimentFactors] = {}
        alerts: list[MonitorAlert] = []
        self._collector.source_failures = []

        global_items = self._collector.collect_global()
        self._fusion.set_global_items(global_items)

        for symbol in self._symbols:
            result = self._analyze_symbol(symbol)
            results[symbol] = result
            alerts.extend(_collect_alerts(symbol, result))

        failures = list(self._collector.source_failures)
        latest_path, archive_path = self._persist(
            run_id, now, results, alerts, failures
        )
        logger.info(
            "IntelligenceMonitor run_id=%s symbols=%s alerts=%d failures=%d path=%s",
            run_id,
            self._symbols,
            len(alerts),
            len(failures),
            latest_path,
        )
        return MonitorRunResult(
            run_id=run_id,
            timestamp=now,
            symbols=list(self._symbols),
            results=results,
            alerts=alerts,
            intel_source_failures=failures,
            latest_path=latest_path,
            archive_path=archive_path,
        )

    def _analyze_symbol(self, symbol: str) -> SentimentFactors:
        """单标的分析（复用已注入的 global items）。"""
        market = MarketSnapshot(
            symbol=symbol,
            timestamp=datetime.now(),
            price=0.0,
            extra={"index_name": SYMBOL_TO_INDEX_NAME.get(symbol, "")},
        )
        return self._fusion.analyze(symbol, market)

    def _persist(
        self,
        run_id: str,
        timestamp: datetime,
        results: dict[str, SentimentFactors],
        alerts: list[MonitorAlert],
        source_failures: list[dict[str, str]],
    ) -> tuple[Path, Path]:
        """写入 latest.json 与归档。"""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        runs_dir = self._output_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "run_id": run_id,
            "timestamp": timestamp.isoformat(),
            "mode": "monitor_only",
            "trade_execution": False,
            "symbols": self._symbols,
            "intel_source_failures": source_failures,
            "alerts": [
                {"symbol": a.symbol, "level": a.level, "message": a.message}
                for a in alerts
            ],
            "results": {sym: sentiment_to_dict(res) for sym, res in results.items()},
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        latest_path = self._output_dir / "latest.json"
        archive_path = runs_dir / f"{timestamp:%Y%m%d_%H%M%S}_{run_id}.json"
        write_text_atomic(latest_path, text)
        write_text_atomic(archive_path, text)
        return latest_path, archive_path


def _collect_alerts(symbol: str, result: SentimentFactors) -> list[MonitorAlert]:
    """从分析结果提取人工关注项。"""
    alerts: list[MonitorAlert] = []
    report = result.analyst_report
    if report is None:
        return alerts

    if report.human_review_required:
        alerts.append(
            MonitorAlert(
                symbol=symbol,
                level="REVIEW",
                message=report.executive_summary[:200] or "需人工复核",
            )
        )
    if report.novelty == "black_swan":
        alerts.append(
            MonitorAlert(
                symbol=symbol,
                level="CRITICAL",
                message=f"黑天鹅信号: {report.executive_summary[:160]}",
            )
        )
    if report.recommended_action in ("REDUCE", "HUMAN_ONLY"):
        alerts.append(
            MonitorAlert(
                symbol=symbol,
                level="ACTION",
                message=f"建议动作 {report.recommended_action}: {report.executive_summary[:160]}",
            )
        )
    return alerts


def format_run_summary(run: MonitorRunResult) -> str:
    """人类可读摘要。"""
    lines = [
        f"=== 情报监控 {run.timestamp:%Y-%m-%d %H:%M:%S} run={run.run_id} ===",
        "模式: 仅监控分析，不自动交易",
    ]
    for symbol, result in run.results.items():
        report = result.analyst_report
        action = report.recommended_action if report else "-"
        conf = report.confidence if report else 0.0
        lines.append(
            f"[{symbol}] composite={result.composite:+.3f} "
            f"cross={result.cross_validation:.2f} action={action} conf={conf:.2f}"
        )
        if report:
            lines.append(f"  摘要: {report.executive_summary[:120]}")
    if run.intel_source_failures:
        lines.append("--- 源失败 ---")
        for fail in run.intel_source_failures:
            lines.append(f"  {fail.get('source')}: {fail.get('error')}")
    if run.alerts:
        lines.append("--- 需关注 ---")
        for alert in run.alerts:
            lines.append(f"  [{alert.level}] {alert.symbol}: {alert.message[:100]}")
    if run.latest_path:
        lines.append(f"已保存: {run.latest_path}")
    return "\n".join(lines)
