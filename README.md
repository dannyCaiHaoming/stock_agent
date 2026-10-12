# Stock Agent

仅供研究建议的股票研究 Agent Package。目标：用 Claude Code 原生的 Skills、Subagents 和 MCP 完成持仓研究、反证与综合建议；Python 只负责数据、计算、输入校验与持久化。

> 不连接券商的交易能力、不创建订单、不执行真实交易。

长期产品方向见 [PRODUCT.md](PRODUCT.md)，开发规则见 [AGENTS.md](AGENTS.md)。

## 当前状态（2026-10-12 瘦身后）

本仓库刚删除了一套自建的控制系统，包括 Codex 启动器、Stage 状态机、Hook 事件、版本锁、Release Gate、Replay/Eval 与任务授权 MCP，只保留了业务能力。目前：

- 没有可用的 MCP server，也没有 Claude Code subagent 配置；
- 部分保留模块（`mcp/live/collection.py`、`web/trades.py` 等）和部分测试会因引用已删代码而无法运行；
- 完整旧版本见 git tag `pre-slim-20261012`。

## 目录

| 路径 | 内容 |
|---|---|
| `product/skills/` | 14 份研究方法 Skill |
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
