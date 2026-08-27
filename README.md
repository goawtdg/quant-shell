# quant-shell

MIT 许可的 A 股**模拟盘研究框架**：管道固定，策略与因子可插拔。

带决策台（Next.js + FastAPI）：用白话写交易想法 → 生成有限菜谱模型 → 跑纸面 / linkage。  
**不是投资建议，不保证盈利。**

## 快速开始

Python ≥ 3.11。建议 conda / venv。

```powershell
cd quant-shell
pip install -e ".[desk]"
pip install -e ./packages/quant-shell-reference   # 可选：示例策略栈

# 终端 1 — API :8766
python -m quant_shell.desk

# 终端 2 — 前端 :3000
cd web
npm install
npm run dev
```

打开 http://localhost:3000 → **交易想法** → 生成并保存模型 → **任务中心** 跑纸面。

可选配置（**不要提交真实密钥**）：

```powershell
copy .env.example .env          # 根目录：DeepSeek / 风控 / 插件
copy web\.env.example web\.env.local   # 前端 API 地址，默认即可
```

在 `.env` 填入 `DEEPSEEK_API_KEY` 后即可启用 LLM；留空则走规则 / OSINT。运行时写入 `/data/`（已 gitignore），克隆后为空账户、无报告、无任务历史。

## 命令行

```powershell
python -m quant_shell.cli model
python -m quant_shell.cli run --symbol 510300
python -m quant_shell.cli account
python -m quant_shell.cli linkage
python -m quant_shell.cli plugins
```

开发依赖：`pip install -e ".[dev]"` 或 `powershell -File scripts/install_dev.ps1`。

## 仓库结构

```
src/quant_shell/     # 框架核（数据 → 信号 → 策略接口 → 风控 → 纸面 → 人工/LLM 门）
  desk/              # 决策台 API
  studio/            # 交易想法 → TradingModel
web/                 # Next.js 决策台
packages/quant-shell-reference/   # 可选示例策略（非内置 alpha）
examples/            # 最小自定义因子 / 策略示例
```

## 扩展（写代码）

通过环境变量挂插件（`module:attr`）：

| 变量 | 作用 |
|------|------|
| `STRATEGY_MODULE` | 实现 `StrategyEngine` 的策略类 |
| `FACTOR_MODULE` | 因子 registry 工厂 |
| `COMMIT_MODULE` | 最终动作收紧 |
| `STRATEGY_PROFILE` | 阈值 YAML 路径 |

契约见 `quant_shell.common.interfaces`；示例见 `examples/` 与 `packages/quant-shell-reference`。

纯壳：只装 `quant-shell`，自行实现接口。装 reference 后默认指向其示例实现。

## 许可与免责

[MIT](LICENSE)。模拟盘研究用途；studio 菜谱与 `quant-shell-reference` **不构成投资建议或收益承诺**。
