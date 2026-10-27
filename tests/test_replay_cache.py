"""现价 / PE / 成分 / 情报：新鲜磁盘样本优先，断网回放上一份。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from quant_shell.common.atomic_io import write_pickle_atomic
from quant_shell.common.exceptions import DataFetchError
from quant_shell.common.types import IntelligenceItem
from quant_shell.data.disk_cache import load_json_record, save_frame_ttl, save_json_record
from quant_shell.intelligence.collector import IntelligenceCollector, clear_global_intel_cache
from quant_shell.intelligence.sources.base import IntelligenceSource


def _etf_frame(price: float = 4.2) -> pd.DataFrame:
    return pd.DataFrame(
        {"代码": ["510300"], "最新价": [price], "成交量": [1000.0]}
    )


def _item(title: str = "cached-news") -> IntelligenceItem:
    return IntelligenceItem(
        item_id="item-1",
        source="cls",
        source_tier=1,
        title=title,
        content=title,
        published_at=datetime(2026, 10, 23, 9, 30),
    )


class _Boom(IntelligenceSource):
    name = "boom"
    is_symbol_scoped = False

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        raise DataFetchError(message="down", suggestion="retry")


class _SymbolBoom(IntelligenceSource):
    name = "symbol-boom"
    is_symbol_scoped = True

    def fetch(self, symbol: str = "") -> list[IntelligenceItem]:
        raise DataFetchError(message="down", suggestion="retry")


@pytest.fixture()
def cache_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "cache"
    root.mkdir()
    for module in (
        "quant_shell.data.disk_cache",
        "quant_shell.data.live_price",
        "quant_shell.data.stock_spot",
        "quant_shell.data.akshare_client",
        "quant_shell.data.universe",
        "quant_shell.intelligence.replay_store",
    ):
        monkeypatch.setattr(f"{module}.CACHE_ROOT", root)
    return root


def test_etf_spot_uses_fresh_disk_without_network(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_shell.data.live_price import clear_live_spot_cache, lookup_etf_spot

    clear_live_spot_cache()
    save_frame_ttl(cache_root / "etf_spot.pkl", _etf_frame(3.5))

    def _boom() -> pd.DataFrame:
        raise AssertionError("fresh disk should skip the network")

    monkeypatch.setattr("quant_shell.data.akshare_client.fetch_etf_spot_batch", _boom)
    row = lookup_etf_spot("510300")
    assert row.price == 3.5


def test_etf_spot_replays_stale_when_network_fails(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_shell.data.live_price import clear_live_spot_cache, lookup_etf_spot

    clear_live_spot_cache()
    write_pickle_atomic(
        cache_root / "etf_spot.pkl",
        {"ts": 0.0, "frame": _etf_frame(2.2)},
    )

    def _boom() -> pd.DataFrame:
        raise DataFetchError(message="eastmoney down", suggestion="use cache")

    monkeypatch.setattr("quant_shell.data.akshare_client.fetch_etf_spot_batch", _boom)
    row = lookup_etf_spot("510300", force_refresh=True)
    assert row.price == 2.2


def test_etf_universe_replays_stale_spot(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_shell.data.live_price import clear_live_spot_cache
    from quant_shell.risk.factor_ops import load_etf_universe

    clear_live_spot_cache()
    write_pickle_atomic(
        cache_root / "etf_spot.pkl",
        {
            "ts": 0.0,
            "frame": pd.DataFrame(
                {
                    "代码": ["510300", "159915"],
                    "最新价": [4.0, 2.0],
                    "成交量": [1.0, 9.0],
                }
            ),
        },
    )

    def _boom() -> pd.DataFrame:
        raise DataFetchError(message="eastmoney down", suggestion="use cache")

    monkeypatch.setattr("quant_shell.data.akshare_client.fetch_etf_spot_batch", _boom)
    symbols = load_etf_universe(max_etfs=5)
    assert symbols[0] == "510300"
    assert "159915" in symbols


def test_stock_quote_replays_stale_when_network_fails(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_shell.data.stock_spot import fetch_stock_spot_quote

    path = cache_root / "spot" / "600519.json"
    save_json_record(
        path,
        {
            "symbol": "600519",
            "name": "贵州茅台",
            "price": 1400.0,
            "volume": 10.0,
            "pe": 20.0,
            "market_cap": 1.0,
            "turnover_rate": 0.1,
        },
    )
    payload = load_json_record(path, ttl_sec=10**9)
    assert isinstance(payload, dict)
    save_json_record(path, payload)
    # 把时间戳改成过期，迫使走网络，再因失败回放。
    text = path.read_text(encoding="utf-8").replace('"ts":', '"ts": 0, "ignored":', 1)
    path.write_text(text, encoding="utf-8")

    def _boom(symbol: str) -> dict[str, float | str]:
        raise DataFetchError(message="quote down", suggestion="use cache")

    monkeypatch.setattr("quant_shell.data.stock_spot._fetch_stock_spot_live", _boom)
    row = fetch_stock_spot_quote("600519")
    assert row["price"] == 1400.0
    assert row["name"] == "贵州茅台"


def test_pe_replays_stale_when_legulegu_fails(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_shell.data.akshare_client import fetch_index_pe_percentile

    path = cache_root / "pe" / "510300.json"
    save_json_record(path, 0.42)
    raw = path.read_text(encoding="utf-8")
    path.write_text(raw.replace('"ts":', '"ts": 0, "ignored":', 1), encoding="utf-8")

    def _boom(index_name: str) -> float:
        raise DataFetchError(message="legulegu down", suggestion="use cache")

    monkeypatch.setattr(
        "quant_shell.data.akshare_client._fetch_legulegu_pe_quantile",
        _boom,
    )
    assert fetch_index_pe_percentile("510300") == 0.42


def test_universe_replays_stale_when_csindex_fails(cache_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quant_shell.data.universe import fetch_index_constituents

    path = cache_root / "universe_000300.json"
    save_json_record(path, ["600519", "600036"])
    # universe 缓存是 {ts, symbols}，与通用 {ts, data} 不同。
    path.write_text(
        '{"ts": 0, "symbols": ["600519", "600036"]}',
        encoding="utf-8",
    )

    def _boom(index_code: str) -> list[str]:
        raise DataFetchError(message="csindex down", suggestion="use cache")

    monkeypatch.setattr("quant_shell.data.universe._fetch_csindex_cons", _boom)
    assert fetch_index_constituents("csi300") == ["600519", "600036"]


def test_intel_replays_stale_global_items(cache_root: Path) -> None:
    from quant_shell.intelligence.replay_store import global_path, save_items

    clear_global_intel_cache()
    save_items(global_path(), [_item("replay-me")])
    raw = global_path().read_text(encoding="utf-8")
    global_path().write_text(raw.replace('"ts":', '"ts": 0, "ignored":', 1), encoding="utf-8")

    items = IntelligenceCollector([_Boom()]).collect_global()
    assert [item.title for item in items] == ["replay-me"]
    clear_global_intel_cache()


def test_intel_replays_stale_symbol_items(cache_root: Path) -> None:
    from quant_shell.intelligence.replay_store import save_items, symbol_path

    save_items(symbol_path("510300"), [_item("symbol-replay")])
    raw = symbol_path("510300").read_text(encoding="utf-8")
    symbol_path("510300").write_text(
        raw.replace('"ts":', '"ts": 0, "ignored":', 1),
        encoding="utf-8",
    )
    items = IntelligenceCollector([_SymbolBoom()]).collect_symbol("510300")
    assert [item.title for item in items] == ["symbol-replay"]
