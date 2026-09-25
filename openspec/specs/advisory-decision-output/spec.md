# advisory-decision-output Specification

## Purpose

定义可供用户审阅但不可直接执行的组合建议格式，使动作、仓位范围、证据、反证、失效条件和风险状态完整且机器可验证。

## Requirements

### Requirement: 最终计划必须使用结构化动作集合
每个被评估标的的最终动作 SHALL 为 `BUY`、`ADD`、`HOLD`、`TRIM`、`EXIT` 或 `NO_TRADE`，并包含适用的目标仓位范围、时间范围和建议理由。

#### Scenario: 输出增加持仓建议
- **WHEN** 最终动作是 `ADD`
- **THEN** 输出包含当前仓位、目标仓位范围、最大建议名义金额、时间范围和最终 Risk 状态

### Requirement: 最终计划必须展示证据和失效条件
非 `NO_TRADE` 的建议 MUST 包含主要 Thesis、Counter Thesis、关键证据引用、未解决不确定性和可观察的失效条件。

#### Scenario: 用户审阅买入建议
- **WHEN** 用户查看 `BUY` 建议
- **THEN** 用户可以沿 Evidence References 追溯至带 `source_id` 和 `as_of` 的事实，并看见何种事件会使 Thesis 失效

### Requirement: NO_TRADE 必须是一等结果
系统 SHALL 使用标准原因码和人类可读解释表达 `NO_TRADE`，并区分数据不足、证据冲突、低置信度、输入无效、Mandate 违规、流动性限制和风险否决。

#### Scenario: 数据过期导致不交易
- **WHEN** 关键证据过期且不能在本次运行中更新
- **THEN** 输出 `NO_TRADE`、`STALE_DATA` 原因码、受影响事实和重新评估条件

### Requirement: 输出必须明确禁止真实执行
所有 Final Decision Plan MUST 标记为 `advisory_only`，不得包含可由券商直接执行的授权、账户凭据、订单标识或已发送状态。

#### Scenario: 生成最终交易计划
- **WHEN** Risk Engine 批准一个或多个建议动作
- **THEN** 系统仅返回研究性计划，不调用任何外部写工具或交易接口

### Requirement: 输出必须通过 Schema 和证据校验
系统 MUST 在保存或展示结果前验证公共信封、动作枚举、Evidence References、Risk Report、版本信息和必要字段；每个 Evidence Reference MUST 存在于本次运行通过 point-in-time Gate 的 Evidence Bundle 中。数据不足、过期、投资冲突、低置信度和 Risk veto MAY 形成契约有效的 `SAFE_NO_TRADE`；Schema、Evidence Closure、运行血缘或必要 Risk Report 校验失败 MUST 形成 `FAILED_VALIDATION`，不得输出伪完整获批计划或将系统错误改写为投资性 `NO_TRADE`。

#### Scenario: 最终计划缺失风险报告
- **WHEN** CIO 生成的计划没有可验证的 Risk Check Report
- **THEN** 运行进入 `FAILED_VALIDATION` 并返回结构化系统错误，不得生成 `decision.json` 或 `report.md`

#### Scenario: 最终计划引用未知 Evidence
- **WHEN** 任一决策引用本次允许 Evidence IDs 中不存在的 ID
- **THEN** 运行进入 `FAILED_VALIDATION`，且不得保存任何 `decision.json` 或 `report.md`

### Requirement: 每次完成的 Council 运行必须输出三个一致产物
每次以 `COMPLETED` 或 `SAFE_NO_TRADE` 终止的 fixture Council 运行 MUST 在指定输出目录保存 `decision.json`、`report.md` 和 `decision_trace.json`。`decision.json` SHALL 是机器可验证的最终建议，`report.md` SHALL 是对同一建议、证据、冲突、失效条件和 Risk 结果的人类可读呈现，`decision_trace.json` SHALL 提供完整运行血缘。以 `FAILED_VALIDATION` 终止的运行 MUST 保存 `decision_trace.json` 和 `run_error.json`，且 MUST NOT 保存 `decision.json` 或 `report.md`。

#### Scenario: 正常研究运行完成
- **WHEN** Evidence、专业报告、CIO 草案和 Risk Result 均通过验证
- **THEN** 三个文件共享同一 `run_id`，动作、Evidence IDs、Risk 状态和 `advisory_only` 标志相互一致

#### Scenario: 数据不足形成安全 NO_TRADE
- **WHEN** 有效输入因 Gate 后无可用事实或 CIO 的证据判断形成合法 `SAFE_NO_TRADE`
- **THEN** 三个最终文件共享同一 `run_id` 和标准 NO_TRADE 原因，且 Trace 表明它不是 Schema 或引用校验失败的替代结果

#### Scenario: 运行因悬空引用失败
- **WHEN** 最终引用闭包校验失败
- **THEN** 输出目录只保存可审计的 `decision_trace.json` 和 `run_error.json`，不存在 `decision.json` 或 `report.md`

### Requirement: 报告渲染不得引入新的投资事实或结论
`report.md` MUST 仅渲染已验证的 `decision.json` 和其引用产物，不得通过模板、后处理或硬编码添加新的 Thesis、Action、Confidence、Evidence ID 或 Risk 结论。对于 `SAFE_NO_TRADE`，报告只需映射适用的证据缺口、冲突、原因码、Risk 状态和重新评估条件，不得要求虚构交易 Thesis。

#### Scenario: 比较机器决策和人类报告
- **WHEN** 验收器比较 `decision.json` 与 `report.md`
- **THEN** 报告中的动作、核心 Thesis、Evidence IDs、失效条件和 Risk 状态均可映射回机器决策且不存在新增事实

### Requirement: Council 决策条件必须来自单一规范契约
系统 MUST 维护一个版本化、机器可读的 canonical decision contract，作为 CIO 动作条件、JSON Schema 条件分支、运行时确定性校验和 CIO 可见示例的唯一规范来源。`action == NO_TRADE` 时，`target_weight_range` 与 `maximum_notional` MUST 均为 JSON `null`；数值 `0`、空数组或任何其他非 `null` 值 MUST 被拒绝。JSON Schema、运行时 Validator 与 CIO Prompt 的派生产物 MUST 通过一致性校验，任何契约缺失、版本不一致或派生漂移 MUST fail closed，且不得放宽现有 Evidence Closure、Risk 或仅供建议边界。

#### Scenario: 合法 NO_TRADE 通过条件校验
- **WHEN** CIO 草案的 `action` 为 `NO_TRADE`，且 `target_weight_range` 与 `maximum_notional` 均为 JSON `null`
- **THEN** JSON Schema 与运行时 Validator 均接受这两个执行字段，并继续校验 NO_TRADE 原因、说明、重评条件、Evidence Closure 和其余既有约束

#### Scenario: 数值零不得冒充 null
- **WHEN** CIO 草案的 `action` 为 `NO_TRADE`，且 `maximum_notional` 为数值 `0`
- **THEN** JSON Schema 与运行时 Validator 均确定性拒绝该草案，运行进入 `FAILED_VALIDATION`，且不得进入 Risk Engine 或发布建议

#### Scenario: NO_TRADE 携带目标仓位范围
- **WHEN** CIO 草案的 `action` 为 `NO_TRADE`，且 `target_weight_range` 为任何非 `null` 值
- **THEN** JSON Schema 与运行时 Validator 均确定性拒绝该草案，且错误明确归因于动作条件契约

#### Scenario: 正常建议遵守对应动作契约
- **WHEN** CIO 草案使用 `BUY`、`ADD`、`HOLD`、`TRIM` 或 `EXIT`
- **THEN** 系统按 canonical decision contract 校验该动作适用的执行字段、理由字段与禁止字段，而不套用 NO_TRADE 的空值规则

#### Scenario: CIO 获得一致的合法与非法示例
- **WHEN** 系统构建 CIO Invocation 的可见指令
- **THEN** 指令包含从同一 canonical decision contract 派生的合法 `NO_TRADE`、`maximum_notional: 0` 非法及非空 `target_weight_range` 非法示例，并标明 `0` 不等于 JSON `null`

#### Scenario: 派生产物与规范契约漂移
- **WHEN** 已保存的 CIO JSON Schema、Prompt 片段或运行时规则与 canonical decision contract 的版本、哈希或确定性派生结果不一致
- **THEN** 测试与运行前完整性校验失败，不允许该候选进入真实 Council 运行

### Requirement: Demo 最终报告必须与真实投资建议明显区分
`DEMO_SCAFFOLD` 的 `decision.json` 和 `report.md` MUST 显示“合成示例、未使用真实 LLM、未使用真实市场数据、不得作为投资建议或交易依据”。到达 CIO 的 Demo 报告 MUST 展示 Portfolio 摘要、参与角色及其状态、示例 Thesis、Counter Thesis、共识、冲突、Evidence References、数据缺口、失效条件、Action、Confidence Rationale 和完整 Risk Result；Agent 前安全终止报告 MUST 展示 Gate 原因且不得伪造角色内容。全部研究内容 MUST 来自 Demo Agent 响应及 Risk 结果，不得由报告模板新增。

#### Scenario: 用户查看 Demo 报告
- **WHEN** 完整 Demo 链路生成最终报告
- **THEN** 报告用中文展示 Agent 数据流结果、风险处理和 Demo 限制，且不会被误认为真实股票研究

#### Scenario: Gate 后没有 Evidence
- **WHEN** Demo 在任何 Agent 调用前形成 `DEMO_SAFE_NO_TRADE`
- **THEN** 报告展示 Portfolio、Gate 排除原因和 NO_TRADE，不生成虚假的 Analyst、Skeptic、CIO 或 Risk 内容

### Requirement: Demo 输出必须保留最终安全字段
Demo 的 `decision.json` SHALL 使用独立 `DemoDecisionEnvelope`，由外层明确记录 `synthetic: true`、`llm_used: false`、`advisory_only: true` 和 Demo 终态，内层 `decision` 继续满足现有动作字段、Evidence Closure、NO_TRADE 条件和 canonical decision contract。确定性 Adapter 不得绕过 Risk Engine，真实产品验收 MUST NOT 接受该 Demo Envelope 代替产品 Decision Schema。

#### Scenario: Demo 形成 NO_TRADE
- **WHEN** Demo 最终动作是 `NO_TRADE`
- **THEN** Envelope 内层 Decision 的 `target_weight_range` 与 `maximum_notional` 均为 null，并保留风险原因和合法 Evidence References


### Requirement: CIO 必须记录多维正反报告的取舍
正反交接 CIO 的版本化输出 SHALL 记录消费报告的唯一身份、证券或共享维度、Invocation 和验证内容哈希，允许同一 Agent 的多个报告而不相互覆盖。CIO SHALL 综合 Company、Macro、Market 对 MRVL 研究判断的影响、共识、关键冲突、反证、不确定性及失效条件；对关键反证 SHALL 关联报告中的 challenge 标识，说明接受、部分接受、驳回或暂无法判断的理由，以及对研究判断或信心的影响。没有影响也 MUST 解释原因。CIO MUST NOT 把投票、多空数量、确定性评分或模板结论当作 LLM 综合。

#### Scenario: Skeptic 挑战正向增长假设
- **WHEN** 正向报告看好增长而反证指出证据时点或客户集中风险
- **THEN** 输出保留双方引用并说明取舍及对研究判断的影响；无法解决时明确保留分歧

#### Scenario: 多个维度由同一个 Agent 产生
- **WHEN** CIO 消费同一 Agent 的多份不同维度报告
- **THEN** 消费记录逐报告保存，不因 Agent 名称相同丢失或覆盖内容

### Requirement: 本阶段 CIO 输出必须保持非动作研究边界
`RESEARCH_SYNTHESIS` MUST 标记 `advisory_only=true`、`complete_portfolio_decision=false` 和 `Risk=NOT_RUN`，并展示原研究截止点与实际生成时间。输出 MUST NOT 包含 HOLD/TRIM/EXIT/NO_TRADE、BUY/ADD、目标仓位、现金安排、最大金额、交易数量或变相买卖指令；积极研究观点不得机械映射为动作。当前 MRVL 已非持仓，报告 MUST 明示未进行当前账户适配和完整组合 Risk。

#### Scenario: 草案越过研究边界
- **WHEN** CIO 草案包含任何动作、仓位、金额或现金目标
- **THEN** 校验拒绝草案，不保存可发布研究报告或建议

#### Scenario: 保留旧契约兼容
- **WHEN** 验证旧 fixture 决策或既有研究交接包
- **THEN** 仍按其锁定版本验证，不要求历史产物新增本阶段消费字段

### Requirement: 研究报告必须与验证产物同源
成功的本阶段运行 SHALL 保存结构化 `cio-research-synthesis.json`、同源中文 `report.md` 与 `decision_trace.json`，不得生成 CIODecisionDraft、`risk.json`、`decision.json` 或虚构 Risk Report。报告 MUST 清楚展示目标、原截止点、生成时间、研究交付级别、关键依据、主要反证及取舍、未解决问题、失效条件和限制；不得声称完成当前持仓建议。最终产物 SHALL 由确定性 finalizer 从已验证结果生成，不由渲染层新增投资判断。非法引用、不完整 Trace 或执行失败 MUST 阻止发布。

#### Scenario: 研究级运行没有 Risk 产物
- **WHEN** CIO 完成合格的 MRVL 非动作综合
- **THEN** Trace 明确记录 `Risk=NOT_RUN`，不伪造空 Risk 检查或决策文件

#### Scenario: 报告引用不存在的 Evidence
- **WHEN** CIO 引用了源 Gate 之外的事实或悬空报告身份
- **THEN** finalizer 报告校验失败，不生成看似合法的最终研究报告

### Requirement: 研究判断不得伪装为账户仓位安排
CIO SHALL 基于 Company、Macro、Market、Skeptic 和可得估值资料解释 MRVL 的业务前景、价格吸引力、分析期限、不确定性与重评条件。当前持仓和个人条件不属于本次已验证研究输入；CIO MUST NOT 从行情推断用户风险承受力、用款需求、目标仓位或现金比例，也不得借研究性观察计划暗示买回 MRVL。

#### Scenario: 用户已经清仓 MRVL
- **WHEN** CIO 综合原时点 MRVL 正反研究，而当前账户没有 MRVL
- **THEN** 报告保留研究判断及证据限制，不给目标仓位、现金区间或买回建议

#### Scenario: 研究判断偏积极
- **WHEN** CIO 判断业务或原截止点的价格资料偏积极
- **THEN** 报告如实表达适用时点、理由与推翻条件，不生成 BUY/ADD 或变相重新建仓指令

### Requirement: 研究综合必须具有明确的非决策边界
`RESEARCH_SYNTHESIS` 输出 MUST 标记 `complete_portfolio_decision=false`，展示请求与实际交付级别、`Risk=NOT_RUN` 及未评估账户适配的原因；MUST NOT 输出 action、目标仓位、最大金额、交易数量或隐含买卖指令，不使用 NO_TRADE 表示资料不全。允许表达原截止点业务、估值或风险的方向性研究判断及待验证条件，但不得声称已经评估当前账户适配。模型执行或完整性失败 MUST NOT 通过改写级别掩盖。

#### Scenario: 当前账户截图并非本研究前提
- **WHEN** 当前账户现金或期权合约详情未提供，但来源 MRVL 正反研究包合格
- **THEN** 系统仍可交付原 cutoff 的非动作研究综合，明确没有完成当前账户建议

#### Scenario: 调用方请求建议
- **WHEN** 请求级别为 `PORTFOLIO_ADVICE`
- **THEN** 宿主在模型前拒绝，不能以研究级产物假装已执行 Risk 后建议

### Requirement: CIO 报告必须回答具体研究问题
研究综合 SHALL 用 MRVL 的实际证据回答六类问题：明确综合判断及适用研究期限；最重要事实及其到判断的推导；关键正反分歧、取舍和剩余不确定性；Macro/Market 对业务、估值或风险的传导及影响有限的理由；会改变判断的可观察事件或指标及方向；优先观察事项及重评事件或时间。报告 SHALL 区分业务前景、价格吸引力与未评估的当前账户适配性。研究分析期限 MUST 标注为分析假设，不冒充用户过去或当前的持有期限。缺少可验证估值资料时 MUST 说明价格吸引力无法判断，不编造目标价、概率或数字阈值。观察计划只作为文字交付，不创建自动监控。

#### Scenario: 输出只有通用谨慎措辞
- **WHEN** 报告仅称增长较好但有宏观风险并建议持续关注，没有证券特定证据、传导或重评条件
- **THEN** 内容验收判定不通过，即使结构、引用和工具调用均合法

#### Scenario: 某维度无法支持结论
- **WHEN** 估值或宏观资料不能支持有把握的方向判断
- **THEN** 报告明确未知项、对总判断的影响和需要的证据，不强制每个维度给出正负结论

### Requirement: CIO 内容质量必须由实际报告复核
独立复核 SHALL 逐项引用实际报告检查六类问题、关键反证的真实处置及对结论的影响，允许以明确且有依据的未知说明满足受限项。复核 MUST 检查是否只复述上游、是否用不存在的数字制造精确性、是否漏掉足以影响判断的重大反证。不得以字段非空、固定字数、固定多空数量或固定动作替代内容验收，也不要求新增评分引擎或自动评估平台。

#### Scenario: 反证没有改变结论
- **WHEN** CIO 认为某项重要反证不足以推翻观点
- **THEN** 复核检查其证据理由、适用边界及何时需要重评，不强制改变观点来证明消费

### Requirement: 最终交付必须让用户直接看到核心内容
宿主任务最终回复 SHALL 从验证后的同源报告展示综合判断、关键依据、主要反证取舍、观察条件及非持仓研究限制，并提供完整报告链接；不得展示 Risk 动作，也不得只返回 run_id、成功状态或文件路径。终端文件输出与会话摘要 MUST 不增加原报告没有的判断；本需求不要求网页改版。

#### Scenario: CIO 成功生成报告
- **WHEN** 阶段完成并交付用户
- **THEN** 用户在回复中即可读到核心研究结论及本阶段未进行持仓建议的边界，而不必自行查找运行目录
