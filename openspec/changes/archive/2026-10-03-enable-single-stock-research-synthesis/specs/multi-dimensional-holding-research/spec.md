## MODIFIED Requirements

### Requirement: 研究阶段必须承接确认持仓并保持角色边界
系统 SHALL 提供显式多维研究阶段：持仓分支直接承接有效 PortfolioHandoff 与绑定 CouncilRequest，保留全部持仓且不限制数量，仅对普通股开展本次研究；非持仓分支直接承接已验证 SINGLE_STOCK_RESEARCH 请求，只研究目标普通股及其授权基准/同行/共享资料，不构造 Handoff。两分支均不要求用户重新准备 Evidence。系统 SHALL 按专业 Skill 分工并记录实际执行 Agent；公司研究仍归 Company Analyst，跨市场研究不得冒充公司结论。单独多维阶段 MUST NOT 自动启动 Skeptic、CIO 决策、交易或修改账户。

#### Scenario: 混合持仓进入新阶段
- **WHEN** 确认输入包含普通股、ETF 与期权
- **THEN** 普通股逐项研究，其他持仓保留未覆盖状态，输出标注研究资料包而非完整组合决策

#### Scenario: 单股非持仓进入多维研究
- **WHEN** 有效 ALB 单股请求与其 Company/来源资料进入本阶段
- **THEN** 复用原八维职责、资料准备与最小报告门禁，保留单股请求、目标和 cutoff 绑定，不引用其他任务或旧 MRVL 资料

## ADDED Requirements

### Requirement: 单股资料准备与独立反证必须保持输入模式闭合
单股资料准备、同行物化、维度报告、覆盖清单、独立反证与 PreDecisionResearchPackage SHALL 承接同一非持仓研究身份，并使用原同源、执行证明、引用、核心 coverage 及 DOWNSTREAM_READY 门禁。Skeptic 首轮 MUST 从该请求及允许的原始证据独立构造，不能读正向报告、摘要或历史观点；辅助维度来源受限不等于核心上游就绪。持仓分支、旧报告及原阶段停止点保持兼容。

#### Scenario: 八维与反证同源闭合
- **WHEN** ALB 八维结果和逐股反证均完成且满足原准入
- **THEN** 交接包保留非持仓输入身份并可供显式 CIO 重验；不会伪造 portfolio_hash 或完成组合建议

#### Scenario: 核心缺口或反证失败
- **WHEN** 核心正向覆盖未就绪或 Skeptic 为证据不足、超时、失败
- **THEN** 仍保存实际逐任务状态和失败产物，但不形成可交付 CIO 的成功综合
