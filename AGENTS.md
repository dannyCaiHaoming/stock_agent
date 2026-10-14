# 开发入口

本仓库是仅供研究建议的股票研究 Agent Package。目标方向：Claude Code 原生能力（Skills、Subagents、MCP）承担研究、编排与交互；Python 只提供数据获取、确定性计算、输入校验与持久化。长期产品方向见 [PRODUCT.md](PRODUCT.md)。

默认用中文沟通和写文档；代码标识符、命令、路径与专业术语保留英文。

## 目录

- `product/skills/`：当前启用的研究 Skills（`stock-research` 入口、`research-standards`、`company-fundamentals`、`valuation`、`peer-comparison`、`macro-market-context`、`technical-structure`、`skeptic-review`、`investment-decision`），以及原样引入的 moomoo 官方搜索类与异动类 Skills（来源与约束见 `product/vendor/moomoo-skills.md`；OpenAPI 交易类明确不引入），通过 `.claude/skills`、`.agents/skills` 符号链接暴露给两个宿主。moomoo 的方向判断、情绪与异动解读只作参考展示，不参与研究判断。
- `product/skills-pending/`：待后续阶段重写的旧 Skills（期权、所有权、研报、催化剂、持仓录入、交易日志与反思），不暴露给宿主。
- 子 Agent：`advocate`（正向研究：亮点与历史验证）与 `skeptic`（反向研究），两者也分别从正反两个角度审查 CIO 的最终判断；定义在 `.claude/agents/` 与 `.codex/agents/`；主线程担任 CIO。
- `product/mcp/server.py`：stock-data MCP server（`.mcp.json`、`.codex/config.toml` 的 `stock_data`），工具在 `data_tools.py`、`calc_tools.py`、`context_tools.py`（宏观、市场、同业）、`decision_log.py`；数据默认写入仓库内已忽略的 `.local/`：`.local/data/`（正式使用的报告与决策记录）、`.local/cache/`（共享原始响应缓存）、`.local/runs/<run-id>/`（每次调试运行）。
- `product/deterministic/`：估值、市场/技术统计、组合指标与硬风险约束。
- `product/mcp/live/`、`product/mcp/provenance.py`：SEC、NASDAQ、Yahoo、Moomoo OpenD、Eastmoney、宏观、期权等只读数据源接入代码，供 MCP 工具复用。
- `product/intake/`：持仓截图/手工输入 → PortfolioDraft/Handoff v3。
- `product/broker/tiger/`、`product/web/trades.py`：Tiger 只读账户快照与私人券商账本。
- `product/trading_journal/`：个人交易日志、K 线标记与交易反思。
- `product/runtime/`：仅剩被上述模块引用的 helper（hashing、schema_validation、monetary、single_stock_input）以及 Research Memory、PIT evidence gate、TTM EPS 构建。
- `evals/`：合成评估样本、rubric、回归情境（只有数据，没有执行框架）。
- `tests/`：业务逻辑测试。
- `archive/`：只读参考（历史规格、未完成需求、旧角色正文、旧流程文档），不参与开发、不被代码引用。

## 规则

- 开发路线与进度见 [docs/roadmap.md](docs/roadmap.md)。
- 2026-10-12 瘦身后，旧编排、CLI、Hook、版本锁、Replay/Eval 与任务授权 MCP 已删除，部分旧模块和测试会因引用已删代码而无法运行，属预期结果，不以修复旧测试为目标。完整旧版本见 git tag `pre-slim-20261012`。
- 能交给 Claude Code 原生能力完成的，不再自建 Python 控制层（Agent loop、状态机、调度、Hook 事件、审批流、版本锁、晋升门槛）。
- 不把主观投资判断编码成确定性评分或规则引擎；LLM 负责研究、解释与判断，Python 只负责数据与数学。
- 承载事实的数据保留 `source_id`、`as_of`、`retrieved_at`。
- 券商接入永久只读：禁止下单、预览、改单、撤单、换汇、转账、交易解锁及任何账户写入。凭据与完整账户号不得进入仓库、Agent 上下文或网页。
- 不提交凭据、私人账本（`product/.private/`）、`product/tiger.md` 或私人会话数据。
- 只做当前任务需要的最小改动；新增机制前先说明现有能力为何不够。
- 宿主实跑调试统一用 `scripts/dev-research.sh <claude|codex> <TICKER> [--model M]`：默认 Claude Code `claude-haiku-5-5`、Codex `gpt-6-luna`，可用 `--model` 或 `STOCK_AGENT_CLAUDE_MODEL` / `STOCK_AGENT_CODEX_MODEL` 覆盖。产物只写入 `.local/runs/<run-id>/`；不要写到 `/tmp` 或用户主目录。
