## ADDED Requirements

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
