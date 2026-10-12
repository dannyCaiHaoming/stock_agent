## ADDED Requirements

### Requirement: 无账户列表不得隐式转换为单股或持仓输入

STOCK_LIST_RESEARCH SHALL 具有独立版本化输入、请求/hash和完整成员绑定，沿既有身份核实与逐证券研究方法消费；SINGLE_STOCK_RESEARCH 保持一证券语义，PortfolioHandoff 保持真实确认账户语义。各阶段请求/manifest/invocation/报告与列表结果 MUST 显式绑定来源模式及成员，未知模式、跨成员/错 run/错 hash/错 Schema 或缺原件模型前拒绝，不能因列表只有一项而猜为单股、因文件缺失回退到 Handoff 或伪造持仓。旧单股/持仓 Schema、报告和执行/读取边界原样保留，新列表采用新版本，不补写旧运行锁。

#### Scenario: 自选股列表只有一个成员
- **WHEN** 用户以 STOCK_LIST_RESEARCH 提交一只合格股票
- **THEN** 仍按列表请求/hash和成员绑定验证，不能静默改为旧 SINGLE_STOCK_RESEARCH 或删除列表 lineage

#### Scenario: 列表原件缺失但目录有 Handoff
- **WHEN** manifest 声明列表模式，而对应冻结列表请求缺失
- **THEN** 明确拒绝，不读取无关 Handoff 当回退输入、不重算旧hash掩盖缺失

### Requirement: 列表内综合必须逐证券保持研究级边界

列表的正式综合 SHALL 明确每个目标证券、共同 cutoff、实际来源报告/挑战和支持关系，沿前置修复的 source_dispositions、calculation_support 及全部目标挑战核对；不能把另一证券的事实/计算/挑战混入当前对象。共享宏观/基准事实只在同 cutoff/允许集/版本且该 invocation 实际获准消费时使用，不因此免除当前直接事实 query。无账户和持仓列表研究的结果 MUST 为 RESEARCH_SYNTHESIS、账户适配未评估、Risk=NOT_RUN，不能生成相对投资排名、自动买卖/仓位或完整组合动作。最终批次索引引用正式原报告和实际失败/未运行，不由 Python 代写批量投资结论。

#### Scenario: A 与 B 使用同一基准但窗口不同
- **WHEN** 两证券研究均引用某基准，而 A 的相对收益计算与 B 的窗口/身份不同
- **THEN** 各综合只能选择自己获准源主张中的精确计算；相同基准名不成为跨证券复用或错窗口免责理由

#### Scenario: 单项失败但其他综合成功
- **WHEN** 一项 CIO 未能形成合格输出，其余项成功
- **THEN** 索引保留该项真实失败和成功项原报告，不将成功项复制补齐失败证券，也不由程序生成其研究判断
