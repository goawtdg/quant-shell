from __future__ import annotations

from pathlib import Path

import pytest

from quant_shell import create_strategy_engine
from quant_shell.plugin.loader import load_strategy_class, resolve_strategy_spec
from quant_shell.plugin.profile import StrategyProfile
from reference_policy.policy.plugin import ReferencePolicyPlugin

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_resolve_default_spec():
    assert resolve_strategy_spec(None).endswith("ReferencePolicyPlugin")


def test_load_reference_class():
    cls = load_strategy_class("reference_policy.policy.plugin:ReferencePolicyPlugin")
    assert cls is ReferencePolicyPlugin


def test_profile_load_and_policy_config():
    path = EXAMPLES / "minimal_custom" / "strategy.yaml"
    profile = StrategyProfile.load(path)
    assert profile.name == "minimal_custom"
    cfg = profile.to_policy_config()
    assert cfg.signal_threshold_moderate == 0.08
    assert cfg.single_stock_limit == 0.08


def test_create_reference_engine():
    engine = create_strategy_engine()
    assert isinstance(engine, ReferencePolicyPlugin)


def test_no_quant_system_import_in_shell():
    import quant_shell.common.types as types_mod

    src = Path(types_mod.__file__).read_text(encoding="utf-8")
    assert "quant_system" not in src


def test_create_minimal_custom_with_profile():
    try:
        from examples.minimal_custom.plugin import MinimalCustomPlugin
    except ImportError:
        pytest.skip("examples not on PYTHONPATH")
    engine = create_strategy_engine(
        strategy_module="examples.minimal_custom.plugin:MinimalCustomPlugin",
        strategy_profile=EXAMPLES / "minimal_custom" / "strategy.yaml",
    )
    assert isinstance(engine, MinimalCustomPlugin)
    assert engine._config.signal_threshold_moderate == 0.08  # noqa: SLF001


def test_create_commit_decision_default():
    from quant_shell.factory import create_commit_decision
    from reference_policy.policy.commit import commit_decision

    assert create_commit_decision() is commit_decision


def test_plugin_status_keys():
    from quant_shell.factory import plugin_status

    st = plugin_status()
    assert "strategy_module" in st
    assert st["strategy_module"].endswith("ReferencePolicyPlugin")
    assert "commit_module" in st
    assert "picker_module" in st
    assert st.get("reference_installed") == "1"


def test_quant_shell_has_no_toplevel_reference_policy_import():
    """框架核源码不得硬绑定 reference_policy（插件经 env 懒加载）。"""
    root = Path(__file__).resolve().parents[1] / "src" / "quant_shell"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "from reference_policy" in line or "import reference_policy" in line:
                offenders.append(f"{path.relative_to(root)}:{i}:{stripped}")
    assert not offenders, "reference_policy hard imports:\n" + "\n".join(offenders)


def test_reference_installed_flag():
    from quant_shell.plugin.loader import reference_installed

    assert reference_installed() is True


def test_quant_shell_package_excludes_reference_tree():
    """主包 src 下不得再残留 reference_policy 目录。"""
    root = Path(__file__).resolve().parents[1] / "src"
    assert not (root / "reference_policy").exists()


def test_desk_adapter():
    from quant_shell.adapters.desk import desk_health, desk_plugin_payload

    assert desk_health()["ok"] is True
    payload = desk_plugin_payload()
    assert payload["ok"] is True
    assert "plugins" in payload


def test_project_root_is_package_root():
    from quant_shell.config.env_loader import project_root

    root = project_root()
    assert (root / "pyproject.toml").is_file()
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "quant-shell"' in text
