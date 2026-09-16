## MODIFIED Requirements

### Requirement: CouncilRequest 必须与 PortfolioHandoff 独立版本化
系统 SHALL 使用独立 `CouncilRequest` 表达研究请求，通过 `handoff_id`、`handoff_hash` 和 `portfolio_hash` 引用已确认的中立 `PortfolioHandoff v3`。研究请求 SHALL 承载研究问题、期限、范围、比较基准、组合约束引用及可选用户约束；持仓交接对象不得复制这些任务字段。对同一持仓创建不同请求 MUST NOT 改变持仓 hash 或要求重新确认账户状态。

系统 SHALL 从用户研究意图自动构造请求。新增版本的显式 `COMMON_STOCK_RESEARCH` 阶段允许 `holding_horizon`、`benchmark_id` 与 `mandate_artifact_id` 为 null，表示未知期限或本阶段不需要的组合字段；不得填入假值。期限未知时只作当前公司研究并说明限制，不输出期限性组合结论。旧版本及完整 Council 阶段仍按其必要输入约束校验，进入完整决策前必须补齐适用信息。

当前产品约定 `research_scope: ALL_INPUT_POSITIONS`，请求证券集合 MUST 与持仓全部 Position 一致，不得通过缩小请求范围隐瞒资产能力缺口。真正必需字段缺失时 SHALL 请求补充或安全停止，不把哨兵字符串写入持仓交接对象。

#### Scenario: 对同一持仓提出不同问题
- **WHEN** 用户先后对同一个持仓交接对象提出是否继续持有和未来三个月风险问题
- **THEN** 系统生成不同请求但引用相同持仓 hash，不要求重新确认账户状态

#### Scenario: 持有期限未知
- **WHEN** 用户未提供期限且调用显式普通股研究阶段
- **THEN** 新版请求记录 null 和研究限制，不猜测期限；完整决策阶段仍检查所需期限

#### Scenario: 研究请求遗漏部分持仓
- **WHEN** 请求声明 ALL_INPUT_POSITIONS 但证券集合少于确认持仓
- **THEN** 在 Agent 启动前拒绝请求

#### Scenario: 公司研究未指定比较基准和组合约束
- **WHEN** 用户已有确认持仓并仅请求公司研究
- **THEN** 系统自动构造新版阶段请求，相应非必需字段为 null，不要求用户为此额外准备文件

### Requirement: Portfolio Council 必须接受全持仓研究 Handoff
`portfolio-council` SHALL 接受通过确定性校验的中立 `PortfolioHandoff v3` 和独立 `CouncilRequest`，并在两者绑定通过后，根据每项持仓的 `asset_type` 和当前产品 Profile 建立 Research Capability 映射、能力可用性判断、研究计划、批次与 Agent 派发。Handoff 中每个持仓证券 MUST 进入后续规划，且任何已启动阶段都 MUST 保留同一完整 Portfolio hash；未确认、确认失效、不完整、请求绑定错误或 Portfolio hash 不一致的输入 MUST 在任何研究 Agent 启动前失败。

Handoff 包含 ETF 或期权时，Council 前置规划 MUST 保留这些资产并声明所需研究能力。若当前候选版本没有对应 Skill/Agent，默认完整 Council MUST 以明确能力缺口停止，不得要求 Intake 预先计算能力状态、不得将这些资产交给 Company Analyst 冒充专业覆盖，也不得仅研究普通股后声称组合完成。

显式普通股研究阶段 MAY 在完整 Council 尚不具备 ETF/期权能力时，对规划中标记为可用的普通股有界并行启动 Company Analyst，同时保存全部持仓覆盖清单、未研究资产及能力缺口。该阶段 SHALL 止于研究报告集，不自动启动 Skeptic、CIO 决策或 Risk；无论输入是否全为普通股，都不得把它视为完整 Council。混合资产未覆盖时 MUST 标记 PARTIAL_RESEARCH，不得把部分覆盖作为完整 Council、完整 Portfolio Risk 或候选版本晋升证据。原 planning_only 入口 MUST 保持零 Agent 调用。

#### Scenario: 十只持仓全部交接
- **WHEN** 中立 Handoff 包含十只已确认持仓且 CouncilRequest 声明 `ALL_INPUT_POSITIONS`
- **THEN** Council 从十只资产事实生成完整研究计划并使用相同 Portfolio hash，不只处理前三只

#### Scenario: Draft 直接提交
- **WHEN** 调用方提交 Draft、未知版本、失效 Handoff 或缺少 CouncilRequest
- **THEN** Council 在研究前拒绝输入并返回需要补全、迁移或确认的原因

#### Scenario: 多资产 Handoff 缺少研究能力
- **WHEN** Handoff 同时包含普通股、ETF 和期权，但当前运行版本只有公司研究能力且调用默认完整 Council
- **THEN** Council 自行识别并报告缺少 ETF/期权能力，保留全部研究对象且不启动不完整的完整 Council

#### Scenario: 显式执行普通股部分研究
- **WHEN** 同一混合资产 Handoff 进入显式普通股研究阶段
- **THEN** Council 只为普通股生成独立 Company Analyst 研究请求，保留 ETF/期权为能力缺口，并输出不得被解释为完整组合建议的覆盖状态和普通股研究产物

#### Scenario: 完整组合暂时不能估值
- **WHEN** ETF/期权价格或账户保证金缺失但对应普通股资料有效
- **THEN** 显式普通股阶段不执行完整组合估值作为前置门槛，保留完整持仓引用继续研究；完整决策阶段的核算与风险要求保持不变

#### Scenario: Intake Handoff 夹带能力状态
- **WHEN** v3 Handoff 包含能力状态、研究计划、研究问题、持有期限、benchmark 或 Mandate
- **THEN** Council 拒绝混合边界输入，不信任 Intake 代替 Council 生成的能力状态

#### Scenario: 公司研究入口直接承接确认持仓
- **WHEN** 用户通过 portfolio-council Skill 提出研究意图，已有有效确认 Handoff，并可选指定研究模型
- **THEN** Skill 接续确认结果，经现有宿主承载自动派生请求并准备公司资料，不要求用户转换持仓文件或传入 Gate；所选模型作用于本批 Analyst，父运行与评分模型分别记录，普通使用不隐式启动评分

#### Scenario: 资产覆盖与专业方向覆盖不同
- **WHEN** 所有普通股均已生成公司报告，但尚未开展市场、板块、图形或资金研究
- **THEN** 清单与报告仍明确本阶段专业范围，普通股全部处理不等于全维度研究完成，未研究方向不被当成无风险或公司研究的前置门槛

#### Scenario: 归集实际评价
- **WHEN** 某份公司报告的绑定有效 Eval 已完成
- **THEN** 覆盖清单关联该报告真实评价状态和产物路径，不继续显示未评估或借用不同报告的 PASS，其他持仓状态保持独立
