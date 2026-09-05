## Why

当前项目需要一套可在 Codex 中运行、以证据和能力为中心的多 Agent 股票投研与组合决策架构。该架构必须把 LLM 的研究与综合能力同确定性数据处理、持仓核算和硬风控清晰分开，并使每次决策可追溯、可回放、可评估，同时禁止真实下单和未经审核的自我修改。

## What Changes

- 建立开发控制面、产品运行面和学习优化面三套相互隔离的职责、权限与晋升边界。
- 建立以 `portfolio-council` Skill 驱动的运行模式：Codex 主线程担任 CIO，按任务动态委派少量专业 runtime 子 Agent，而不是预先创建大量固定 Agent。
- 为每项投资研究能力定义 `Input -> Tool/Data -> Skill/Reasoning -> Structured Output -> Eval` 的完整契约。
- 建立只读 MCP 数据访问、双时间 Evidence Store，以及带 `source_id` 和 `as_of` 的事实与主张血缘。
- 建立前置风险预检和后置不可绕过的 deterministic Risk Engine；LLM 负责投资判断，Python 仅负责数据、数学、核算、硬约束、验证和存储。
- 输出仅供研究参考的结构化 `BUY / ADD / HOLD / TRIM / EXIT / NO_TRADE` 计划、目标仓位范围、证据、反证、失效条件和风险否决原因。
- 建立 Decision Trace、Human Feedback、Market Outcome、Point-in-time Replay 和 Regression 机制。
- 自我优化初期仅允许生成 Improvement Proposal；任何生产变更均须回到开发控制面，经 OpenSpec、测试、评审和人工晋升。
- MVP 收敛为单一市场、日频或收盘后、long-only、高流动性普通股票、无杠杆、无衍生品、无做空、无券商写入和无真实下单；具体市场和数据供应商通过适配层选择，不在本架构 Change 中绑定。

## Capabilities

### New Capabilities

- `three-plane-governance`: 定义开发控制面、产品运行面、学习优化面的指令、权限、依赖和版本晋升边界。
- `point-in-time-evidence`: 定义只读数据访问、事实来源、双时间证据、冲突与过期检测以及 Evidence Store 行为。
- `specialist-research`: 定义公司研究、估值、市场与催化剂、反证研究等可组合能力及其结构化输出。
- `portfolio-council-orchestration`: 定义 CIO 主线程、`portfolio-council` Skill、动态委派、独立研究、冲突综合和一次修订协议。
- `deterministic-portfolio-risk`: 定义持仓规范化、组合数学、前置预检、后置硬风控和不可绕过的否决语义。
- `advisory-decision-output`: 定义结构化投资计划、证据闭包、失效条件、`NO_TRADE` 和禁止真实执行的输出契约。
- `decision-trace-evaluation`: 定义完整决策追踪、能力级 Eval、回放、防未来数据泄漏和多 Agent 消融评估。
- `controlled-learning-loop`: 定义反馈、市场结果、反思建议、离线回归和人工版本晋升流程。

### Modified Capabilities

无。当前项目没有既有产品能力规格。

## Impact

- 将新增根级和产品级 Agent 指令边界、Codex Agent Package、Skills、runtime Agent 配置和 MCP 契约。
- 将新增事实、证据、研究报告、组合决策、风险报告、Decision Trace 和 Improvement Proposal 等版本化 Schema。
- 将新增 Python 确定性层，用于数据规范化、数学计算、持仓核算、硬风控、验证和存储，但不得承载主观投资判断规则。
- 将新增 Evidence Store、只读 MCP 契约、可重复的 fixture/reference adapter、Eval 数据集、Replay 与 Regression 流程；首个生产数据供应商适配器由后续独立 Change 选择和实现。
- 产品面不会包含券商写工具、订单发送接口或任何真实交易执行能力。
