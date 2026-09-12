# portfolio-intake Specification

## Purpose

定义面向用户的持仓摄取与确认能力，使任意数量的普通股、ETF 与上市期权截图或手工持仓能够安全转换为可追溯的标准组合输入，并将所有输入证券保留为后续研究对象。

## Requirements

### Requirement: portfolio-intake 必须是独立产品 Skill
系统 SHALL 提供 `portfolio-intake` Skill，接受一张或多张持仓截图、手工描述或两者组合，输出 `PortfolioDraft`、集中澄清问题或已确认 `PortfolioHandoff`。该 Skill MUST NOT 研究公司、生成买卖动作、充当 CIO、调用研究 Agent 或自动启动 `portfolio-council`。

#### Scenario: 用户上传持仓截图
- **WHEN** 用户调用 `portfolio-intake` 并提供可读取截图
- **THEN** Skill 提取可见持仓事实并生成 Draft，而不是投资建议

#### Scenario: 用户手工输入组合
- **WHEN** 用户仅用文字提供持仓
- **THEN** Skill 使用相同 Draft 与确认流程，不要求图片或伪造图片来源

### Requirement: PortfolioDraft 必须保留不确定性和来源
`PortfolioDraft` MUST 允许缺失、歧义和冲突。每项持仓事实 MUST 可追溯到 `source_id`、`as_of`、`retrieved_at` 和来源内容 hash；截图不可见、被裁切或无法确定的字段 MUST 标记为 `MISSING`、`AMBIGUOUS` 或 `CONFLICTING`，不得猜测。用户修订 SHALL 作为新来源保存，并产生新的 Draft hash。

#### Scenario: 截图未显示现金
- **WHEN** 截图没有现金余额
- **THEN** Draft 标记现金缺失并集中请求补充，不能自动写成零

#### Scenario: 用户修正数量
- **WHEN** 用户纠正模型提取的持仓数量
- **THEN** Draft 保留原提取与用户修订来源，更新 hash，并使旧确认失效

### Requirement: 组合完整性必须基于用户声明的范围
Draft 与 Handoff MUST 声明 `portfolio_scope` 为 `BROKER_ACCOUNT` 或 `USER_DEFINED_PORTFOLIO`。`portfolio_complete` 只表示当前声明范围完整；系统不得把券商列表的一页伪装成完整账户，也不得强迫用户定义的组合证明整个券商账户完整。

#### Scenario: 券商截图还有下一页
- **WHEN** 用户声明 `BROKER_ACCOUNT` 且截图显示仍有未展示持仓
- **THEN** Draft 保持不完整，不能生成 Handoff

#### Scenario: 用户声明自定义组合
- **WHEN** 用户明确确认当前输入就是要分析的 `USER_DEFINED_PORTFOLIO`
- **THEN** 完整性按该输入集合判断，并在 Handoff 中保留范围限制

### Requirement: 所有输入持仓都必须是研究对象
Portfolio 与 Handoff Schema MUST NOT 设置持仓数量业务上限。Handoff MUST 声明 `research_scope: ALL_INPUT_POSITIONS`，研究证券集合必须与确认 Portfolio 的证券集合完全相同；不得截断、抽样、只取前三只或要求用户另选重点标的。

#### Scenario: 输入十只股票
- **WHEN** 用户确认包含十只支持股票的组合
- **THEN** Handoff 保留十只并将十只全部标记为后续研究对象

#### Scenario: 实现存在固定数量上限
- **WHEN** Schema、Skill 或交接器试图因持仓数量超过固定值而删除或拒绝合法持仓
- **THEN** 验收失败；资源控制只能通过透明分批处理，不能改变研究集合

### Requirement: Intake 必须区分普通股、ETF 与期权
Draft 与 Handoff MUST 使用可辨别资产结构支持 `COMMON_STOCK`、`ETF` 与 `OPTION`。ETF MUST 保留其自身证券身份，不得伪装为普通股；期权 MUST 保留标的证券、`CALL/PUT`、到期日、执行价、合约乘数、可选原始合约标识及带符号数量。数量为零 MUST 被拒绝；负数 MUST 表示已有空头仓位而不是输入错误。

#### Scenario: 组合包含杠杆 ETF
- **WHEN** 截图明确显示 SOXL 等 ETF 持仓
- **THEN** Draft 与 Handoff 将其记录为 `ETF` 并纳入全持仓计划，不静默删除或改写为普通股

#### Scenario: 组合包含空头 Put
- **WHEN** 截图显示数量为负的 Put 期权
- **THEN** Intake 保留负数量及期权身份；输入接受不代表允许新增空头交易

#### Scenario: 期权标识被截断
- **WHEN** 截图只显示部分合约标识或无法确定执行价
- **THEN** Draft 将对应字段标记为缺失/歧义并集中请求用户确认，不得猜测后生成 Handoff

### Requirement: 用户只需对当前 Draft 做一次集中确认
系统 MUST 汇总所有缺失和冲突后一次性向用户澄清，并展示完整确认摘要。只有用户明确确认当前 Draft hash、组合范围和全部持仓后才能生成 Handoff；普通“继续”、上传图片或请求研究不得视为确认。确认后任何事实变化 MUST 要求重新确认。

#### Scenario: 用户确认完整摘要
- **WHEN** 用户明确确认当前 Draft 内容和声明范围无误
- **THEN** Handoff 内嵌确认时间、Draft hash 和 `advisory_only: true`

#### Scenario: 确认后修改持仓
- **WHEN** 用户修改任何持仓或现金字段
- **THEN** 旧 Handoff 不再有效，系统返回新 Draft 等待一次新确认

### Requirement: Handoff 前必须进行最小确定性校验
系统 MUST 校验非零带符号数量、显式现金、基础币种、资产辨别字段、期权身份、重复证券、组合范围、来源闭合和研究集合等于全部输入持仓。现金未知不等于零；`cost_basis` MAY 缺失且不得单独阻断输入确认。未知证券或无法完整识别的合约 MUST 明确列出，不得静默删除。

#### Scenario: 明确零现金
- **WHEN** 用户或来源明确确认现金为零
- **THEN** 零值合法并保留来源，不与未知现金混淆

#### Scenario: 期权字段完整
- **WHEN** 用户确认期权标的、类型、到期日、执行价、合约乘数和数量
- **THEN** Handoff 保留完整期权结构并将该合约纳入研究计划

### Requirement: 输入接受不得扩大研究或交易权限
Intake SHALL 如实表示用户已有 ETF、期权与空头仓位，但 MUST NOT 因此授权建立新仓、卖空、衍生品交易或真实下单。研究计划 MUST 为每项资产声明所需能力；当前 Agent Package 缺少 ETF 或期权研究能力时 MUST 显式报告能力缺口，不得删去该持仓后声称全组合研究完成。

#### Scenario: Intake 接受期权但 Council 尚无 Options Skill
- **WHEN** 有效 Handoff 包含期权而当前候选版本没有对应研究能力
- **THEN** Council 前置检查保留该期权并报告能力缺口，不启动伪装成完整研究的运行

### Requirement: PortfolioHandoff 必须兼容 Council 输入边界
`PortfolioHandoff` SHALL 包含确认后的完整多资产 Portfolio、声明范围、期限、研究问题、Mandate/benchmark 引用、来源 lineage、Draft hash、每项 `required_capability` 和 `research_scope: ALL_INPUT_POSITIONS`。它 MUST 能在不启动 Council 的情况下单独验证，并不得包含截图推导的市场 Evidence、Thesis、动作或订单指令。

#### Scenario: 独立验证 Handoff
- **WHEN** 确认后的 Handoff 提交给交接校验器
- **THEN** 校验器确认 Portfolio 与研究证券集合完全一致、来源闭合且确认有效，不调用研究 LLM

### Requirement: 私人持仓不得进入仓库
真实截图、账户标识、私人 Draft 和 Handoff MUST 保存在仓库外。仓库内只允许通用实现、Schema、合成样例和脱敏验证记录；不得保存完整账户号、凭证或真实持仓。

#### Scenario: 使用真实截图
- **WHEN** 用户执行真实持仓 Intake
- **THEN** 原图与私人产物只写入外置目录，Git 工作区不出现其内容
