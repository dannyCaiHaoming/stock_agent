## ADDED Requirements

### Requirement: 研究任务终止与报告成功必须分别识别
系统 SHALL 使用可信派发、Start 子会话绑定与最终 Stop/执行结果识别正向及反证任务终止，不依赖模型草案中的身份字段。失败任务终止后 MUST 释放并发槽位并保留失败原因；只有验证成功的报告满足下游依赖。格式修复仍在进行时不得提前认定终止。全部任务已终止或依赖阻塞后 SHALL 收尾，不持续等待已结束任务；超时保留成功产物及未完成清单，不补造报告或生命周期事件。本修复 MUST NOT 新增调度器、自动研究重试或补查询再提交机制。

#### Scenario: 草案缺身份且全部子任务已结束
- **WHEN** 可信生命周期已确认全部派发任务结束，但部分草案缺失技术身份或报告校验失败
- **THEN** 系统完成失败归集而非继续空等，保留成功结果和具体错误，核心失败时不启动 Skeptic

#### Scenario: 子任务尚在格式修复或缺终止证明
- **WHEN** Stop 被一次格式修复阻止，或当前任务没有可信最终终止记录
- **THEN** 系统不把它计为已结束；超时按执行未完成处理，不制造成功或终止事件

### Requirement: Portfolio Council 必须提供显式独立反证研究阶段
`portfolio-council` SHALL 支持显式 `stage=INDEPENDENT_COUNTER_THESIS_RESEARCH`，从有效的 PortfolioHandoff 与绑定 CouncilRequest 开始，在同一运行中依次复用资料准备、多维正向研究、正向研究包确定性验证和逐普通股 Independent Skeptic。现有 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 阶段仍 SHALL 停止于正向研究包，不得因本能力存在而自动启动 Skeptic。

#### Scenario: 用户明确请求正向多维研究和独立反证
- **WHEN** 用户已有确认 Handoff，并通过 `portfolio-council` 明确选择独立反证研究阶段
- **THEN** 系统使用同一 Portfolio、Request、run、cutoff 和 Gate 完成正向研究及独立反证，再生成正反研究交接产物

#### Scenario: 用户只请求多维研究
- **WHEN** 用户选择既有 `MULTI_DIMENSIONAL_HOLDING_RESEARCH`
- **THEN** 系统保持原有停止点，不启动 `runtime_skeptic`，也不把缺少反证显示为该阶段失败

### Requirement: 独立反证阶段必须在 CIO 与 Risk 之前停止
独立反证研究阶段 SHALL 只产生正向研究包、逐证券 `CounterThesisReport`、正反研究交接包、同源中文摘要和必要执行证明。该阶段 MUST NOT 构造或调用 `runtime_cio`，不得运行 Risk Engine、生成 `CIODecisionDraft`、`decision.json`、组合动作、Outcome、历史重放或回测，也不得将研究交接包描述为完整 Portfolio Council 建议。

#### Scenario: 正反研究全部技术就绪
- **WHEN** 正向研究和每只普通股的反证报告均通过阶段校验
- **THEN** 运行以研究阶段完成状态结束，明确标记 `complete_portfolio_decision=false` 和未启动 CIO/Risk

#### Scenario: 调用方试图在同一阶段提交 CIO 草案
- **WHEN** 独立反证研究运行目录出现 CIO、Risk 或最终决策产物，或调用方请求阶段 finalizer 消费这些产物
- **THEN** 阶段校验 fail closed，不把越界产物纳入合法研究交接

### Requirement: 独立反证阶段必须保留全持仓覆盖与可恢复失败
阶段 SHALL 保留 Handoff 中全部持仓及能力覆盖，只对当前支持的普通股启动 Skeptic。非普通股、正向研究未就绪的普通股和 Skeptic 系统失败 MUST 以逐资产覆盖缺口保留；任一缺口不得被隐藏为完整正反研究。Agent 合法领域状态与系统失败 MUST 分开表示。冻结输入、版本锁和成功产物 hash 均保持有效时，SHALL 允许通过既有恢复入口续跑未完成或失败任务，保留成功结果。重试使用独立 Invocation/attempt 与输出引用，不覆盖历史尝试或成功报告；每次显式恢复每个目标任务最多一个新研究尝试，格式修复沿用一次上限。cutoff、Gate、Handoff、Request 或版本锁变化时 MUST 使用全新运行。

#### Scenario: 混合资产组合进入阶段
- **WHEN** Handoff 同时包含普通股与当前不支持独立反证的 ETF 或期权
- **THEN** 系统只为合格普通股派发 Skeptic，保留其他资产的能力缺口，并拒绝把交接包标记为完整组合决策输入

#### Scenario: 一项 Skeptic Invocation 系统失败
- **WHEN** 某证券反证输出存在非法结构、身份或 Evidence 引用
- **THEN** 系统保存该证券失败与已完成证券的合法产物，交接包不标记为 `DOWNSTREAM_READY`，且不启动 CIO 或 Risk

#### Scenario: 同一冻结运行恢复失败证券
- **WHEN** 用户通过宿主恢复入口重试失败 Skeptic 且冻结输入与成功产物重验通过
- **THEN** 仅派发目标未完成任务，保留其他研究结果和旧尝试，显式记录采用的新结果，不重新采集资料或重跑已成功正向研究

#### Scenario: 恢复时版本或资料发生变化
- **WHEN** 当前运行代码版本锁或冻结输入与原运行不一致
- **THEN** 拒绝原地续跑并要求新运行，不能把新旧资料拼接为原截止点的研究

### Requirement: 首个真实样本必须证明研究链路而非投资结果
Change 验收 SHALL 通过宿主产品入口对至少一个已确认的真实普通股样本执行一次新的独立反证研究运行，保存正向研究、Skeptic 调用、只读 Evidence 工具事件、输入隔离、交接包和阶段边界证据。验收 MUST 使用全新运行目录和同一 point-in-time 边界，不得复用不同 cutoff 的临时报告拼装结果，也不得以市场涨跌、固定 Thesis、固定动作或回测收益作为通过条件。

#### Scenario: MRVL 作为首个真实纵向样本
- **WHEN** 操作者使用当前确认的 MRVL 普通股持仓启动本 Change 的宿主验收
- **THEN** 运行证明正向研究与独立 Skeptic 共享同一 Gate 但保持结论隔离，形成可验证正反研究交接，并明确未启动 CIO、Risk 或回测

#### Scenario: 首次 MRVL 验收发生失败
- **WHEN** 首次样本未完成真实反证或交接验证失败
- **THEN** 允许显式有界修复和重试，满足冻结条件时续跑，否则新运行；不因“一次运行”限制接受失败，不自动扩张样本集

#### Scenario: 工具调用真实但报告空泛
- **WHEN** 执行证明合法而人工复核发现报告只有通用风险、缺少事实支持或可检验解释
- **THEN** Change 不能仅凭 Schema 和工具事件宣称研究质量验收通过；记录具体问题，不引入固定观点、挑战数量或自动分数门槛
