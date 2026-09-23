## Why

Macro、Market 与 Company 的采集和多维研究已经能够形成结构化资料，但真实持仓链路仍停在 `HoldingResearchBundle`，尚未让现有 Independent Skeptic 对同一 point-in-time Evidence 开展独立反证。先补齐“正向多维研究 + 独立反证”的可验证研究层，可以在不引入 CIO、Risk 或回测复杂度的前提下暴露 MRVL 等真实样本的证据冲突和失败路径，并为下一阶段组合综合提供可靠输入。

## What Changes

- 补齐真实 MRVL 暴露的正向研究交付阻塞：可信会话绑定封装缺失技术身份、区分执行结束与报告成功、精确 Evidence 引用交付，以及单股 Macro/Market 传导要求。先用失败样例做确定性验证，再做真实验收；不通过增加模型重试或降低核心门禁绕过失败。
- 在 `portfolio-council` 下增加显式 `INDEPENDENT_COUNTER_THESIS_RESEARCH` 阶段；它承接已验证的 `DOWNSTREAM_READY` 多维研究包和同一 `PortfolioHandoff`、`CouncilRequest`、cutoff、Evidence Gate，不改变现有多维研究阶段“不会自动启动下游”的行为。
- 复用现有 `runtime_skeptic`、`counter-thesis` Skill 与 Gate-scoped 只读 Evidence 工具，按普通股逐证券生成 `INDEPENDENT_FIRST_PASS` 独立风险研究。正向研究保持客观，Skeptic 寻找遗漏的替代解释和失败路径，不固定唱空；首版不增加读取正向报告后的针对性质疑轮次。
- 对 `CounterThesisReport` 作最小版本升级，补齐报告内假设定义与引用闭合，沿用现有挑战字段表达事实依据、传导逻辑、待补证据和可推翻条件；不增加评分体系或强制挑战数量。
- Skeptic 的模型输入只包含证券、研究范围、截止时点、必要的非结论性任务上下文及其许可 Evidence IDs；不得读取 `EquityResearchReport`、`ResearchDimensionReport`、`HoldingResearchBundle` 内容、未解决问题、摘要、hash 或其他 Agent 派生结论。
- 确定性层生成轻量的正反研究交接索引，引用而不复制已验证 `HoldingResearchBundle` 和逐证券 `CounterThesisReport`，校验 run、Portfolio、Request、cutoff、Gate、身份和 Evidence Closure 一致性，并区分诊断可读与后续 CIO 就绪。
- 阶段在正反研究交接处停止：不启动 CIO、Risk、组合动作、真实交易、Outcome 观察、历史重放、回测、Regression、Ablation 或 Promotion。
- 明确逐 Invocation 的工具授权、同行公开事实和确定性计算的读取范围；区分报告合法可读与反证完成，超时及证据不足保留为限制交接。同一冻结运行允许有界续跑失败任务，已经验证的成功产物保持不变。
- 以 MRVL 作为首个真实纵向样本：必须在同一时间边界下形成合格正向研究包和独立反证报告；不得拼接当前 v2/v4 或其他历史运行的不同 cutoff 产物冒充同一次研究。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `multi-dimensional-holding-research`：定义合格多维研究包进入独立反证阶段的绑定、核心覆盖、交接状态与跨运行拒绝规则。
- `specialist-research`：把现有 Independent Skeptic 激活到真实多维持仓研究后续阶段，明确逐证券输入隔离、Evidence 范围、结构化输出和失败语义。
- `portfolio-council-orchestration`：增加显式独立反证研究阶段及其终止边界，保持 CIO、Risk 和完整组合决策未启动。

## Impact

- 本 Change 已获实施、一次 MRVL 真实运行及最终同步归档授权；实现、聚焦确定性验证和真实纵向验收结果写入独立验收记录。保留全部失败证据；`EVIDENCE_CLOSURE_FAILED` 只证明引用不在允许集合，不等于未查询证据，且本 Change 未增加“补查询再提交”机制。
- 主要影响 `product/runtime/multidimensional_stage.py`、阶段规划/CLI/宿主启动接缝、Invocation 与 Hook 绑定、确定性验证和阶段终态产物。
- 复用 `product/.codex/agents/runtime_skeptic.toml`、`product/skills/counter-thesis/` 与现有 live Evidence MCP；报告新版本补充假设定义，并保留旧版本报告的读取与验证路径。MCP 从单一 focus/固定文件绑定扩展到可信任务映射中的逐 Invocation 授权。
- 需要一个版本化的正反研究交接索引 Schema、同源中文摘要及聚焦契约测试；历史研究包继续按其锁定版本读取，不自动补写 Skeptic 产物。
- MRVL 真实验收需要新的同一 run/cutoff 运行目录和宿主真实 Agent 证据；现有 `/private/tmp` 运行只作为缺口依据，不作为新 Change 的完成证据。
