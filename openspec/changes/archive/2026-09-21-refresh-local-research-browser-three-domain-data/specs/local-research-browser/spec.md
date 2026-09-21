## ADDED Requirements

### Requirement: 三域页面必须呈现与对象匹配的数据覆盖
系统 MUST 从通过校验且与所选运行绑定的 `research-provider-coverage/1.0.0` 产物中，将数据集按目标研究能力映射到 Macro、Market、Company 页面。每项数据集 MUST 显示 dataset、目标 capability、Capture、Gate eligible、Delivered、delivery status、已知限制或失败码；页面不得把其他运行、其他证券或其他研究域的记录混入当前对象。首页 SHALL 提供三域覆盖摘要，但不得以汇总数字替代域内逐项状态。

#### Scenario: 新版三域 coverage 完整可用
- **WHEN** 已配置运行包含 hash 有效、cutoff 与运行上下文一致且路由状态闭合的 provider coverage
- **THEN** Macro 显示 `MACRO_CONTEXT` 数据集，Market 显示 `MARKET_STATE` 和 `OPTIONS_FLOW` 数据集，Company 显示公司及所有权/研报相关数据集，并保留其原始计数和状态

#### Scenario: 旧运行没有 coverage 产物
- **WHEN** 已配置运行仍只有既有 Macro、Market 或研究报告产物而没有 provider coverage
- **THEN** 原有快照、计算和报告继续可读，页面明确显示“该运行未保存数据覆盖审计”，不得将其解释为零覆盖或采集失败

#### Scenario: Coverage 与所选版本不匹配
- **WHEN** coverage 的运行来源或 decision cutoff 不能与所选快照、View 或报告闭合
- **THEN** 系统隔离该 coverage 并显示稳定的绑定错误提示，不借用其数据集、计数或状态

### Requirement: 数据交付与实际研究使用状态必须分开
系统 MUST 分别呈现 Capture、Gate eligible、Delivered、Actual research use 和研究报告状态。`DELIVERED` 仅表示资料已交付到目标能力输入，不能表述为 Agent 已采用或结论已覆盖；只有有效产物明确提供实际使用证明时才能显示“已用于研究”。`NOT_EVALUATED_AT_PREPARATION`、`NO_GATE_EVIDENCE`、`SOURCE_LIMITED`、`NOT_ATTEMPTED` 及其他原始状态 MUST 保持可查，不得折叠成笼统成功或失败。

#### Scenario: 已交付但尚未评估实际使用
- **WHEN** 某数据集 Capture、Gate eligible 和 Delivered 均大于零，但 `actual_research_use_status` 为 `NOT_EVALUATED_AT_PREPARATION`
- **THEN** 页面显示“已交付，实际研究使用未评估”，不得显示“Agent 已采用”或“研究已覆盖”

#### Scenario: 数据集没有 Gate Evidence
- **WHEN** 数据集的 `delivery_status` 为 `NO_GATE_EVIDENCE` 且计数为零
- **THEN** 页面将其列为明确数据缺口并保留失败码或限制，不得隐藏、填零成有效值或推断现实中不存在该资料

#### Scenario: 已有有效研究使用证明
- **WHEN** 与同一 run、cutoff、security 和 capability 绑定的有效报告或使用审计明确引用该数据集 Evidence
- **THEN** 页面可以单独显示该使用证明及报告状态，同时保留原始交付计数，不以报告存在反向改写 coverage

### Requirement: Macro 补充层必须与官方事实分层展示
Macro 页面 SHALL 展示已保存的官方宏观快照和 `MACRO_CONTEXT` 研究报告，并增加 Dot Plot、economic calendar、macro history 等覆盖状态。若同一 source/run/cutoff 的有效 Gate 包含 coverage 明确引用的冻结 Evidence，页面 MUST 将其实际值、观察期、单位和来源口径转换为可读的指标、趋势、点阵分布与事件表；页面 MUST 区分官方宏观事实、供应商实际值、市场共识、前值、官方预测和市场隐含概率。Provider coverage 只证明数据准备状态，不得把覆盖计数本身渲染成宏观数值或趋势。

#### Scenario: 官方快照与 Moomoo 补充同时存在
- **WHEN** 同一运行包含官方宏观快照，以及路由到 `MACRO_CONTEXT` 的 Dot Plot、economic calendar 或 macro history 覆盖
- **THEN** 页面分别展示官方观测与补充冻结值，明确来源层、观察期和资料截止，不用补充层覆盖官方数值

#### Scenario: Coverage 与 Gate Evidence 绑定闭合
- **WHEN** coverage 表明 Dot Plot、economic calendar 或 macro history 已交付，且同一运行 Gate 含有其声明的合法 Evidence
- **THEN** 页面优先显示实际冻结内容及其时间、单位和供应商口径，并将 coverage 技术明细放入默认折叠的审计区

#### Scenario: 只有补充覆盖而没有可渲染 Evidence
- **WHEN** coverage 表明数据集已交付，但 Gate 缺失、hash 无效或没有包含其声明的 Evidence
- **THEN** 页面仅显示交付状态和稳定限制，不根据 coverage 计数生成数值、趋势或宏观结论

### Requirement: Market 页面必须呈现共享市场状态的实际冻结内容
Market 页面 MUST 在 coverage 审计之前展示同一 source/run/cutoff Gate 中已绑定的共享市场 Evidence。FedWatch MUST 显示会议日期、目标区间和概率；option market statistics MUST 显示全市场 Call/Put 成交量、持仓量、Put/Call ratio 及观察日期；market breadth 无 Evidence 时 MUST 显示明确缺口。页面不得因旧式 benchmark snapshot 或 market calculation 缺失而隐藏这些新版冻结内容，也不得把市场隐含概率描述为官方承诺或投资结论。

#### Scenario: 新版 Market Evidence 可读但旧式快照缺失
- **WHEN** 运行没有 benchmark snapshot 或 market calculation，但 Gate 含有 coverage 已引用的 FedWatch 或 option market statistics Evidence
- **THEN** Market 页面显示实际概率和时间序列，并将“基准快照未保存”限制放在相应缺口位置，不以全页空状态遮盖已有内容

#### Scenario: Market breadth 没有 Gate Evidence
- **WHEN** coverage 对 market breadth 标记 `NO_GATE_EVIDENCE` 且 Gate 中没有对应 Evidence
- **THEN** 页面明确显示该项尚无数据，不以其他市场指标或零值代替

### Requirement: 共享环境数据与证券级数据必须使用正确范围标签
Macro 历史、Dot Plot、经济日历、FedWatch 和全市场期权统计 MUST 标为共享美国宏观或市场环境；其所在运行服务于某只持仓研究，不得被页面表述为该证券专属数据。只有包含证券标识并通过 security/run/cutoff/Evidence 绑定的期权链、标的波动率和供应商资金流可以标为证券级内容。

#### Scenario: MRVL 运行包含共享环境 Evidence
- **WHEN** MRVL 研究运行包含美国宏观、FedWatch 或全市场期权统计 Evidence
- **THEN** 页面显示“共享宏观环境”或“共享市场环境”，并可另行说明该运行用于 MRVL 研究，但不得显示“适用证券 MRVL”

#### Scenario: MRVL Options Evidence
- **WHEN** Gate 与 coverage 包含 security 为 MRVL 的期权链、标的波动率或供应商资金流
- **THEN** 页面明确显示 MRVL 证券范围、观察时间和供应商口径，并与共享市场状态分区

### Requirement: Options 必须作为 Market 域专项安全呈现
Market 页面 SHALL 在共享市场状态之外展示路由到 `OPTIONS_FLOW` 的证券级冻结内容、数据集覆盖及有效报告。系统 MUST 标明适用 security、run、cutoff 和 capability；options snapshot MUST 以有界明细显示合约、到期日、行权价、Call/Put、Bid/Ask、成交量、持仓量和 IV 等已有字段，underlying context MUST 显示 IV/HV 及 Call/Put 汇总，vendor money flow MUST 显示供应商定义的分类与期间。缺失 Greeks、合约乘数或主动买卖方时 MUST 明确限制；options snapshot、underlying context、option market statistics 与 vendor money flow MUST 保持各自语义，不得冒充共享大盘状态、账户资金流或确定买卖方向。Company 页面 MAY 提供指向同一证券 Options 专项的关联摘要，但不得复制或改写报告身份。

#### Scenario: 证券级 Options 报告绑定闭合
- **WHEN** `OPTIONS_FLOW` 报告与 coverage、security、run、cutoff 和 Evidence 引用均校验通过
- **THEN** Market 页面显示该证券专项的冻结数据、摘要、状态、限制和稳定报告身份，并与共享 `MARKET_STATE` 分区

#### Scenario: Options 数据存在但报告未生成
- **WHEN** options 数据集已经 Delivered，但没有有效 `OPTIONS_FLOW` 报告
- **THEN** 页面显示“资料已交付、研究报告未生成或未绑定”，不得把原始成交量、持仓量或 vendor money flow 自动解释为资金方向

#### Scenario: Options 报告证券错配
- **WHEN** 报告 security 与所选 coverage 或页面证券不一致
- **THEN** 系统隔离该报告并显示绑定错误，不在 Market 或 Company 页面借用其结论

### Requirement: Coverage 适配必须安全降级且不扩大刷新权限
系统 MUST 只从显式准入运行目录的固定审计位置读取受支持 coverage，并只从同一目录固定 `evidence/gate.json` 读取受支持的冻结 Evidence；两者均须验证 schema version、内容 hash、必要结构和运行绑定。manifest 声明 decision cutoff 时，coverage 与 Gate cutoff MUST 与其精确一致；manifest 未声明 cutoff 时，只有 manifest 同时以 `gate_hash` 与 `provider_coverage_hash` 精确引用对应产物，并且 run 与 Gate/coverage cutoff 相互闭合，内容才可用。页面只能消费 coverage 中对应 dataset 已声明且同时存在于 Gate allowlist 的 Evidence ID，并通过逐数据集语义字段允许列表生成小型 projection；除明确的 Greeks 子字段外，允许字段只接收无绝对路径的标量，不得把完整 Gate、任意 value、嵌套对象、账户/组合上下文或绝对路径直接交给模板。系统继续应用既有路径穿越、符号链接、私人字段和绝对路径保护；未知版本、损坏内容或单个异常记录 MUST 以稳定提示隔离，不阻断其他页面。页面刷新 MUST 仅重新读取现有 Memory 和已配置本地运行目录，不得访问 Provider、OpenD、网络、模型或研究调度，也不得写入或修复产物。

#### Scenario: Coverage hash 损坏或版本未知
- **WHEN** 固定审计位置中的 coverage hash 不匹配或 schema version 未受支持
- **THEN** 页面显示对应格式/完整性提示并忽略其正文，既有 Company、Macro、Market 资料继续可读

#### Scenario: Gate 损坏或 Evidence 不在 coverage 声明范围
- **WHEN** Gate hash/版本/运行绑定无效，或某条 Evidence ID 未被所选 coverage dataset 声明
- **THEN** 页面不展示该 Evidence 值并给出稳定限制，其他已验证内容与 coverage 审计仍可继续阅读

#### Scenario: 用户点击重新读取
- **WHEN** 用户在任一页面执行重新读取操作
- **THEN** 系统只重新扫描启动时准入的本地目录并返回更新后的页面，不发起网络、OpenD、Provider、模型或数据写入调用

#### Scenario: Coverage 含有私人或未允许字段
- **WHEN** coverage 或嵌套记录包含账户、组合、凭据、本机绝对路径或未列入展示契约的原始内容
- **THEN** 页面不返回这些字段，只展示经过允许和转义的数据集状态、数量、时间、限制及稳定标识

### Requirement: 三域刷新验收必须证明真实可读性与兼容性
验收 MUST 使用当前三域冻结产物或其完整结构副本，核对已交付数据集、明确缺口、`OPTIONS_FLOW`、来源层和状态文案；同时使用确定性样本覆盖旧运行无 coverage、绑定错配、损坏/未知版本、安全字段清理和只读刷新。验收 MUST 实际查看桌面及窄屏页面。若真实运行只有 preparation 证据，验收只能证明采集/Gate/交付展示，不得宣称实际研究使用或产品 Smoke 已通过。

#### Scenario: 使用当前新版运行验收
- **WHEN** 验收读取包含 Company、Macro、Market 和 Options 路由的真实冻结运行
- **THEN** 页面逐域显示与底层 coverage 一致的 dataset、计数、状态和缺口，并将 `NOT_EVALUATED_AT_PREPARATION` 正确呈现为未评估实际研究使用

#### Scenario: 浏览前后状态保持不变
- **WHEN** 验收记录浏览前后的 Memory 与运行产物 hash，并执行首页、三域页面、版本选择和重新读取
- **THEN** 所有浏览目标保持不变，除只读访问外没有采集、研究、checkpoint、报告或 coverage 写入
