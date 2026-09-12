## ADDED Requirements

### Requirement: CouncilRequest 必须与 PortfolioHandoff 独立版本化
系统 SHALL 使用独立 `CouncilRequest` 表达一次多 Agent 研究请求。它 MUST 通过 `handoff_id`、`handoff_hash` 和 `portfolio_hash` 引用一个已确认的中立 `PortfolioHandoff v3`，并承载 `research_question`、`holding_horizon`、`research_scope`、`benchmark_id`、`mandate_artifact_id` 和可选用户约束。`PortfolioHandoff` 不得复制这些任务字段；对同一 Handoff 创建不同 CouncilRequest MUST NOT 改变 Handoff hash 或要求用户重新确认账户状态。

当前产品约定 `research_scope: ALL_INPUT_POSITIONS`，因此 CouncilRequest 的研究证券集合 MUST 与 Handoff 的全部 Position 完全一致，不得只选部分持仓。CouncilRequest 的缺失任务字段必须由 Council 在 Agent 启动前请求补充或安全停止，不得通过修改 Handoff 填充哨兵字符串。

#### Scenario: 对同一持仓提出不同问题
- **WHEN** 用户先后对同一个 Handoff 提出“是否继续持有”和“未来三个月主要风险”两个研究问题
- **THEN** 系统生成两个不同 CouncilRequest，但两者引用相同 Handoff/Portfolio hash 且不要求重新确认持仓

#### Scenario: 持有期限未知
- **WHEN** 用户尚未提供持有期限
- **THEN** CouncilRequest 将期限保留为明确未知或停在补充输入状态，不把 `UNSPECIFIED_REQUIRES_COUNCIL_CLARIFICATION` 等哨兵文本写入 PortfolioHandoff

#### Scenario: 研究请求遗漏部分持仓
- **WHEN** CouncilRequest 声明 `ALL_INPUT_POSITIONS` 但其研究证券集合少于 Handoff
- **THEN** 确定性校验在任何 Agent 前拒绝该请求

### Requirement: Council 规划只能消费确认状态与研究请求的组合
Council 的最小确定性规划接缝 SHALL 同时消费一个有效 `PortfolioHandoff v3` 和与之绑定的有效 `CouncilRequest`，再根据自身版本和 Product Profile 产生能力映射、能力缺口、批次及 Research Plan。规划产物 MUST 标记 `planning_only: true`，保留输入 hash 和全部持仓覆盖状态；它不得获取研究 Evidence、启动 Agent、生成 Thesis、动作、Risk 结果或最终报告。

#### Scenario: 只生成多资产研究计划
- **WHEN** 有效 Handoff 包含普通股、ETF 和期权且 CouncilRequest 覆盖全部持仓
- **THEN** 规划接缝输出相应能力需求和缺口，保持零 Agent/LLM 调用且不产生投资结论

#### Scenario: 研究请求绑定错误 Handoff
- **WHEN** CouncilRequest 的 Handoff 或 Portfolio hash 与实际 Handoff 不一致
- **THEN** 规划接缝 fail closed，不生成 Research Plan

## MODIFIED Requirements

### Requirement: Portfolio Council 必须接受全持仓研究 Handoff
`portfolio-council` SHALL 接受通过确定性校验的中立 `PortfolioHandoff v3` 和独立 `CouncilRequest`，并在两者绑定通过后，根据每项持仓的 `asset_type` 和当前产品 Profile 建立 Research Capability 映射、能力可用性判断、研究计划、批次与 Agent 派发。Handoff 中每个持仓证券 MUST 进入后续规划，CIO 与 Risk MUST 接收同一完整 Portfolio；未确认、确认失效、不完整、请求绑定错误或 Portfolio hash 不一致的输入 MUST 在任何研究 Agent 启动前失败。

Handoff 包含 ETF 或期权时，Council 前置规划 MUST 保留这些资产并声明所需研究能力。若当前候选版本没有对应 Skill/Agent，Council MUST 以明确能力缺口停止，不得要求 Intake 预先计算能力状态，不得将这些资产交给 Company Analyst 冒充专业覆盖，也不得仅研究普通股后声称组合完成。

#### Scenario: 十只持仓全部交接
- **WHEN** 中立 Handoff 包含十只已确认持仓且 CouncilRequest 声明 `ALL_INPUT_POSITIONS`
- **THEN** Council 从十只资产事实生成完整研究计划并使用相同 Portfolio hash，不只处理前三只

#### Scenario: Draft 直接提交
- **WHEN** 调用方提交 Draft、未知版本、失效 Handoff 或缺少 CouncilRequest
- **THEN** Council 在研究前拒绝输入并返回需要补全、迁移或确认的原因

#### Scenario: 多资产 Handoff 缺少研究能力
- **WHEN** Handoff 同时包含普通股、ETF 和期权，但当前运行版本只有公司研究能力
- **THEN** Council 自行识别并报告缺少 ETF/期权能力，保留全部研究对象且不启动不完整的 Council

#### Scenario: Intake Handoff 夹带能力状态
- **WHEN** v3 Handoff 包含能力状态、研究计划、研究问题、持有期限、benchmark 或 Mandate
- **THEN** Council 拒绝混合边界输入，不信任 Intake 代替 Council 生成的能力状态

### Requirement: Intake Change 验收不得隐式启动研究链路
本 Change SHALL 止于统一 Portfolio Draft、账户快照、用户确认、中立 Handoff v3、独立 CouncilRequest 和 `planning_only` Research Plan 的确定性验证，不委派 Company Analyst、Independent Skeptic 或任何按资产划分的输入 Agent，不调用 CIO 综合、获取市场 Evidence、执行 Risk 或生成投资报告。

#### Scenario: 验证输入能力
- **WHEN** 开发者执行 `refine-unified-portfolio-intake` 限定验收
- **THEN** 系统证明股票、ETF、期权、现金及可见保证金字段完整进入中立 Handoff，并可与独立 CouncilRequest 生成只读规划输出后停止，不启动真实研究链路
