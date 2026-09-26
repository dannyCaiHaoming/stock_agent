## ADDED Requirements

### Requirement: 正反研究至 CIO 的联调必须证明同源资料消费
系统 SHALL 对同一普通股、同一 `decision_cutoff` 的 Company、Macro、Market 正向报告、独立 Skeptic 报告及 CIO 研究综合核对来源运行、Gate、报告身份/hash、执行终态和实际 Evidence 引用。只有正向及适用反证交接达到既有下游就绪条件且 CIO 真实消费后，联调才可称为完成。完成检查 MUST 包含内容复核：核心判断有具体依据，重要反证被处置并说明影响，三域限制被准确传递；仅准备成功、Schema 合法、工具调用成功或多个历史 PASS 的拼接不足以通过。

#### Scenario: 同一截止点端到端完成
- **WHEN** 合格正向、独立反证和非动作 CIO 报告均来自同一冻结截止点且引用闭合
- **THEN** 输出可追溯的完成证明及仍存在的资料限制，研究级结果保持 `Risk=NOT_RUN`，不生成单股操作建议

#### Scenario: 上游引用或执行证明失败
- **WHEN** 一个必需报告存在悬空引用、缺实际终态或与 Gate/hash 不一致
- **THEN** 联调失败并指出断点；不得把错误转换为低置信度 CIO 报告或投资性 `NO_TRADE`

#### Scenario: 内容合法但没有回答关键反证
- **WHEN** CIO 结构合法，却没有解释关键 Skeptic 挑战对判断的影响
- **THEN** 内容验收不通过；保留原始报告，不为取得 PASS 改写其结论或启动无预算重试

### Requirement: 链路核验必须检查既有前置条件与合法来源关联
运行计划 SHALL 核对既有 COMPANY_RESEARCH、TECHNICAL_STRUCTURE、FUNDAMENTAL_EVENT、INDUSTRY_COMPARISON、MACRO_CONTEXT、MARKET_STATE 及其他适用交接条件，逐项标明可复用、需补跑、合法受限或阻断。复用 MUST 满足既有导入规则，核对来源 Gate、输入版本、截止点适用性、报告身份/hash 与真实执行证明；合法导入或 run_id 重绑定产生不同 Gate hash 不等于来源不一致，也不得据此豁免校验。新旧不等价样本不得混为一条已通过链路。

#### Scenario: 必需维度合法受限
- **WHEN** 必需报告以 INSUFFICIENT_EVIDENCE 或 SOURCE_LIMITED 合法保存且满足现有下游就绪条件
- **THEN** 允许按原规则流转，覆盖继续显示受限；任务执行完成不使维度研究升级 COMPLETE，缺失或校验失败报告仍阻断

### Requirement: 本次完成必须交付有限且实质的验收结果
本次 MRVL 验收 SHALL 交付三域覆盖与正确性表、按调用追踪的关键证据消费记录、一条真实正向/独立反证/CIO 研究综合链路，以及聚焦回归与剩余缺口结论。关键标准化错误、必需报告失败、非法引用、缺真实执行证明或内容验收失败 MUST 阻止完成；辅助来源限制可明确保留，不要求所有 provider 全字段齐全。合法 gap report、预算耗尽或多个历史 PASS 不能替代实质内容验收。完成仍需人工批准，不代表历史回测或候选晋升通过。

#### Scenario: 预算耗尽但关键断点仍存在
- **WHEN** 已确认模型调用预算耗尽且仍有关键断点未通过
- **THEN** 提交已有证据和准确阻断，不自动续跑、不降低内容标准、不标记需求完成
