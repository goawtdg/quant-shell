"""白名单 GP 表达式求值 — 插件因子唯一计算器。"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

_TS_RANK_WINDOW = 60


class ExprError(ValueError):
    """表达式非法或求值失败。"""


def _ts_rank(series: pd.Series, window: int = _TS_RANK_WINDOW) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce")
    return clean.rolling(window, min_periods=max(10, window // 4)).rank(pct=True)


def _as_series(value: pd.Series | float, like: pd.Series) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    return pd.Series(float(value), index=like.index)


def _rolling_window(n: pd.Series | float) -> int:
    if isinstance(n, pd.Series):
        raise ExprError("window arg must be scalar int")
    w = int(float(n))
    if w < 1:
        raise ExprError(f"invalid window {w}")
    return w


def _call(name: str, args: list[pd.Series | float], like: pd.Series) -> pd.Series | float:
    n = name.lower()
    if n == "rank":
        if len(args) != 1:
            raise ExprError("rank takes 1 arg")
        return _ts_rank(_as_series(args[0], like))
    if n == "abs":
        return _as_series(args[0], like).abs()
    if n == "neg":
        return -_as_series(args[0], like)
    if n == "log1p":
        return np.log1p(_as_series(args[0], like).clip(lower=-0.999999))
    if n == "div":
        a, b = _as_series(args[0], like), _as_series(args[1], like)
        return a / b.replace(0, np.nan)
    if n == "mul":
        return _as_series(args[0], like) * _as_series(args[1], like)
    if n == "add":
        return _as_series(args[0], like) + _as_series(args[1], like)
    if n == "sub":
        return _as_series(args[0], like) - _as_series(args[1], like)
    if n == "sum":
        x, w = _as_series(args[0], like), _rolling_window(args[1])
        return x.rolling(w, min_periods=max(1, w // 2)).sum()
    if n == "sma":
        x, w = _as_series(args[0], like), _rolling_window(args[1])
        return x.rolling(w, min_periods=max(1, w // 2)).mean()
    if n == "std":
        x, w = _as_series(args[0], like), _rolling_window(args[1])
        return x.rolling(w, min_periods=max(2, w // 2)).std()
    if n == "pct_change":
        if len(args) == 1:
            return _as_series(args[0], like).pct_change(periods=1)
        x, w = _as_series(args[0], like), _rolling_window(args[1])
        return x.pct_change(periods=w)
    if n == "min":
        if len(args) == 2 and not isinstance(args[1], pd.Series):
            x, w = _as_series(args[0], like), _rolling_window(args[1])
            return x.rolling(w, min_periods=max(1, w // 2)).min()
        return np.minimum(_as_series(args[0], like), _as_series(args[1], like))
    if n == "max":
        if len(args) == 2 and not isinstance(args[1], pd.Series):
            x, w = _as_series(args[0], like), _rolling_window(args[1])
            return x.rolling(w, min_periods=max(1, w // 2)).max()
        return np.maximum(_as_series(args[0], like), _as_series(args[1], like))
    raise ExprError(f"unknown function {name}")


def eval_factor_expression(expr: str, df: pd.DataFrame) -> pd.Series:
    """在单票 OHLCV 上求值白名单表达式。"""
    text = (expr or "").strip()
    if not text:
        raise ExprError("empty expression")
    cols = {
        "open": pd.to_numeric(df["open"], errors="coerce"),
        "high": pd.to_numeric(df["high"], errors="coerce"),
        "low": pd.to_numeric(df["low"], errors="coerce"),
        "close": pd.to_numeric(df["close"], errors="coerce"),
        "volume": pd.to_numeric(df["volume"], errors="coerce").replace(0, np.nan),
    }
    like = cols["close"]

    def parse(s: str, i: int = 0) -> tuple[pd.Series | float, int]:
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s):
            raise ExprError("unexpected end")
        if s[i].isdigit() or (s[i] == "." and i + 1 < len(s) and s[i + 1].isdigit()):
            m = re.match(r"\d+(\.\d+)?", s[i:])
            assert m
            return float(m.group()), i + len(m.group())
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", s[i:])
        if not m:
            raise ExprError(f"bad token at {i}: {s[i : i + 20]!r}")
        name = m.group()
        i += len(name)
        while i < len(s) and s[i].isspace():
            i += 1
        if i >= len(s) or s[i] != "(":
            if name in cols:
                return cols[name], i
            raise ExprError(f"unknown identifier {name}")
        i += 1
        args: list[pd.Series | float] = []
        while True:
            while i < len(s) and s[i].isspace():
                i += 1
            if i < len(s) and s[i] == ")":
                i += 1
                break
            arg, i = parse(s, i)
            args.append(arg)
            while i < len(s) and s[i].isspace():
                i += 1
            if i < len(s) and s[i] == ",":
                i += 1
                continue
            if i < len(s) and s[i] == ")":
                i += 1
                break
            raise ExprError(f"expected , or ) at {i}")
        return _call(name, args, like), i

    value, end = parse(text, 0)
    if text[end:].strip():
        raise ExprError(f"trailing junk: {text[end:]!r}")
    return _as_series(value, like)


def validate_expression_syntax(expr: str) -> None:
    """用合成 OHLCV 校验语法；失败抛 ExprError。"""
    n = 80
    close = pd.Series([10.0 + i * 0.01 for i in range(n)])
    df = pd.DataFrame(
        {
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": pd.Series([1_000_000.0 + i * 1000 for i in range(n)]),
        }
    )
    series = eval_factor_expression(expr, df)
    if series.dropna().empty:
        raise ExprError("expression produced all-NaN series")


def make_compute(expression: str):
    """返回 FactorSpec.compute 闭包。"""
    expr = expression.strip()

    def _compute(df: pd.DataFrame) -> pd.Series:
        return eval_factor_expression(expr, df)

    return _compute
