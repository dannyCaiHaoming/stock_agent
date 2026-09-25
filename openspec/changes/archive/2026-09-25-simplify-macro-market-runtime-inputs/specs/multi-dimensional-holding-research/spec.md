## ADDED Requirements

### Requirement: Macro 与 Market 研究必须使用可追溯的任务相关来源覆盖视图

正式正向 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 阶段的 `MACRO_CONTEXT` 与 `MARKET_STATE` 任务的模型输入 MUST 提供与各自研究职责相关的来源覆盖视图，而不是直接转交按 provider 粗筛后仍包含无关数据集及完整证据 ID 清单的审计对象。视图 MUST 从同一冻结运行的完整来源覆盖审计记录派生，并可核对其审计身份；完整审计记录及 hash MUST 保持为权威来源。视图 MUST 保留判断来源可用性和限制所需的 provider `plane`、provider、标的、相关数据集、观察状态、失败原因、时间、限制与回退语义，且 MUST 区分全局 provider 状态与任务范围内的数据集状态。即使某相关数据集没有合格 Evidence，其失败、不可用或未覆盖观察也 MUST 可见。任务相关性 MUST 包括该任务实际消费的跨域背景资料，不得仅用一张静态数据集路由表筛选。视图收敛 MUST NOT 改变 Evidence Gate、允许的 Evidence、已有 Evidence Catalog、研究输出契约或其他阶段/能力的输入，尤其不得修改 `INDEPENDENT_COUNTER_THESIS_RESEARCH` 阶段同名 capability 的输入与任务说明。

视图 MUST 明确声明自身阶段和 capability，并把原件 schema 版本及 `coverage_hash` 标识为审计来源身份，不得当作精简对象自身的 hash。provider 全局状态、计数与失败码 MUST 与任务数据集观察分隔展示；没有数据集明细或筛选后明细为空的候选 provider MUST 保留覆盖状态和限制，并明确空明细的含义，不得由此推断无 Evidence 或获取失败。机械 hash 验证、路由校验和计数核算 MUST 由确定性层执行，不转交研究 Agent。

#### Scenario: Macro 与 Market 获得各自相关的覆盖信息
- **WHEN** 同一冻结正向研究运行准备 `MACRO_CONTEXT` 和 `MARKET_STATE` 任务，审计记录含有各自相关及无关的数据集观察
- **THEN** 两个任务分别收到保留各自相关观察、缺口和回退含义的视图，且不包含仅属于无关数据集的大量证据 ID 清单；完整审计记录保持不变

#### Scenario: 同名 provider 跨 plane 及多标的资料
- **WHEN** 同名 provider 在不同 `plane` 提供资料，或研究任务涉及多个标的
- **THEN** 视图保留各条观察原有的 `plane`、provider、标的与数据集身份，不将不同来源层级或标的合并成一条可用性结论

#### Scenario: 零 Evidence 与失败来源仍可辨认
- **WHEN** 任务相关数据集未形成合格 Evidence，或其观察为失败、过期、不可用或来源受限
- **THEN** 模型仍能看到相应状态、原因、时间和限制，并能区分任务范围内观察与仅表示全局情况的 provider 状态，不把缺口误报为可用事实

#### Scenario: 来源覆盖视图与审计记录不一致
- **WHEN** 任务视图无法与本次冻结运行的完整审计记录或其 hash 核对
- **THEN** 系统不得把该视图当作可信的正式研究输入继续分派，并记录可定位的失败原因

#### Scenario: 官方来源已有 Evidence 但没有数据集明细
- **WHEN** 候选官方宏观 provider 有已通过 Gate 的 Evidence，但原始覆盖记录没有数据集观察明细
- **THEN** 模型视图仍保留该 provider 的全局覆盖状态、计数与限制，明确原件无明细，不把它判为未采集或无 Evidence，也不伪造数据集观察

#### Scenario: 独立反证复用同名能力
- **WHEN** 独立反证阶段通过共享组装入口准备 `MACRO_CONTEXT` 或 `MARKET_STATE`
- **THEN** 其输入与任务说明保持原状，不启用此次正向研究的来源覆盖投影

### Requirement: Macro 与 Market 输入消减必须验证实际减量和消费兼容性

消减完成 MUST 在同一冻结 MRVL 输入、同一序列化方式下证明两个任务各自的来源覆盖视图与完整 packet 字节数均下降，并经正式 Macro/Market 运行及独立复核确认重要信息与研究质量没有实质性退化。系统 MUST 保持既有报告汇总、CIO 输入装配及历史 packet 读取契约；这些兼容性检查 MUST 使用确定性入口与合法绑定样本，不要求额外启动完整 LLM 链或历史 Execution Replay。

#### Scenario: 体积没有下降
- **WHEN** 冻结样本比对发现任一目标任务的来源覆盖视图或完整 packet 字节数未下降
- **THEN** 不能宣告输入消减完成；记录实测结果并调整，不以已存在投影函数作为完成依据

#### Scenario: 新报告被下游消费
- **WHEN** 合法同 run、同 cutoff 和绑定关系下的 Macro/Market 报告进入现有研究汇总与 CIO 输入装配入口
- **THEN** 两个入口均可验证并消费原有报告契约、Evidence 引用与来源缺口，不要求下游适配精简覆盖视图

#### Scenario: 历史 packet 没有新视图标记
- **WHEN** 读取已有合法历史 packet，其不包含新增模型视图标记
- **THEN** 系统沿用原读取与 hash 校验行为，不强制迁移历史产物；新视图的绑定校验仍正常生效

#### Scenario: 当前状态判断遗漏同一 Gate 中更新的观察
- **WHEN** Macro/Market 报告采用较旧指标描述当前状态，而同一截止点内已有可查询的更新观察且可能改变解释
- **THEN** 验收必须核对证据可见性、查询及模型选取，修正并定向复验，或由独立复核给出不构成实质问题的证据；不得以输出契约通过代替内容验收，不得把历史 vintage 限制误写为当前冻结快照不可使用

#### Scenario: 原生计量或查询记录不完整
- **WHEN** 宿主产物只有父轮次 token/cache 用量，或没有逐任务完整查询日志
- **THEN** 验收记录必须区分计量范围，将无法取得的项标为 `UNAVAILABLE` 并记录原因，以可定位报告和 Evidence 引用提供替代核对证据；不得伪造子任务计量、查询次数或宣称实际 token 节省，独立复核须明确证据限制是否影响质量判断

#### Scenario: 同次运行存在非目标维度缺口
- **WHEN** Macro/Market 已保存报告，但公司报告未导入或技术结构等非目标任务失败
- **THEN** 验收记录必须分别说明导入状态、任务失败及与本次差异的关系；仅对本次变更导致的回退补修，不以阶段 `PASSED` 宣称全部维度完成，也不自动扩展本需求的数据采集或其他 Agent 改造范围

### Requirement: Macro 与 Market 验收必须使用可重复的既有宿主启动路径

目标任务 MUST 能通过既有宿主 launcher 使用受控产品配置运行，不依赖手工创建临时认证链接作为正常启动步骤。启动修复 MUST 保留严格配置校验、产品工具与权限边界，且以真实运行事件证明实际加载；MUST NOT 修改用户全局配置、持久化复制认证或引入第二套编排入口。

#### Scenario: 用户 Desktop 配置含宿主 CLI 不兼容字段
- **WHEN** 用户配置中的应用专用字段阻断宿主 CLI 的严格解析
- **THEN** 受影响入口优先复用现有 CIO 入口的用户配置隔离方式，验证 CLI 支持及产品配置实际加载；不支持时保留明确失败，不通过关闭严格校验绕过，临时隔离运行成功不得替代正常入口修复证明
