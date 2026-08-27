from __future__ import annotations

from pathlib import Path

import pytest

from quant_shell.factors import build_empty_registry, load_registry
from quant_shell.factors.registry import FactorRegistry

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_empty_registry_by_default():
    reg = load_registry(base_dir=EXAMPLES / "_tmp_data", scope="etf")
    assert isinstance(reg, FactorRegistry)
    assert reg.active_specs() == []


def test_user_factor_module(monkeypatch):
    monkeypatch.setenv(
        "FACTOR_MODULE",
        "examples.user_factors.registry:build_registry",
    )
    reg = load_registry(base_dir=EXAMPLES / "_tmp_data", scope="etf")
    names = {s.name for s in reg.active_specs()}
    assert "momentum_20" in names


def test_build_empty_registry():
    assert build_empty_registry().all_specs() == []
