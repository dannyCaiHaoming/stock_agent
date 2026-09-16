## Why

当前仓库已经具备 Agent、Skill、只读工具、CIO 与 Risk Engine 等基础组件，但默认开发闭环把“证明 Agent Package 能连通”与真实 LLM 研究质量、Replay、Regression、Ablation、Promotion 等发布级验证绑定，导致产品骨架尚未稳定时反复消耗在验证平台和批准流程上。现在需要先恢复一个可理解、可调用、可逐段观察的多 Agent MVP，让后续按 Agent 逐个接入真实 LLM 与专业能力。

## What Changes

- 新增明确的 `DEMO_SCAFFOLD` Profile：接受任意符合 Demo Schema 的 Portfolio 与 Evidence 输入，按固定数据流调用 Company Analyst、Independent Skeptic、CIO 和 deterministic Risk Engine，并生成最终 Demo 报告。
- 增加最小 `AgentPackageTopology`，绑定仓库内实际 Plugin manifest、`portfolio-council` Skill、CIO Role Policy、两个 Specialist Agent definitions、专业 Skills、只读 Tool/MCP 契约和角色输出 Schema；Demo 只证明绑定存在，不声称这些资源已参与真实推理。
- 为每个 Agent 定义清晰的输入信封、输出信封和状态，并由编排层用独立 Dispatch Record 记录发送者、接收者和原始 Artifact；每个角色既可单独调用并返回结构化响应，也可在完整链路中把已验证输出无人工改写地传给下游。
- Demo Adapter 只能通过与现有 Evidence Query 契约兼容的只读 Tool Port 按允许 ID 读取 Gate 合格事实，不得直接读取原始 fixture、Evidence 文件或隐式全局状态；后续真实 MCP/LLM Adapter 必须可在不改变 Agent 输入输出契约的情况下逐节点替换。
- MVP 阶段允许使用确定性 Demo Adapter 代替真实 LLM，以验证 Agent Package 的装配、隔离、数据传递、失败传播和最终输出；所有此类产物必须显式标记为 synthetic/demo，不得冒充真实投资研究、Runtime LLM 证明或候选晋升证据。
- `CIO Demo Adapter` 只验证 CIO Role Contract，不证明 Codex 当前主线程已担任 CIO；真实产品 Profile 仍要求 `portfolio-council` Skill 使当前主线程承担 CIO，并原生委派 Subagents。
- 保留 Evidence Closure、PIT、Schema、Risk、只读和禁止真实下单等硬边界；Demo 数据也必须携带 `source_id`、`as_of` 和 `retrieved_at`。
- 将 Runtime Eval、Execution Replay、12-case Regression、Calibration、Ablation、Promotion Gate 和重复真实 LLM 运行从默认开发与普通 Change 验收入口停用。源码与显式命令留存为参考能力，只有专门请求版本晋升或相关能力维护时才运行。
- 简化授权节奏：一次 apply 授权覆盖既定范围内的连续实施、普通错误修复和聚焦测试；仅在权限升级、破坏性操作、外部付费/凭证、范围或安全契约变化、真实阻断以及最终归档推送时请求用户决定。
- `us-equity-live-advisory-slice` 继续保持暂停和未完成状态；其实现与历史证据不删除、不回写为成功，也不进入本 MVP 的默认入口。待 Agent Package Demo 稳定后，再决定哪些部分可复用。
- **BREAKING**：现有把真实 LLM、语义 Eval、独立 Reviewer 或发布级验证作为每个 Agent Package 开发步骤默认完成条件的流程将被替换为分层验收；这些要求仍可作为显式产品运行或候选晋升门禁。

## Capabilities

### New Capabilities

- `agent-package-demo`: 定义无需真实 LLM 的多 Agent Demo Profile、实际 Package 拓扑绑定、只读 Tool Port、角色输入输出、链路传递、终态和最小 MVP 验收。

### Modified Capabilities

- `portfolio-council-orchestration`: 区分 `DEMO_SCAFFOLD` 与真实产品 Council，定义逻辑 fan-out/fan-in、编排层路由和 CIO 主线程升级接缝，同时禁止 Demo 冒充真实 LLM 运行。
- `specialist-research`: 为专业 Agent 增加可单独调用的输入输出边界，并将真实 LLM/Skill 证明限定到真实产品 Profile；Demo Profile 只验证契约和传递。
- `advisory-decision-output`: 增加明确标记的 Demo 报告终态与完整内容要求，保持证据、失效条件、风险和禁止真实执行边界。
- `decision-trace-evaluation`: 将默认 MVP 验收收敛为受影响的确定性测试与一次完整 Demo 流；高级评测和晋升能力改为显式按需执行。
- `three-plane-governance`: 简化已授权范围内的暂停条件和批准点，并规定高级验证能力不得阻塞 Agent Package MVP；具体 live Change 的暂停只记录在本 Change 规划中，不进入永久治理规格。

## Impact

- 主要影响 Agent Package 的 Demo 入口、拓扑清单、角色与 Tool 适配层、数据流契约、Demo fixture/产物、相关聚焦测试，以及根开发规则、开发流程和产品运行说明。
- 现有真实 `portfolio-council`、Agent 定义、Skills、MCP、Evidence/PIT/Risk 实现继续保留；真实产品 Profile 仍不得使用 Demo Adapter 形成投资建议。
- Replay、Regression、Calibration、Ablation、Promotion 与历史验证产物不删除、不迁移、不补写，只从默认开发/验收命令和文档主路径移除。
- 不接入真实行情、SEC 新能力、券商或真实下单；不恢复暂停中的 `us-equity-live-advisory-slice`，不修改其 21/24 任务完成记录。
