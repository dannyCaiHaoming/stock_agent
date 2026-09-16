## ADDED Requirements

### Requirement: MVP 开发授权不得被拆成逐步骤批准
用户明确批准 apply 后，开发 Agent SHALL 连续完成该 Change 既定任务、普通错误修复和聚焦确定性验证。仅当需要新增权限、执行破坏性操作、使用付费服务或凭证、改变已批准范围或安全契约、遇到无法自行解除的真实阻断，或准备最终归档与推送时，才 MUST 请求用户决定；阶段汇报、文件修改、普通测试失败和下一项任务不得单独触发批准。

#### Scenario: 实现过程中出现普通断言错误
- **WHEN** 修复不改变规格、权限、外部状态或安全边界
- **THEN** 开发 Agent 自行修复并继续聚焦验证，不暂停等待“继续”

#### Scenario: 准备归档并推送
- **WHEN** Change 任务与限定验收均完成
- **THEN** 开发 Agent提交完成摘要并等待一次明确人工完成批准，未获批准不归档或推送

### Requirement: Agent Package MVP 与候选晋升必须使用不同完成标准
`DEMO_SCAFFOLD` 的 Change 完成 SHALL 只证明 Agent Package 静态拓扑绑定、输入、只读 Tool Port、角色响应、数据传递、Risk 和最终输出可运行。独立 Reviewer、真实 LLM、语义评分、Replay、Regression、Calibration、Ablation 与 Promotion MUST NOT 成为该 Demo Change 的默认完成条件；当用户明确申请真实产品验收或候选晋升时，仍按对应规格执行，不能继承 Demo PASS。

#### Scenario: Demo MVP 满足完成条件
- **WHEN** 受影响聚焦测试和一次完整 Demo 均通过，且安全边界没有被放宽
- **THEN** Change 可以提交人工完成批准，不因缺少发布级证据继续扩建验证平台
