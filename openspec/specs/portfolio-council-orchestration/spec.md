# portfolio-council-orchestration Specification

## Purpose

定义 Codex 主线程作为 CIO 的组合决策协议，使专业研究可动态并行委派、独立完成、显式处理冲突并接受不可绕过的风险校验。

## Requirements

### Requirement: Portfolio Council 必须由 CIO 主线程主持
用户提供持仓后，`portfolio-council` Skill SHALL 使当前 Codex 主线程承担 CIO 职责，并保持用户目标、Portfolio Snapshot、Mandate 和完整决策上下文。

#### Scenario: 启动组合评审
- **WHEN** 用户提交有效持仓并调用 portfolio council
- **THEN** CIO 建立本次运行的研究问题、能力需求、证据时点和委派计划

### Requirement: CIO 必须按能力需求动态委派
CIO SHALL 根据持仓、数据缺口、决策影响和可并行性选择专业 Agent，不得在每次运行中机械调用所有 Agent。

#### Scenario: 持仓仅需公司基本面复核
- **WHEN** 市场和事件数据仍然有效且不存在相应缺口
- **THEN** CIO 可以只委派 Company Analyst 和 Skeptic，并在 Trace 中记录未调用其他能力的理由

### Requirement: 并行研究必须隔离初始结论
被并行委派的专业 Agent SHALL 在独立上下文中完成第一轮研究，CIO 在收集报告后负责比较共识、冲突和证据质量。

#### Scenario: 两个 Agent 给出相反判断
- **WHEN** Company Analyst 与 Skeptic 对关键 Thesis 存在实质冲突
- **THEN** CIO 明确记录冲突事实、双方证据、未解决部分及其对动作和置信度的影响

### Requirement: CIO 必须允许 NO_TRADE
当关键数据缺失或过期、证据存在无法解决的实质冲突、置信度不足或风险约束不可满足时，CIO SHALL 输出 `NO_TRADE`，不得为了完成流程而强制产生交易建议。

#### Scenario: 关键证据无法及时补齐
- **WHEN** CIO 判断缺失信息可能实质改变决策且当前运行无法获取
- **THEN** 草案使用标准原因码输出 `NO_TRADE` 并列出所需补充证据

### Requirement: 风险否决后最多允许一次修订
Risk Engine 对完整草案返回 `REVISE_REQUIRED` 时，CIO MAY 根据可行边界修订一次；修订后仍不合规则最终计划 MUST 为 `NO_TRADE` 或删除受否决的交易意图。

#### Scenario: 修订后仍违反仓位上限
- **WHEN** CIO 的第二版草案仍违反相同或其他硬约束
- **THEN** 系统停止循环并输出风险否决结果，不继续自动协商
