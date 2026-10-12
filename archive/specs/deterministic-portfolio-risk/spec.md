# deterministic-portfolio-risk Specification

## Purpose

提供独立、可重复和不可绕过的组合核算与硬风控能力，在不替代投资判断的前提下约束所有建议动作的可行性。

## Requirements

### Requirement: 持仓输入必须先规范化和核算
系统 MUST 在研究开始前解析证券标识、数量、现金、价格时点、基准和 Mandate，并验证重复持仓、未知标的、金额守恒和必要字段。

#### Scenario: 持仓包含无法映射的证券
- **WHEN** Security Master 无法唯一映射用户提交的标识
- **THEN** 系统不猜测标的，并返回输入无效或要求补充信息

### Requirement: Risk Engine 必须执行前置和后置两阶段检查
同一版本化 Risk Policy SHALL 支持研究前的风险预检和 CIO 草案后的最终校验；前置结果提供当前风险状态与可行边界，后置结果拥有最终否决权。

#### Scenario: CIO 形成草案前
- **WHEN** Portfolio Snapshot 通过输入验证
- **THEN** Risk Engine 返回当前现金、仓位、集中度、敞口、流动性和其他适用风险指标

#### Scenario: CIO 提交草案
- **WHEN** 草案包含一个或多个目标仓位范围
- **THEN** Risk Engine 计算建议前后指标并返回 `APPROVED`、`REVISE_REQUIRED` 或 `REJECTED`

### Requirement: 硬约束必须确定性且可解释
Risk Engine SHALL 仅执行可表述为会计恒等式、数学定义、数据质量要求或明确 Mandate 的硬约束，并为每项违规输出政策条款、输入、计算和原因码。

#### Scenario: 计划超过单一标的上限
- **WHEN** 计划后的目标仓位超过版本化 Mandate 上限
- **THEN** Risk Engine 返回具体违规、计算值和允许的最大可行边界

### Requirement: Risk Engine 不得进行主观投资判断
Risk Engine MUST NOT 根据商业质量、估值吸引力、新闻含义、市场情绪或模型生成的信心分数选择证券或创造投资 Thesis。

#### Scenario: 风险校验收到低置信度 Thesis
- **WHEN** CIO 草案的置信度较低但所有硬约束均满足
- **THEN** Risk Engine 不以主观置信度替代 CIO 决策，只校验明确政策；CIO 可自行选择 `NO_TRADE`

### Requirement: 风险否决不可被 Agent 覆盖
任何 Agent、Skill 或 CIO 输出均不得把 `REJECTED` 风险结果改写为通过；最终输出 MUST 保留原始 Risk Check Report 和 policy version。

#### Scenario: CIO 坚持被否决的交易
- **WHEN** CIO 文本结论与 Risk Engine 的 `REJECTED` 状态冲突
- **THEN** 最终结构化状态以风险否决为准，并记录该冲突

### Requirement: Risk 必须使用完整声明组合
当 Portfolio 来源于 Intake Handoff 时，Risk Engine 的前置核算和未来后置校验 MUST 使用用户确认的完整声明组合。传入持仓集合、现金或 Portfolio hash 被截断、抽样或与 Handoff 不一致时 MUST fail closed。

完整声明组合 MAY 包含 ETF、期权和带符号数量。Intake Risk 输入 MUST 保留这些事实；现有 Risk Policy 若不支持衍生品核算 MUST 明确 fail closed，不得丢弃期权、取数量绝对值或把输入接受解释为交易授权。

#### Scenario: 非前几只持仓造成集中度风险
- **WHEN** 第十只持仓导致组合违反明确集中度约束
- **THEN** Risk 仍识别该风险，不能因为分批或输入顺序而忽略

#### Scenario: Risk 只收到部分持仓
- **WHEN** Risk 输入少于 Handoff 的确认持仓集合
- **THEN** 核算失败并报告组合不完整，不产生看似合法的风险结果

#### Scenario: Risk 尚不支持期权核算
- **WHEN** 完整 Handoff 含期权而当前 Risk Engine 没有对应确定性计算能力
- **THEN** Risk 前置检查报告不支持并保留完整输入 hash，不以只计算普通股的结果冒充全组合风险


### Requirement: 正反研究综合不得伪造完整组合 Risk
本 Change 的 `PREDECISION_CIO_SYNTHESIS` 仅交付 `RESEARCH_SYNTHESIS`。该级别 SHALL 明确记录 `Risk=NOT_RUN` 和 `complete_portfolio_decision=false`，不得创建风险预检、风险通过结果或 `decision.json`。来源包的 DOWNSTREAM_READY 仅证明研究可供 CIO 综合，不证明当前现金、持仓或个人限制齐全；本阶段不为已清仓 MRVL 构造当前 PortfolioSnapshot 或默认 Mandate。既有 fixture Council 的 Risk 契约与运行能力 MUST 保持不变。

#### Scenario: 当前账户现金未用于历史研究
- **WHEN** MRVL 来源研究包合格而用户没有提供当前账户现金
- **THEN** 系统仍可进行非动作综合，Trace 标记 Risk 未运行，不推断账户资金

#### Scenario: 调用方要求风险通过的持仓建议
- **WHEN** 请求选择本阶段未发布的 `PORTFOLIO_ADVICE`
- **THEN** 模型前拒绝，不返回 `Risk=APPROVED` 或以研究综合代替建议

#### Scenario: 当前账户包含 ETF 或空头期权
- **WHEN** 用户只要求历史 MRVL 研究综合，当前组合另有 ETF 或空头期权
- **THEN** 本阶段不裁剪资产、不运行完整组合 Risk，也不要求补期权合约资料以完成 MRVL 研究

### Requirement: 研究级运行必须与风险级产物隔离
本阶段的研究级运行 SHALL 绑定原研究包、Gate、报告和 Trace，但 MUST NOT 进入 CIO 前风险预检或草案后 Risk。研究内容可讨论证券风险，却不得把投资风险解释等同于确定性组合硬检查。关闭本阶段建议入口 MUST NOT 关闭旧 fixture Council 的独立 Risk。

#### Scenario: 报告讨论经营风险
- **WHEN** CIO 在研究综合中解释 MRVL 的经营或市场风险
- **THEN** 报告仍标记 Risk NOT_RUN，不生成仓位可行区间或政策通过声明

#### Scenario: 旧完整 Council 仍运行 Risk
- **WHEN** 既有 fixture Council 按原契约形成决策草案
- **THEN** 继续执行其独立 Risk，不受本研究级阶段的入口收敛影响

### Requirement: 未验收建议代码不得作为可用风控能力暴露
若工作树存在仅服务本阶段 `PORTFOLIO_ADVICE` 的准备、CIO 动作草案或后置 Risk 实现，收尾时 MUST 从可调用宿主路径移除或在模型前确定性拒绝，并检查没有可被误认为正式建议的输出；不得仅删除文档条款却留下可用入口。与本阶段无关的通用 Risk Engine 和旧 fixture 规则不得为此改写。

#### Scenario: 内部调用绕过宿主参数
- **WHEN** 调用方直接尝试本阶段建议 finalizer 或准备命令
- **THEN** 在产生建议性产物前拒绝，不因宿主脚本隐藏选项就变成隐蔽可用能力

#### Scenario: 研究内容不能自证账户适配
- **WHEN** CIO 报告对 MRVL 的业务或原时点估值偏积极
- **THEN** 报告不据此声称当前组合硬检查通过或用户个人条件适配
