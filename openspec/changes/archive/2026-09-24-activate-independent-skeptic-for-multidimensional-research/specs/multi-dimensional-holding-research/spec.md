## ADDED Requirements

### Requirement: 宏观与市场研究必须适配实际持仓数量
正向 Macro/Market 研究的 Prompt 与 Skill SHALL 对单股解释该公司敏感性、传导假设和反向情景，仅在多股时要求比较持仓差异。同行比较 MUST 限于既有授权冻结资料，不为了满足比较要求自动补入第二只公司。真实资料不足仍按原领域状态保留，不能仅因没有第二只持仓判定不足。

#### Scenario: MRVL 是唯一普通股持仓
- **WHEN** 输入仅有 MRVL 且存在可用宏观市场及公司资料
- **THEN** 报告研究 MRVL 的传导机制与限制，不要求第二只持仓，也不因此自动返回资料不足

#### Scenario: 多股可比较但部分资料不足
- **WHEN** 有多只持仓且部分敏感性比较缺乏依据
- **THEN** Agent 比较有据可查的差异并保留具体资料缺口，不由确定性层补写比较结论

### Requirement: 独立反证阶段必须基于同一运行的下游就绪研究包
显式独立反证研究阶段 SHALL 在同一 `run_id` 内复用本次冻结的 PortfolioHandoff、CouncilRequest、证券身份、decision cutoff 与 Evidence Gate，并且只在本次 `HoldingResearchBundle` 已通过 Schema、绑定、PIT、Evidence Closure 和 `DOWNSTREAM_READY` 校验后进入反证派发。系统 MUST NOT 从其他运行、其他 cutoff、历史 Research Memory 或临时验收目录补入正向报告以满足该条件。

#### Scenario: 同一运行的多维研究满足前置条件
- **WHEN** 本次运行的每只普通股均具有兼容 Company Research，核心多维任务具有合法终态，且 `HoldingResearchBundle` 为 `DOWNSTREAM_READY`
- **THEN** 系统允许进入独立反证派发，并沿用完全相同的 Portfolio、Request、cutoff、Gate 和证券身份绑定

#### Scenario: 历史 MRVL 报告来自不同截止点
- **WHEN** 调用方尝试将不同 run 或不同 decision cutoff 的 Company、Macro、Market 或其他维度报告拼入当前研究包
- **THEN** 系统拒绝将该包标记为反证阶段可用，并保留具体跨运行或时间绑定错误

#### Scenario: 核心研究仍有失败或未研究项
- **WHEN** Company Research 缺失，或价格技术、基本面事件、行业、Macro、Market 中任一适用核心任务没有可验证报告而处于 `FAILED`、`TIMEOUT`、`NOT_RESEARCHED` 或依赖阻塞
- **THEN** 系统保存诊断产物但不启动 Skeptic，不把结构可解析误报为完整正反研究

### Requirement: 正反研究交接必须引用原产物而不重新综合判断
系统 SHALL 生成版本化正反研究交接包，引用本次已验证 `HoldingResearchBundle` 和逐普通股 `CounterThesisReport` 的路径、内容 hash、状态与绑定，并提供同源中文摘要。确定性归集器 MUST 校验 Portfolio、Request、run、cutoff、Gate、证券身份和 Evidence Closure 一致性，不得复制、改写、补写或裁决正方与反方的投资判断。

交接包 SHALL 区分 `STRUCTURALLY_CONSUMABLE` 与 `DOWNSTREAM_READY`：前者只表示产物可解析并保留真实缺口；后者要求正向研究包已就绪，且每只适用普通股都有身份、Invocation、Schema 和 Evidence Closure 合法、状态为 `COMPLETE` 或已完成研究的 `LOW_CONFIDENCE` 独立反证报告。合法 `INSUFFICIENT_EVIDENCE` 或 `TIMEOUT` 必须原样保留，但整体最多为 `STRUCTURALLY_CONSUMABLE`，不得因结构合法宣称反证完成。没有返回合法报告的宿主超时属于执行未完成，不由归集器生成报告。普通股研究就绪不等于完整组合决策输入就绪；非普通股能力缺口持续展示。

#### Scenario: 正反报告全部完成技术绑定
- **WHEN** 下游就绪多维研究包和每只适用普通股的已完成独立反证报告均通过重验
- **THEN** 交接包标记为 `DOWNSTREAM_READY`，并可从每个引用追溯到原报告、Invocation、允许 Evidence 和内容 hash

#### Scenario: 一只普通股缺少合法反证报告
- **WHEN** 多维研究包包含多只普通股但任一普通股缺少可验证的 `CounterThesisReport`
- **THEN** 交接包最多标记为 `STRUCTURALLY_CONSUMABLE`，明确该证券缺口且不得声称已准备好进入 CIO

#### Scenario: 归集器发现正反观点冲突
- **WHEN** 正向报告与 Skeptic 报告对同一风险或解释形成实质差异
- **THEN** 系统分别保留原始报告引用和状态，不由确定性程序选择胜方、计算观点分数或生成动作

#### Scenario: 反证合法但超时或资料不足
- **WHEN** 任一适用普通股返回合法 `TIMEOUT` 或 `INSUFFICIENT_EVIDENCE`
- **THEN** 保留正文和状态用于诊断，交接包最多为 `STRUCTURALLY_CONSUMABLE`，明确不能宣称完整正反研究

### Requirement: 中文交付必须可直接阅读实际研究内容
系统 SHALL 提供正向报告与逐证券反证中文正文的明确引用。反证正文 SHALL 忠实展示 Agent 的挑战、事实依据、假设、传导解释、待补证据、推翻条件和限制；交接索引只汇集原始状态和引用，不以 hash 清单替代可读研究，也不增加一轮 LLM 综合或自动观点裁决。本 Change 不要求扩建网页。

#### Scenario: 用户阅读已完成正反研究
- **WHEN** 用户打开交接摘要
- **THEN** 能定位并阅读原始正向与独立反证正文，理解依据及限制，而无需从执行日志自行拼装报告

### Requirement: 历史多维研究包必须保持兼容且不得自动补写反证
本 Change 之前生成的 `HoldingResearchBundle` SHALL 继续按其锁定 Schema、run 和 cutoff 读取及验证。历史包没有反证报告时 MUST 保持原状态；系统不得因当前存在 Skeptic 能力而修改历史包、推断历史反证已经执行，或把旧包自动升级为正反研究交接包。

#### Scenario: 打开历史研究包
- **WHEN** 用户或 Reviewer 读取一个没有独立反证产物的历史 `HoldingResearchBundle`
- **THEN** 系统按历史契约展示其正向研究与缺口，不写入新文件、不启动 Agent，也不显示反证已完成
