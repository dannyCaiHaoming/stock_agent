# controlled-learning-loop Specification

## Purpose

建立受控、离线和可人工审核的学习优化闭环，让系统能够从决策、反馈和市场结果中提出改进，同时禁止自动修改生产行为。

## Requirements

### Requirement: 学习面必须关联三类观测
学习优化面 SHALL 将 Decision Trace、Human Feedback 和多期限 Market Outcome 通过稳定 run_id 和 artifact_id 关联，同时保留原始记录和版本。

#### Scenario: 用户反馈证据错误
- **WHEN** 用户把某项结论标记为来源错误
- **THEN** 反馈记录关联具体 Claim、Fact、Agent 和运行版本，而不是只保存自由文本评价

### Requirement: Human Feedback 必须分类保存
系统 SHALL 区分事实错误、证据缺失、推理缺口、Mandate 误解、表达可用性和结果评价等反馈类型，并允许保留补充说明。

#### Scenario: 用户不同意投资观点
- **WHEN** 用户提交观点分歧但未指出事实错误
- **THEN** 系统将其保存为判断反馈，不自动修改事实或标记数据源失效

### Requirement: Reflection 只能生成 Improvement Proposal
学习面 MAY 分析失败模式并提出修改 Skill、Agent 配置、Schema、数据源或 Eval 的建议，但 MUST NOT 编辑生产文件、Risk Policy 或默认版本指针。

#### Scenario: Reflection 建议调整 Skill
- **WHEN** 多个 Replay 样本显示同一反证遗漏模式
- **THEN** 系统生成包含证据、根因假设、拟议变化、预期指标、退化风险和验证计划的 Improvement Proposal

### Requirement: 改进建议必须经过离线验证和人工晋升
任何 Improvement Proposal MUST 通过 point-in-time Replay、Regression、对抗样本和人工评审后，才能由开发控制面创建候选生产版本。

#### Scenario: 候选版本改善训练样本但损害留出集
- **WHEN** 回归评估发现候选版本在留出集或硬约束测试上退化
- **THEN** 晋升流程拒绝该候选并保留失败记录

### Requirement: 版本晋升必须可回滚
每次人工晋升 SHALL 生成包含旧版本、新版本、评估报告、批准人、时间和回滚条件的 Promotion Record。

#### Scenario: Shadow Run 出现严重回归
- **WHEN** 新版本在预定义监控指标上触发回滚条件
- **THEN** 系统可恢复上一已批准版本，且不删除新版本的 Trace 和评估记录
