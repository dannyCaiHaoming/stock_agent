## ADDED Requirements

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
