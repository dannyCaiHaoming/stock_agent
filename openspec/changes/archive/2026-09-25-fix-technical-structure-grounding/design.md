## Context

见 proposal.md 与本 Change 的 delta spec。当前 `_prepare_technical_artifacts` 在个股或基准日线缺失时返回 `calculation=null`、`chart=null` 及 `TECHNICAL_SERIES_MISSING`；MRVL 冻结样本是个股 250 行、SPY 0 行。Technical 分派说明却只描述有计算产物时怎样引用，模型在无计算时写出四条无引用的否定性 Claims，现有校验器正确拒绝。基准完整的另一份 MRVL 样本已能通过计算引用与图表引用闭合。图表生成路径本已把预期的渲染错误记为 gap，保留先前写入的 calculation，但研究说明仍有“必须引用图”的无条件表达。

## Goals / Non-Goals

**Goals:**

- 用现有 `prepared_analysis` 的真实状态限定 Technical 的输出：无 calculation 时为合法的零 Claim 缺口报告；有 calculation 时保留原有研究及引用门禁。
- 单独表达 chart 缺口，不能把它升级成 calculation 缺口或消除已得结论。
- 在最终研究包中区分保存成功与核心技术研究完成。

**Non-Goals:**

- 不跨 run 拼接 SPY，不补采数据，不从 MRVL 单股日线推导新的“无基准技术研究”契约。
- 不让 Python 根据涨跌阈值生成投资主张，不放松通用 Claim grounding、PIT、artifact/Evidence closure。
- 不引入新状态机、Agent、编排器、图表服务或 Schema 大版本。

## Decisions

1. **复用当前任务级动态输出约束。** 在 `TECHNICAL_STRUCTURE` 且 `prepared_analysis.calculation` 为空时，按现有 `INDUSTRY_COMPARISON` 无可比资料分支的模式限制 `claims` 为零，并在任务说明中明确 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、缺失的是个股还是基准、`data_gaps` 的具体影响及禁止捏造引用。对应状态须由当前输出契约和确定性校验约束，不只依赖提示词。保留通用 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 门禁。备选“允许无引用的否定性 Claim”会削弱所有维度的引用纪律，故不采用。
2. **有 calculation 的路径保持原样。** 已冻结的计算文件、`artifact_id`、`calculation_refs`、allowed artifact 与 Claim closure 仍是技术主张的依据。仅对技术任务说明与 Skill 中图表可用性的表述作条件化，不改计算公式和报告结构。备选“用确定性代码补写技术结论”违反 LLM/计算职责边界。
3. **图表是独立的展示产物。** 预期渲染失败时，`prepared_analysis.calculation` 和其 artifact ref 不变，`chart=null`、allowed refs 不包含不存在的图，保留独立 chart gap。模型可继续解释计算并引用计算产物；不得引用缺失图，也不得因此输出 `INSUFFICIENT_EVIDENCE`。意外的文件/权限错误不伪装成图表来源受限。备选“图表失败即整项失败”会丢失有效研究。
4. **不改变冻结输入身份或扩建状态模型。** 旧 MRVL Gate 的 SPY 缺失只能验收受限分支；基准完整分支复用另一份自身合法绑定的 MRVL 样本作对照，不把两份 Gate 或报告拼成同一次运行。任务执行 `SAVED` 与研究结论分开记录：缺 calculation 的合法报告仍为 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`，现有研究包聚合沿用报告状态使 `coverage.status=INSUFFICIENT_EVIDENCE`；网页和下游不得因 JSON 合法或任务已保存展示 `TECHNICAL_STRUCTURE COMPLETE`。`PARTIAL` 只属于报告 `sufficiency`，不加入 coverage 状态枚举。chart-only gap 单列，不机械地把有引用的 Claims 降为无计算资料。对外分别记录保存数、研究状态、chart gap 和研究包就绪性。

## Risks / Trade-offs

- [零 Claim 报告被误读为技术研究成功] → 报告 `status/sufficiency` 与研究包 `coverage.status` 分别检查，网页不得误标 `COMPLETE`；验收不以任务 `SAVED` 数量代替核心内容通过。
- [条件化 Skill/任务说明影响正常研究] → 基准完整样本验证计算引用、图表引用、MRVL 专属解释与反向条件仍保留；不扩展到 Market 其他 capability。
- [图表缺口被误报为无计算] → 聚焦模拟可预期的渲染失败，检查计算文件/hash、allowed refs、Claim closure 与仅图表 gap；不吞没未知异常。

## Migration Plan

不迁移或改写历史报告。实施后先完成三种输入的聚焦确定性验证，再用既有宿主 launcher 对受影响的缺基准 MRVL 冻结输入做一次真实 Technical 输出验证；已有基准完整真实报告作为正常路径对照，若本次说明变更影响正常路径则补同源宿主验证。未满足内容门槛时保留 Change 未完成，不以归档或 8/8 `SAVED` 替代验收。
