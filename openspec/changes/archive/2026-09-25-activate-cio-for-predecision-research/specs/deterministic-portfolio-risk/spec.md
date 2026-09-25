## ADDED Requirements

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
