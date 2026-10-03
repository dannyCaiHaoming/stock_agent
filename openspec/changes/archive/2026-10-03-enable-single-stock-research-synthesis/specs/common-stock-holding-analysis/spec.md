## MODIFIED Requirements

### Requirement: 普通股持仓研究必须具有完整 Capability Contract
系统 SHALL 为普通股研究定义统一的 Input、Tool/Data、Skill/Reasoning、Structured Output 和 Eval。持仓输入 MUST 来自通过确定性校验且相互绑定的 `PortfolioHandoff v3` 与 `CouncilRequest`；单股非持仓输入 MUST 来自已验证的 `SINGLE_STOCK_RESEARCH` 请求并保留独立输入类型与请求绑定。事实 MUST 来自本次运行已冻结且通过 point-in-time Gate 的 Evidence；研究 MUST 由真实 Company Analyst LLM 使用专业 Skills 完成；输出 MUST 是可验证的 `EquityResearchReport`。两个输入分支不能互相伪装，单股研究不要求账户确认。

#### Scenario: 从确认持仓启动普通股研究
- **WHEN** 有效 Handoff 和 CouncilRequest 包含一只具备公司研究能力的普通股
- **THEN** 系统为该证券建立独立研究请求，并能从同一输入、冻结 Evidence、专业 Skills、结构化输出和 Eval 追溯完整能力链

#### Scenario: 输入未确认或绑定错误
- **WHEN** 持仓 Handoff 未确认、CouncilRequest 引用错误 hash，或任一分支的证券不属于其有效输入
- **THEN** 系统在获取研究 Evidence 或启动 Company Analyst 前 fail closed

#### Scenario: 非持仓单股输入
- **WHEN** 用户提供已验证 ALB 单股研究请求但没有 Handoff
- **THEN** 同一个 Company Analyst 在独立证券上下文中研究，报告保留单股输入身份，不填持仓或盈亏

### Requirement: EquityResearchReport 必须是公司专属结构化产物
每份 `EquityResearchReport` MUST 绑定 `run_id`、`invocation_id`、对应输入类型的可信研究绑定、证券身份、decision cutoff、Agent 与 Skill 版本；持仓分支保留原 Portfolio/CouncilRequest hash，非持仓分支绑定单股请求 hash 而不伪造持仓字段。报告 SHALL 包含研究状态、研究范围、公司概览、商业模式、Thesis 支柱、财务表现、资本配置、竞争地位、估值、公司级催化剂、主要风险、反证、失效条件、观察指标、假设、数据缺口、置信度及理由、Evidence References 和计算产物引用。所有事实和解释中的 Evidence References MUST 逐字属于当前 Gate 允许集合。

#### Scenario: 报告进入下游
- **WHEN** Company Analyst 返回一份完整普通股报告
- **THEN** Schema、Evidence Closure 和绑定校验通过后，CIO 无需人工改写即可消费该报告；第一轮 Independent Skeptic 仅消费自身 Gate 合格 Evidence，不接收 Analyst 报告或摘要

#### Scenario: 报告只有泛化观点
- **WHEN** 报告缺少公司特定 Thesis、证据、估值状态、失效条件或数据缺口说明
- **THEN** 普通股研究 Eval 判定其不能满足该能力的完成标准，即使基础 JSON 语法有效
