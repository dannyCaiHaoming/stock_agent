## Purpose

建立覆盖数据、推理、编排、风控和结果的可审计评估体系，使任何运行都能在原始时点重放并比较不同版本和 Agent 架构。

## ADDED Requirements

### Requirement: 每次运行必须生成完整 Decision Trace
系统 MUST 记录输入快照、研究计划、Agent 委派与输入、工具调用、证据版本、Agent 输出、CIO 草案、修订、Risk Report 和 Final Decision Plan。

#### Scenario: 审计历史决策
- **WHEN** 评审者打开任一历史 run_id
- **THEN** 可以重建从用户输入到最终输出的产物链和每个产物的生产者版本

### Requirement: 运行必须锁定关键版本
Decision Trace SHALL 记录模型及快照、Skill、Agent 配置、Schema、MCP Adapter、Risk Policy 和数据快照版本。

#### Scenario: 比较两个运行版本
- **WHEN** Replay 比较候选版本与生产版本
- **THEN** 评估报告明确列出所有版本差异，不把未知漂移归因于投资推理

### Requirement: Replay 必须遵守 point-in-time 边界
历史 Replay MUST 仅使用决策时点已经被系统获取的证据，不得访问后续修订、新闻、财报或市场结果作为研究输入。

#### Scenario: 回放历史财报期
- **WHEN** 后续存在修订财务数据
- **THEN** Replay 使用当时 `retrieved_at` 不晚于决策截止时点的版本

### Requirement: Eval 必须覆盖五类质量
系统 SHALL 分别评估确定性正确性、数据与证据质量、推理质量、决策及组合结果、多 Agent 架构增益，并为每项能力维护可重复的接受标准。

#### Scenario: 候选版本申请晋升
- **WHEN** 候选 Skill 或 Agent 配置进入回归评估
- **THEN** 评估同时报告 Schema/数学测试、引用正确性、反证与冲突处理、风险和组合指标以及消融结果

### Requirement: 市场结果不得作为唯一正确性标签
系统 MUST 将市场收益视为多期限、带噪声的 Outcome Observation，并结合 Thesis 事件实现、风险暴露、基准和交易成本分析决策质量。

#### Scenario: 正确推理后价格短期下跌
- **WHEN** Thesis 证据仍有效但短期相对收益为负
- **THEN** Eval 不自动把该决策标为推理错误，而是保留分解后的结果指标供评审

### Requirement: 新 Agent 必须通过消融评估
系统 SHALL 比较 CIO 单体、现有 Council 和新增 Agent 候选，在预先定义的留出集上验证增益和成本。

#### Scenario: 新 Agent 只增加一致性文本
- **WHEN** 新 Agent 提高 token 和延迟但未改善预定质量指标
- **THEN** 晋升门禁拒绝把该 Agent 加入默认 Council

