## REMOVED Requirements

### Requirement: Change 验收必须包含真实 Codex LLM 运行证据

**Reason**: 该标题把所有 Change 都描述为必须运行真实 LLM，与新增的纯 Agent Package 装配 Demo 层级冲突，也容易把产品运行和候选晋升要求带入普通骨架开发。

**Migration**: 使用下方“Change 验收必须匹配其声明的运行层级”；真实 fixture/live 研究与候选晋升仍保留真实 Codex LLM 证据要求，只有明确标记的 `DEMO_SCAFFOLD` 可以使用零 LLM 验收。

## ADDED Requirements

### Requirement: Change 验收必须匹配其声明的运行层级
单元测试和确定性 Adapter MAY 验证 Agent Package 的数据流与安全边界。仅声明交付 `DEMO_SCAFFOLD` 的 Change MUST 至少成功执行一次完整 Demo，并保存 Package 拓扑、角色输入输出、Tool Port 调用、Dispatch、失败传播、Risk 结果和最终产物；它不需要真实 Codex LLM、语义 Eval、Execution Replay、Regression、Calibration、Ablation 或 Promotion 证据。任何声明真实 fixture/live 研究、真实 Skill 推理、Codex 主线程 CIO、真实 Subagent 或候选版本晋升的 Change 仍 MUST 提供对应的真实 Codex LLM 与既有分层验收证据，不得用 Demo 替代。

#### Scenario: 只有确定性 Demo 通过
- **WHEN** Agent Package Change 的声明范围仅为 `DEMO_SCAFFOLD`，聚焦契约测试和完整 Demo 均通过
- **THEN** 可以认定多 Agent 骨架、实际 Package 静态绑定和数据流完成，但结论必须明确排除真实研究质量、真实 Skill 执行、主线程 CIO、Subagent 激活和候选晋升

#### Scenario: 使用 Demo 证明真实 Council
- **WHEN** Change 声称真实 fixture/live Agent、Skill、主线程 CIO 或 Subagent 已激活，却只提供 Demo Adapter 产物
- **THEN** 真实产品验收保持失败，不得把 synthetic 产物改标为真实运行

### Requirement: 高级验证能力必须由显式目的触发
Runtime Eval、Execution Replay、完整 Regression、Calibration、Ablation 和 Promotion Gate SHALL 保留为显式维护或候选晋升能力，但 MUST NOT 被普通实现、聚焦测试、Demo 完成检查、独立差异阅读或归档准备隐式启动。默认开发入口 MUST 在没有显式子命令和对应授权时保持这些能力未运行。

#### Scenario: 普通 Agent 数据流修改完成
- **WHEN** 开发者完成 `DEMO_SCAFFOLD` 范围内的实现和聚焦测试
- **THEN** 默认流程只运行受影响测试与一次 Demo，不自动追加真实 LLM、Replay、Regression、Ablation 或 Promotion

#### Scenario: 用户申请候选版本晋升
- **WHEN** 用户明确进入 Promotion 流程
- **THEN** 系统可以按现有晋升规格调用所需高级验证，且不能把此前未运行状态当作 PASS
