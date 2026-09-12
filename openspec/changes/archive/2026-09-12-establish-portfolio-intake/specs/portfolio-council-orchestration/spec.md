## ADDED Requirements

### Requirement: Portfolio Council 必须接受全持仓研究 Handoff
`portfolio-council` SHALL 接受通过确定性校验的 `PortfolioHandoff`。Handoff 中每个持仓证券 MUST 进入后续研究计划，CIO 与 Risk MUST 接收同一完整 Portfolio；未确认、确认失效、不完整或研究集合与 Portfolio 不一致的输入 MUST 在任何研究 Agent 启动前失败。

Handoff 包含 ETF 或期权时，前置计划 MUST 保留这些资产并声明 `etf-research` 或 `options-research` 能力要求。若当前候选版本没有对应 Skill/Agent，运行 MUST 以明确能力缺口停止，不得将这些资产交给 Company Analyst 冒充专业覆盖，也不得仅研究普通股后声称组合完成。

#### Scenario: 十只持仓全部交接
- **WHEN** Handoff 包含十只已确认持仓
- **THEN** Council 前置计划包含十只研究对象且使用相同 Portfolio hash，不只处理前三只

#### Scenario: Draft 直接提交
- **WHEN** 调用方提交 Draft 或失效 Handoff
- **THEN** Council 在研究前拒绝输入并返回需要补全或确认的原因

#### Scenario: 多资产 Handoff 缺少研究能力
- **WHEN** Handoff 同时包含普通股、ETF 和期权，但当前运行版本只有公司研究能力
- **THEN** 前置检查保留全部研究对象并报告缺少 ETF/期权能力，不启动不完整的 Council

### Requirement: 大组合只能透明分批而不能减少研究范围
后续 Council 执行 MAY 使用有界并发或分批处理全部持仓，但 MUST 保存总数、已完成、待处理和失败项目。只要有持仓尚未形成规定的研究状态，系统 MUST NOT 声称全部组合研究完成；批大小和并发限制不得写成 Portfolio Schema 的持仓数量上限。

#### Scenario: 分两批研究十只持仓
- **WHEN** 执行资源一次只允许处理五只
- **THEN** 系统执行两个批次并最终覆盖十只；中间状态明确列出剩余五只

### Requirement: Intake Change 验收不得隐式启动研究链路
本 Change SHALL 止于 Handoff 与 Council 前置计划的确定性验证，不委派 Company Analyst、Independent Skeptic，不调用 CIO 综合，不获取市场 Evidence，也不生成投资报告。

#### Scenario: 验证输入能力
- **WHEN** 开发者执行 `establish-portfolio-intake` 限定验收
- **THEN** 系统证明所有输入持仓都进入计划后停止，不启动真实研究链路
