# 开发入口

本仓库是仅供研究建议的股票研究 Agent Package。目标方向：Claude Code 原生能力（Skills、Subagents、MCP）承担研究、编排与交互；Python 只提供数据获取、确定性计算、输入校验与持久化。长期产品方向见 [PRODUCT.md](PRODUCT.md)。

默认用中文沟通和写文档；代码标识符、命令、路径与专业术语保留英文。

## 目录

- `product/skills/`：当前启用的研究 Skills（`stock-research` 入口、`research-standards`、`company-fundamentals`、`valuation`、`peer-comparison`、`macro-market-context`、`technical-structure`、`skeptic-review`、`investment-decision`；评估用的轻量组内方向预测 `direction-forecast`），以及原样引入的 moomoo 官方搜索类与异动类 Skills（来源与约束见 `product/vendor/moomoo-skills.md`；OpenAPI 交易类明确不引入），通过 `.claude/skills`、`.agents/skills` 符号链接暴露给两个宿主。moomoo 的方向判断、情绪与异动解读只作参考展示，不参与研究判断。
- `product/references/`：三个角色共用的方法卡（`methods/`）、历史案例卡（`cases/`，按结果已知日期过滤）与输出格式（`templates/`）；统计证据由 `scripts/build-signal-events.py` 生成事件表，经 `get_signal_stats` 按“当时已知”统计；关键图形时刻（跌破/突破平台、趋势失败、急速反转）由 `scripts/build-key-moments.py` 建表，经 `get_key_moments` 给出同类时刻之后的概率与幅度分布。
- `product/skills-pending/`：待后续阶段重写的旧 Skills（期权、所有权、研报、催化剂、持仓录入、交易日志与反思），不暴露给宿主。
- 子 Agent：`advocate`（正向论点：业务驱动、预期差、催化剂）与 `skeptic`（先独立反向研究，再核验正向论点一轮）；定义在 `.claude/agents/` 与 `.codex/agents/`；主线程担任 CIO。
- `product/mcp/server.py`：stock-data MCP server（`.mcp.json`、`.codex/config.toml` 的 `stock_data`），工具在 `data_tools.py`、`calc_tools.py`、`context_tools.py`（宏观、市场、同业、GDELT 历史新闻）、`ownership_tools.py`（Form 4 内部人交易、知名基金 13F）、`congress_tools.py`（众议院议员交易申报，索引由 `scripts/build-house-ptr-index.py` 建立）、`decision_log.py`；所有时点工具支持 `as_of` 历史回放；数据默认写入仓库内已忽略的 `.local/`：`.local/data/`（正式使用的报告与决策记录）、`.local/cache/`（共享原始响应缓存）、`.local/runs/<run-id>/`（每次调试运行）。
- `product/deterministic/`：估值、市场/技术统计、组合指标与硬风险约束。
- `product/mcp/live/`、`product/mcp/provenance.py`：SEC、NASDAQ、Yahoo、Eastmoney、宏观等只读数据源接入代码，供 MCP 工具复用（旧采集管线、OpenD 行情与期权接入已于 2026-11-11 移除，见 tag `pre-slim-20261012`）。
- `product/intake/`：持仓截图/手工输入 → PortfolioDraft/Handoff v3。
- `product/broker/tiger/`、`product/web/trades.py`：Tiger 只读账户快照与私人券商账本。
- `product/trading_journal/`：个人交易日志、K 线标记与交易反思。
- `product/runtime/`：仅剩被上述模块引用的 helper（hashing、schema_validation、monetary、single_stock_input）。
- `evals/`：历史回放与对照实验（`replay/`）、信号与市场情境统计（`signals/`、`macro/`、`short/`、`news/`、`community/`）、前瞻账本（`forward/`）。评分脚本在 `scripts/score-forecasts.py`（完整研究）与 `scripts/score-group-forecasts.py`（组内排序）。
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
- 宿主实跑调试统一用 `scripts/dev-research.sh <claude|codex> <TICKER> [--model M]`：2026-11-10 起调试与批量回放优先用 Codex（`gpt-6-luna` 默认，`gpt-6.1-terra` 用于需要更强推理的对照），Claude Code 会话额度留给交互开发；Claude Code 默认 `claude-haiku-5-5`。可用 `--model` 或 `STOCK_AGENT_CLAUDE_MODEL` / `STOCK_AGENT_CODEX_MODEL` 覆盖。产物只写入 `.local/runs/<run-id>/`；不要写到 `/tmp` 或用户主目录。

<!-- handoff:learnings:begin -->
## Session Learnings (auto-updated by handoff)

### Key Decisions
- Decision: expected return from scenario table no longer gates BUY/NO_TRADE; valuation only sizes position — Reason: base scenario negative in 65/84 replay reports regardless of regime, 1-year value gap vs 60-day window mismatch
- Decision: evaluate ranking within peer group vs group median, always alongside prior-60d/126d momentum controls — Reason: plan C 0.47 rank corr fell to 0.23 within sector; single date = one observation
- Decision: stop adding replay dates / tuning rules for 60-day direction — Reason: ablation, A/A'/C, plan D all at coin-flip; pre-registered rule in plan D said stop
- Decision: target is advisor at key chart moments with base-rate distributions (p_up, avg gain/loss, expectancy, drawdown) vs any-day baseline — Reason: user confirmed; wants unemotional probability x payoff advice, not a backtested formula
- Decision: moment definitions normalised by each stock's daily volatility, thresholds not tuned to results — Reason: same rule must fit KO and RKLB; avoid data dredging
- Decision: keep scripts/build-pead-events.py — Reason: insider/congress stats still use its daily control rows
- Decision: sub-session work shares main checkout, no branches — Reason: user preference to work on main

<!-- handoff:learnings:end -->
