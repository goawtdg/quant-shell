# quant-shell-reference

可选**示例**策略包，非框架必选，无盈利承诺。

```bash
pip install -e ./packages/quant-shell-reference
# 或: pip install -e ".[reference]"
```

装好后默认：

```
STRATEGY_MODULE=reference_policy.policy.plugin:ReferencePolicyPlugin
PICKER_MODULE=reference_policy.picker.engine:FactorStrategyEngine
COMMIT_MODULE=reference_policy.policy.commit:commit_decision
```

只装 `quant-shell` 时可自行实现 `StrategyEngine` / `StockPicker`。
