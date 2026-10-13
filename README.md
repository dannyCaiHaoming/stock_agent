# Stock Agent

仅供研究建议的股票研究 Agent Package。目标：用 Claude Code 原生的 Skills、Subagents 和 MCP 完成持仓研究、反证与综合建议；Python 只负责数据、计算、输入校验与持久化。

> 不连接券商的交易能力、不创建订单、不执行真实交易。

长期产品方向见 [PRODUCT.md](PRODUCT.md)，开发规则见 [AGENTS.md](AGENTS.md)。

## 使用

在本仓库目录打开 Claude Code 或 Codex，说“研究 MSFT”即可。首次在 Claude Code 中使用时需批准项目 MCP server `stock-data`。

- 入口 Skill：`stock-research`；数据与计算：stock-data MCP（免费来源 SEC EDGAR、Yahoo）。
- 报告与决策记录保存在仓库内已忽略的 `.local/data/`（可用 `STOCK_AGENT_DATA_DIR` 修改），不进入 git。
- 开发调试：`scripts/dev-research.sh <claude|codex> <TICKER> [--model M]`，产物在 `.local/runs/`。
- 开发路线与进度：[docs/roadmap.md](docs/roadmap.md)。旧版本完整内容见 git tag `pre-slim-20261012`。

## 目录

| 路径 | 内容 |
|---|---|
| `product/skills/` | 当前启用的研究 Skills（入口 `stock-research`） |
| `product/skills-pending/` | 待重写的旧 Skills |
| `product/mcp/server.py` 等 | stock-data MCP：数据、计算、决策记录工具 |
| `product/deterministic/` | 估值、TTM、市场/技术统计、组合指标、硬风险约束 |
| `product/mcp/live/` | SEC（companyfacts、13F、segments、Forms 3/4/5）、NASDAQ、Yahoo、Moomoo OpenD、Eastmoney、宏观（BLS/Treasury/Fed）、期权、OpenAlex 数据接入 |
| `product/intake/` | 持仓截图/手工输入 → PortfolioHandoff v3（`python3 -m product.intake.cli`） |
| `product/broker/tiger/` | Tiger 只读账户快照与私人券商账本（`python3 -m product.broker.tiger.cli`） |
| `product/trading_journal/` | 个人交易日志、K 线标记与交易反思 |
| `product/runtime/` | 共享 helper、Research Memory、PIT evidence gate |
| `evals/` | 合成评估样本、rubric、回归情境 |
| `docs/data/` | 数据源目录、免费源能力矩阵、SDK 契约、Tiger 只读边界 |
| `archive/` | 只读参考：历史规格、未完成需求、旧角色与流程文档 |

## 安装

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[live,broker-tiger]'
```
