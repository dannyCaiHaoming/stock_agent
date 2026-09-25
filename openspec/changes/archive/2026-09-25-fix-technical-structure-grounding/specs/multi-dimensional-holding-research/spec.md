## MODIFIED Requirements

### Requirement: 价格成交量研究必须解释技术结构及适用窗口
系统 SHALL 研究价格趋势、成交量变化、相对基准强弱、波动、回撤及关键价格区域，明确窗口、基准、复权与交易时段。数学结果 MUST 由确定性工具计算，LLM SHALL 解释结构、替代解释及失效条件，不由指标阈值直接生成投资动作。历史不足、停牌、拆股与重组断点 MUST 限定适用结论。技术任务缺少可用个股或基准序列、因而没有确定性 calculation 时，系统 MUST 保留准确的来源缺口，不得要求 Agent 生成无引用的“无法判断” Claim；其合法报告 MUST 为 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT` 且 `claims=[]`，并明确缺失项及其对技术研究的影响。任务执行状态 `SAVED` 只表示合法报告已保存，不改变报告状态或研究包 `coverage.status`；后者 MUST 保留 `INSUFFICIENT_EVIDENCE`，不得因保存成功或 JSON 合法而展示 `TECHNICAL_STRUCTURE COMPLETE`。`PARTIAL` 仅是报告 `sufficiency` 的可用值，不得作为 `coverage.status`。技术任务有有效 calculation 时，Claims MUST 引用实际计算并通过现有 artifact closure；只有图表失败不得抹除计算、阻断有效 Claims 或伪装为计算资料不足。

#### Scenario: 技术报告有实质内容
- **WHEN** 普通股具有足够合格日线与基准数据
- **THEN** 输出带日期和计算依据的趋势、相对表现、波动及量价解释，以及可能推翻解释的观察信号；技术主张通过真实 `calculation_refs` 连接获准计算产物

#### Scenario: 重组或拆股造成价格断点
- **WHEN** 历史序列不可直接连续比较
- **THEN** 解释调整或截断依据，不将机械断点当作崩盘、突破或真实收益

#### Scenario: 个股有日线而广泛市场基准缺失
- **WHEN** MRVL 有合格日线，但同一冻结 Gate 缺少 SPY 基准，且技术任务没有确定性 calculation
- **THEN** 技术任务可以 `SAVED`，但报告 MUST 保持 `status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、`claims=[]`，研究包 `coverage.status` MUST 为 `INSUFFICIENT_EVIDENCE`；明确基准缺失及其影响，不得跨 run 拼入基准、伪造 calculation，或在研究包与网页中把技术研究标为 `COMPLETE`

#### Scenario: 计算成功但图表失败
- **WHEN** 同一冻结输入已产生有效 technical calculation，而相对表现图生成失败
- **THEN** 允许 Agent 保留有真实 `calculation_refs` 的技术 Claims，报告只新增与图表相关的具体 gap，不虚构 chart artifact，也不因图表失败改称 calculation 或全部技术资料缺失；若充分性因此受限，用报告 `sufficiency=PARTIAL` 表达，不把 `PARTIAL` 写入研究包 `coverage.status`

### Requirement: 研究问题与展示必须使多维输出可理解
系统 SHALL 从已有合格资料形成逐公司核心问题清单，各维度说明回答的问题、具体事实、推导及假设、改变结论的观察条件。技术报告在同源量价与相对表现图可生成时 SHALL 提供该图，标明期间/基准/口径；仅图表生成受限时 MUST 明确原因及影响，并保留已合法生成的计算与研究结论，不把缺图当作缺少全部技术资料。公司研究 SHALL 分析可得管理层指引变化，行业和宏观 SHALL 选择公司相关变量并解释传导。最终中文摘要 SHALL 仅归集已有发现、依据、限制和信号，不新增投资判断。

#### Scenario: 指引变化与一致预期不同
- **WHEN** 资料只有管理层两次指引
- **THEN** 比较原值、版本和口径并解释变化，不声称取得市场一致预期或预期差

#### Scenario: 只有图表产物生成失败
- **WHEN** 技术 calculation 已通过绑定和引用校验，但图表无法生成
- **THEN** 中文技术报告展示有依据的技术主张及 chart gap，不展示不存在的图、不丢弃有效计算，也不因此宣称技术研究没有资料
