# 开发入口

本仓库是仅供研究建议的股票研究 Agent Package。目标方向：Claude Code 原生能力（Skills、Subagents、MCP）承担研究、编排与交互；Python 只提供数据获取、确定性计算、输入校验与持久化。长期产品方向见 [PRODUCT.md](PRODUCT.md)。

默认用中文沟通和写文档；代码标识符、命令、路径与专业术语保留英文。

## 目录

- `product/skills/`：研究方法 Skills（公司、估值、反证、催化剂、行业、宏观、期权、所有权、研报、技术结构、持仓录入、交易日志与反思）。
- `product/deterministic/`：估值、市场/技术统计、组合指标与硬风险约束。
- `product/mcp/live/`、`product/mcp/provenance.py`：SEC、NASDAQ、Yahoo、Moomoo OpenD、Eastmoney、宏观、期权等只读数据源接入；目前没有 MCP server 对外暴露。
- `product/intake/`：持仓截图/手工输入 → PortfolioDraft/Handoff v3。
- `product/broker/tiger/`、`product/web/trades.py`：Tiger 只读账户快照与私人券商账本。
- `product/trading_journal/`：个人交易日志、K 线标记与交易反思。
- `product/runtime/`：仅剩被上述模块引用的 helper（hashing、schema_validation、monetary、single_stock_input）以及 Research Memory、PIT evidence gate、TTM EPS 构建。
- `evals/`：合成评估样本、rubric、回归情境（只有数据，没有执行框架）。
- `tests/`：业务逻辑测试。
- `archive/`：只读参考（历史规格、未完成需求、旧角色正文、旧流程文档），不参与开发、不被代码引用。

## 规则

- 2026-10-12 瘦身后，旧编排、CLI、Hook、版本锁、Replay/Eval 与任务授权 MCP 已删除，部分模块和测试会因引用已删代码而无法运行，属预期结果。完整旧版本见 git tag `pre-slim-20261012`。
- 能交给 Claude Code 原生能力完成的，不再自建 Python 控制层（Agent loop、状态机、调度、Hook 事件、审批流、版本锁、晋升门槛）。
- 不把主观投资判断编码成确定性评分或规则引擎；LLM 负责研究、解释与判断，Python 只负责数据与数学。
- 承载事实的数据保留 `source_id`、`as_of`、`retrieved_at`。
- 券商接入永久只读：禁止下单、预览、改单、撤单、换汇、转账、交易解锁及任何账户写入。凭据与完整账户号不得进入仓库、Agent 上下文或网页。
- 不提交凭据、私人账本（`product/.private/`）、`product/tiger.md` 或私人会话数据。
- 只做当前任务需要的最小改动；新增机制前先说明现有能力为何不够。
