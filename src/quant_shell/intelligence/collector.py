"""多源情报采集编排 — 源级并行；市场源每轮只采一次。"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from quant_shell.common import audit
from quant_shell.common.exceptions import DataFetchError
from quant_shell.common.logging_config import get_logger
from quant_shell.common.retry import call_with_retry
from quant_shell.common.types import IntelligenceItem
from quant_shell.intelligence.deduper import dedupe_items
from quant_shell.intelligence.sources import build_sources
from quant_shell.intelligence.sources.base import IntelligenceSource
from quant_shell.intelligence.tagger import tag_items

logger = get_logger(__name__)

_global_items_cache: list[IntelligenceItem] | None = None
_global_cache_mono: float = 0.0
_global_cache_lock = threading.Lock()


def clear_global_intel_cache() -> None:
    """清空市场源会话缓存（每轮联动开始时调用）。"""
    global _global_items_cache, _global_cache_mono
    with _global_cache_lock:
        _global_items_cache = None
        _global_cache_mono = 0.0


class IntelligenceCollector:
    """并行调度各 OSINT 源，汇总去重后的 IntelligenceItem。"""

    def __init__(self, sources: list[IntelligenceSource] | None = None) -> None:
        self._sources = sources or build_sources()
        self.source_failures: list[dict[str, str]] = []

    def collect_global(self) -> list[IntelligenceItem]:
        """只采市场级源；结果写入会话缓存，同轮可复用。"""
        global _global_items_cache, _global_cache_mono
        with _global_cache_lock:
            if _global_items_cache is not None and self._global_cache_fresh():
                logger.info(
                    "IntelligenceCollector global cache_hit items=%d",
                    len(_global_items_cache),
                )
                return list(_global_items_cache)

        global_sources = [s for s in self._sources if not s.is_symbol_scoped]
        items = self._finalize(self._fetch_many(global_sources, ""))
        with _global_cache_lock:
            _global_items_cache = list(items)
            _global_cache_mono = time.monotonic()
        logger.info(
            "IntelligenceCollector global fetched sources=%d items=%d",
            len(global_sources),
            len(items),
        )
        return list(items)

    def collect_symbol(self, symbol: str) -> list[IntelligenceItem]:
        """只采依赖 symbol 的源（个股新闻）。"""
        if not symbol:
            return []
        scoped = [s for s in self._sources if s.is_symbol_scoped]
        return self._finalize(self._fetch_many(scoped, symbol))

    def collect_for_symbol(
        self,
        symbol: str,
        *,
        global_items: list[IntelligenceItem] | None = None,
    ) -> list[IntelligenceItem]:
        """市场源（传入或会话缓存）∪ 个股源。"""
        base = list(global_items) if global_items is not None else self.collect_global()
        scoped = self.collect_symbol(symbol)
        return self._finalize(base + scoped)

    def _fetch_many(
        self,
        sources: list[IntelligenceSource],
        symbol: str,
    ) -> list[IntelligenceItem]:
        if not sources:
            return []
        workers = self._workers(len(sources))
        if workers <= 1 or len(sources) == 1:
            raw: list[IntelligenceItem] = []
            for source in sources:
                raw.extend(self._fetch_safe(source, symbol))
            return raw

        raw = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(self._fetch_safe, source, symbol): source.name
                for source in sources
            }
            for fut in as_completed(futs):
                raw.extend(fut.result())
        return raw

    def _finalize(self, raw_items: list[IntelligenceItem]) -> list[IntelligenceItem]:
        tagged = tag_items(dedupe_items(raw_items))
        logger.info(
            "IntelligenceCollector finalize raw=%d unique=%d",
            len(raw_items),
            len(tagged),
        )
        return tagged

    @staticmethod
    def _workers(n_sources: int) -> int:
        from quant_shell.config.settings import settings

        configured = int(getattr(settings, "intel_source_workers", 4) or 4)
        return max(1, min(configured, n_sources, 8))

    @staticmethod
    def _global_cache_fresh() -> bool:
        from quant_shell.config.settings import settings

        max_age_min = float(getattr(settings, "intel_cache_max_age_min", 120) or 120)
        if max_age_min <= 0:
            return True
        age_sec = time.monotonic() - _global_cache_mono
        return age_sec <= max_age_min * 60.0

    def _fetch_safe(self, source: IntelligenceSource, symbol: str) -> list[IntelligenceItem]:
        """单源偶发失败先重试；仍失败则空列表 + INTEL_SOURCE_FAIL。"""
        try:
            return call_with_retry(
                lambda: source.fetch(symbol),
                layer="L2",
                op=source.name,
                symbol=symbol,
            )
        except DataFetchError as exc:
            audit.emit(
                layer="L2",
                event="intel_source_fail",
                severity="ERROR",
                symbol=symbol,
                error_code="INTEL_SOURCE_FAIL",
                message=f"{source.name}: {exc.message}",
                data={"source": source.name},
            )
            self.source_failures.append(
                {
                    "source": source.name,
                    "symbol": symbol,
                    "error": exc.message,
                }
            )
            logger.warning("source=%s failed: %s", source.name, exc.message)
            return []
