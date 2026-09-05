## 1. 建立三平面治理

- [x] 1.1 创建根 `AGENTS.md`，定义 OpenSpec、实现、测试、评审和版本晋升规则，并通过治理检查确认开发控制面不授予 runtime 投资决策权限
- [x] 1.2 创建 `product/AGENTS.md`，定义 CIO、runtime Agent、只读工具、`NO_TRADE`、禁止下单和禁止生产修改规则，并通过权限场景测试验证写操作被拒绝
- [x] 1.3 创建最小的 `dev_architect`、`dev_contracts`、`dev_eval` 和 `dev_reviewer` 配置，并验证每个开发 Agent 的职责和允许工具与根治理规则一致
- [x] 1.4 建立 Capability Contract 模板和架构评审清单，并用一个完整示例验证 Input、Tool/Data、Skill/Reasoning、Structured Output 和 Eval 五部分均为必填
- [x] 1.5 建立版本清单格式，覆盖模型、Skill、Agent、Schema、MCP Adapter 和 Risk Policy，并验证缺少任一版本时候选运行无法进入晋升流程

## 2. 定义核心数据与产物契约

- [x] 2.1 定义所有 Artifact 的公共信封、稳定 ID、生产者和输入血缘字段，并通过 Schema 测试验证跨 Artifact 引用可解析
- [x] 2.2 定义 `FactEnvelope`、`Claim`、`Assumption` 和 `EvidenceBundle` Schema，并验证每项事实缺失 `source_id`、`as_of` 或 `retrieved_at` 时校验失败
- [x] 2.3 定义 `PortfolioInput`、`PortfolioSnapshot`、`Mandate` 和 Security Identifier Schema，并通过有效、重复、未知和歧义标的样本验证输入行为
- [x] 2.4 定义 `AgentResearchReport`、`ValuationAssessment`、`CatalystMap` 和 `CounterThesisReport` Schema，并验证事实、假设、反证和数据缺口可以区分
- [x] 2.5 定义 `CouncilDraftDecision`、`RiskCheckReport` 和 `FinalDecisionPlan` Schema，并验证动作枚举、目标仓位范围、风险状态及 `advisory_only` 约束
- [x] 2.6 定义 `DecisionTrace`、`HumanFeedback`、`MarketOutcome`、`ImprovementProposal` 和 `PromotionRecord` Schema，并验证它们可通过 run_id 和 artifact_id 关联

## 3. 建立 Point-in-time Evidence 平面

- [x] 3.1 定义 provider-neutral 的 Security Master、Market Data、Fundamentals、Filings/News 和 Evidence Query MCP 契约，并通过工具清单测试确认全部为只读操作
- [x] 3.2 创建可重复的 fixture/reference adapter，覆盖正常、过期、缺失、冲突和后续修订数据，并验证固定输入生成稳定的 Evidence Artifact
- [x] 3.3 实现数据标准化和 provenance 封装，并通过契约测试验证原始来源、单位、时区、币种和内容哈希不会在转换中丢失
- [x] 3.4 实现追加式 Evidence Store 和双时间索引，并验证新修订不会覆盖旧版本且可按 `as_of` 与 `retrieved_at` 查询
- [x] 3.5 实现版本化 freshness 和关键事实冲突检测，并通过边界样本验证检测层只标记问题、不替 LLM 解释投资影响
- [x] 3.6 实现 Claim-Evidence Closure 校验，并验证无依据且未标为假设的实质 Claim 不能进入 CIO 综合阶段
- [x] 3.7 增加禁止券商、订单和账户写工具的权限测试，并验证运行时工具发现结果中不存在可执行交易能力

## 4. 建立持仓核算和确定性 Risk Kernel

- [x] 4.1 实现持仓规范化、证券映射、价格时点和金额守恒验证，并通过重复持仓、未知标的、缺失现金和价格过期样本
- [x] 4.2 实现现金、权重、行业敞口、集中度、换手、流动性和模拟成本等确定性计算，并使用 golden cases 验证数值
- [x] 4.3 实现版本化 Mandate 与 Risk Policy 契约，并验证每条政策可映射到数学定义、数据质量要求或明确硬约束
- [x] 4.4 实现同一 Risk Policy 的前置预检和后置校验接口，并验证两者在相同输入上使用相同政策版本和指标定义
- [x] 4.5 实现 `APPROVED`、`REVISE_REQUIRED`、`REJECTED`、feasible bounds 和 veto codes，并通过仓位、现金、集中度和流动性违规样本验证
- [x] 4.6 增加 Risk Engine 属性测试和极端边界测试，并验证任何硬约束违规均不能返回 `APPROVED`
- [x] 4.7 增加职责边界测试和评审检查，验证 Risk Engine 不包含公司质量、估值吸引力、新闻含义或买卖选择规则

## 5. 实现首批专业研究 Capability

- [x] 5.1 建立 Capability Registry 和能力级 Eval fixture，并验证未定义五段式合同或 Eval 的能力不能注册为生产能力
- [x] 5.2 创建 `evidence-grounding` Skill，定义事实、假设、引用、冲突、时效和停止条件，并用有依据与无依据样本验证输出
- [x] 5.3 创建 `company-research` 和 `valuation` Skills，将数值计算委派给确定性工具，并通过研究报告 Schema 和估值 golden cases 验证边界
- [x] 5.4 创建 `runtime_company_analyst`，仅授予所需只读数据和研究 Skills，并验证其输出完整 Agent Research Report 而不决定全组合动作
- [x] 5.5 创建 `counter-thesis` Skill 和 `runtime_skeptic`，并验证第一轮研究上下文不包含其他 Agent 结论
- [x] 5.6 创建 `catalyst-analysis` Skill 和 `runtime_market_catalyst`，并通过事件时点、行情 freshness 和流动性样本验证输出
- [x] 5.7 为三个 runtime Agent 建立失败、超时、缺失证据和低置信度场景，并验证它们返回结构化缺口而非编造结论

## 6. 实现 Portfolio Council 纵向切片

- [x] 6.1 在首个可运行能力存在后创建 Codex Agent Package manifest，并验证只打包产品级 Skills、runtime Agents、只读 MCP 和必要契约
- [x] 6.2 创建 `portfolio-council` Skill，定义 CIO 输入验证、研究截止时点、能力选择、委派预算和停止条件，并通过 Skill contract tests
- [x] 6.3 实现 CIO 动态委派和第一轮上下文隔离，并验证简单场景不会机械调用全部 Agent、并行 Agent 互不可见结论
- [x] 6.4 实现结构化报告收集、共识与冲突综合，并通过相反 Thesis 样本验证 CIO 保留双方证据和未解决部分
- [x] 6.5 实现 Draft Decision 到 Risk Engine 的后置协议和最多一次修订状态机，并验证第二次不合规时停止循环
- [x] 6.6 实现 `BUY / ADD / HOLD / TRIM / EXIT / NO_TRADE` Final Decision Plan 生成和 Schema 校验，并验证目标仓位范围、证据、反证、失效条件和 Risk Report 完整
- [x] 6.7 增加 `NO_TRADE` 标准原因码和重新评估条件，并通过过期、缺失、冲突、低置信度、输入无效和风险否决场景验证
- [x] 6.8 增加输出安全检查，验证所有结果含 `advisory_only: true` 且没有订单标识、账户凭据、发送状态或外部写调用
- [x] 6.9 使用 fixture Portfolio 和 Evidence 运行首个 CIO + Company Analyst + Skeptic + Risk Engine 端到端场景，并验证完整 Artifact 链可追溯

## 7. 建立 Decision Trace、Replay 和 Eval

- [x] 7.1 实现 Decision Trace 追加记录，覆盖输入、委派、工具调用、Evidence、Agent 报告、CIO 草案、修订、Risk Report 和最终输出，并通过完整性测试
- [x] 7.2 实现运行版本锁定，记录模型快照、Skill、Agent、Schema、MCP Adapter、Risk Policy 和数据快照，并验证版本缺失会使 Replay 不可晋升
- [x] 7.3 实现 point-in-time Replay 数据选择，并通过后续财报修订和未来新闻样本验证 `retrieved_at <= decision_cutoff`
- [x] 7.4 建立确定性测试套件，覆盖 Schema、持仓数学、Risk Engine、freshness、冲突和 Evidence Closure，并验证所有硬门禁可重复
- [x] 7.5 建立证据和推理 Eval，覆盖引用支持度、Thesis、Counter Thesis、冲突处理、失效条件和置信度校准，并用人工标注样本验证 grader
- [x] 7.6 建立多期限 Outcome Eval，报告相对基准、回撤、暴露、换手、模拟成本和 Thesis 事件实现，并验证单次涨跌不会成为唯一标签
- [x] 7.7 建立 CIO 单体、不同 Agent 组合和完整 Council 的消融流程，并验证新增 Agent 同时报告质量增益、token 和延迟成本
- [x] 7.8 定义候选版本晋升门禁和留出集策略，并验证训练集改善但留出集或硬约束退化的候选被拒绝

## 8. 建立受控学习优化面

- [x] 8.1 实现分类 Human Feedback 记录，并验证事实错误、证据缺失、推理缺口、Mandate 误解、可用性和观点分歧可分别关联到 Artifact
- [x] 8.2 实现多期限 Market Outcome 观察，并验证 Outcome 只在决策后追加且不会进入历史研究输入
- [x] 8.3 构建 point-in-time Attribution Dataset，并验证每个样本保留原始 Trace、版本、反馈、基准和市场结果
- [x] 8.4 创建 Reflection 流程，仅输出包含证据、根因假设、拟议变化、预期指标、退化风险、Replay 和回滚计划的 Improvement Proposal
- [x] 8.5 增加学习面权限测试，验证 Reflection 无法编辑生产 Skill、Agent、Schema、Risk Policy 或默认版本指针
- [x] 8.6 实现 Improvement Proposal 的 Replay、Regression、对抗样本和 Shadow Run 记录流程，并验证失败候选不会晋升
- [x] 8.7 实现人工 Promotion Record 和版本回滚流程，并验证回滚恢复上一批准版本且保留全部 Trace 和评估记录

## 9. 完成系统验收与后续拆分

- [x] 9.1 执行产品包权限审计，并验证 runtime Agent 只有明确列出的 Skills、只读 MCP 和结构化输出能力
- [x] 9.2 执行架构边界评审，并验证 Python 模块只包含数据、数学、核算、硬风控、验证和存储职责
- [x] 9.3 运行包含正常建议、关键数据过期、来源冲突、Risk 修订成功和最终否决的端到端验收集，并验证每个场景产生预期结果
- [x] 9.4 生成首个版本化 Capability Map 和 Eval 报告，并验证三个 runtime Agent 均有可测职责且无空角色
- [x] 9.5 记录后续独立 Change：首发市场与生产数据供应商适配、部署 Mandate 数值、额外研究能力，并验证它们不阻塞本 Change 的 fixture/reference 验收
- [x] 9.6 运行严格 OpenSpec、Schema、测试、Eval 和人工 Review 门禁，并在全部通过后生成候选版本而不启用任何真实交易能力
