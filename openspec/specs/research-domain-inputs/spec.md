# research-domain-inputs Specification

## Purpose

为当前持仓研究提供唯一、可发现且可校验的 Company / Macro / Market 输入拓扑，使研究域、专业能力、执行 Agent、provider 层和实际完成状态保持一致，同时明确区分当前入口与历史兼容入口。

本能力同时要求三域资料完成真实获取与研究消费，并限定旧 live 创建链路和残余产物的退役边界，避免分类齐全而输入不足或维护重复实现。

## Requirements

### Requirement: 当前研究输入拓扑必须具有权威版本
系统 SHALL 提供一个版本化的当前持仓研究输入拓扑，逐项声明研究域、capability、执行 Agent、作用范围、结构化输出、provider plane 及其引用的 source policy/capability matrix。运行清单 MUST 锁定该拓扑的版本与内容 hash；文档或配置若与权威拓扑冲突，校验 MUST 失败而不是静默选择其中一份。

#### Scenario: 当前研究运行被创建
- **WHEN** 系统准备一次新的多维持仓研究运行
- **THEN** 运行清单引用并锁定当前研究输入拓扑，消费方可从同一入口解析 Company、Macro、Market 的能力、Agent 和 provider 归属

#### Scenario: 声明的 Agent 与运行绑定漂移
- **WHEN** 拓扑声明某 capability 由指定 Agent 执行，但运行清单绑定不同 Agent 或缺少拓扑 hash
- **THEN** 系统在模型调用前拒绝该运行并报告配置漂移

### Requirement: 研究域不得被解释为一域一个 Agent
Company、Macro、Market SHALL 作为面向研究输入与展示的稳定域。系统 MUST 通过 capability 映射到专业 Agent：Company 域的公司基本面、公司事件与公开研报研究由 Company Analyst 承担；Macro 与 Market 域可由同一 Market Catalyst 在隔离 invocation 中分别执行。系统 MUST NOT 仅因新增页面栏目、指标或 provider 而新增 Agent；新增默认 Agent 仍须满足既有可测增益要求。

#### Scenario: Macro 与 Market 同时进入研究计划
- **WHEN** 当前持仓研究同时需要宏观环境和市场状态输入
- **THEN** 系统生成两个可独立追踪的 capability invocation，并允许它们绑定同一 Market Catalyst，而不是合并成一个不可区分的结果或新建两个数据源 Agent

#### Scenario: 新 provider 被接入
- **WHEN** 当前来源计划增加或替换一个只读 provider
- **THEN** 系统更新 provider plane 与 capability 覆盖，不因来源变化改变 Agent 职责

### Requirement: 当前与退役入口必须明确区分
研究拓扑发现入口 MUST 将可用于新运行的配置标记为 CURRENT，并将只用于历史重放或兼容校验的配置标记为 RETIRED/COMPATIBILITY_ONLY。退役 `live-us-equity/4.0.0` 的内容和既有历史绑定 MUST 保持可验证，但新研究、产品说明和默认发现 MUST NOT 将其展示为当前 Company / Macro / Market 拓扑。

#### Scenario: 查阅当前 provider 与 Agent 视图
- **WHEN** 使用者或校验器请求当前持仓研究配置
- **THEN** 返回包含 Company Analyst、Market Catalyst 及当前 provider planes 的权威拓扑，并单独标明退役 profile 的兼容用途

#### Scenario: 重放历史 live profile
- **WHEN** 历史运行锁定 `live-us-equity/4.0.0`
- **THEN** 系统仍按其冻结内容完成兼容校验，不要求历史产物补写 Market Catalyst、Moomoo 或新 capability

### Requirement: Provider 视图必须表达职责层而非虚假全覆盖
当前 provider 视图 SHALL 区分基础行情/身份/披露层、官方宏观资料层与研究补充层，并引用既有来源政策、补充来源计划和数据集能力矩阵。每个 provider/dataset MUST 表达适用区域、认证条件、状态和限制；Moomoo Singapore MUST 仅作为受限研究补充层，不能被呈现为 SEC/Yahoo 的替代、完整研究覆盖或交易入口。

#### Scenario: Moomoo 只有部分数据集可用
- **WHEN** OpenD 的某个批准 Quote API 数据集可用而其他数据集受限
- **THEN** provider 视图逐数据集显示实际状态，并继续显示 SEC/Yahoo 可独立工作的能力，不把 Moomoo 标记为整体可用或整体失败

#### Scenario: 来源政策或能力矩阵发生变化
- **WHEN** 权威拓扑引用的来源文件内容 hash 与运行清单不一致
- **THEN** 新运行要求重新解析并锁定一致版本，旧运行保留原 hash，不静默继承新状态

### Requirement: 三域必须具有逐数据集的真实获取闭环
系统 MUST 为 Macro、Market、Company 声明核心和增强数据集、来源、范围、字段、时间、预算、状态及消费位置。Macro 核心 SHALL 覆盖通胀/就业、利率、经济活动、央行政策原文和已公布日历；Market 核心 SHALL 覆盖大盘/相关板块、跨资产代表序列、波动/信用环境及限定窗口市场新闻；Company 核心 SHALL 覆盖全部确认普通股的财务/披露、可定位且去重的 issuer/IR 正文、指引/预期分类与 issuer/IR 材料发现。公开独立研报的发现与全文属于增强数据集，MUST 与 issuer/IR 正文分开标记和验收。事实 MUST 有 source_id、as_of、retrieved_at 和可核实的公开时间/原文定位。系统 MUST 完成实际获取、标准化、PIT、Gate、冻结工具查询与对应研究引用，不能以新增配置、空报告或技能安装证明完成。

#### Scenario: 三域正式研究
- **WHEN** 用户通过当前入口提交确认持仓并启动三域研究
- **THEN** 系统自动准备同一 cutoff 的资料，逐数据集输出覆盖和缺口，产生公司、宏观、市场的真实消费证据，无需用户手工拼接资料

#### Scenario: 核心项尚无数据
- **WHEN** 一个核心项只有来源名称或未验证的接口，没有合格数据和研究引用
- **THEN** 该项保持未完成，整个 Change 不得仅凭结构校验申请完成

### Requirement: 免费补充来源必须有界准入并保留语义
系统 SHALL 允许为三域缺口接入已核实的免费官方 API、RSS、公开新闻与研究正文来源，逐项说明认证、额度、允许用途、美股覆盖、时效和失败策略。系统 MUST 保留原始来源、转载链、事实与外部观点区别，代理序列不得冒充原指标。付费、平台专属权限或未知版权/访问条件不得默认视为免费可用；候选尝试必须在预先声明的预算内结束。

#### Scenario: 信用和跨资产代理
- **WHEN** 只能取得 ETF 或其他代理而不能取得目标现货或专有指数
- **THEN** 报告显示代理身份、适用范围和限制，不输出目标指数的虚构数值

#### Scenario: 新闻窗口没有新条目
- **WHEN** 已完成规定时间窗口和范围的真实查询但没有合格新闻
- **THEN** 保存查询范围及零结果，不虚构新闻，也不推断市场没有事件

### Requirement: 外部金融 Skill 必须证明可移植及可取数
`wb-finance-skill` 及公开第三方归档 `infometa/workbuddyskills` 中的 `westock-data`、`neodata-financial-search` 等候选 MUST 逐数据集核实原包/归档 commit、文件和脚本 hash、依赖精确版本与完整性、许可、网络端点、宿主工具、认证、费用及美股实际字段覆盖。归档内容 MUST 只作为候选发现与审阅材料，不能被视为官方分发、数据权威或可直接执行的生产依赖；仅当独立数据能力真实可调用并满足 Evidence 契约时才能经确定性 adapter 接入。含浮动依赖、远程脚本或通用命令执行的候选 MUST 在代码审阅、版本锁定、最小网络 allowlist 和隔离验证前保持禁用。未取得原包、依赖 WorkBuddy 专属服务或无法确认使用条件时 MUST 标记 `NOT_VERIFIED`、`SOURCE_LIMITED` 或 `REJECTED`，并继续其他公开来源路径。系统 MUST NOT 把复制 Skill 文本、安装成功或 README 声明视为获得外部数据权限或完成取数。

#### Scenario: 候选依赖宿主专有工具
- **WHEN** Skill 调用了当前环境不存在且没有独立接入途径的工具
- **THEN** 记录具体依赖与限制，不伪造工具结果，不阻塞无此依赖的公开来源采集

#### Scenario: 公开归档候选声明可覆盖多个数据集
- **WHEN** `westock-data`、`neodata-financial-search` 或其他归档 Skill 声明可提供行情、新闻、宏观或公司材料
- **THEN** 系统仅对完成真实返回、来源时点、字段语义、许可与供应链审查的具体数据集准入，其他声明保持未验证，不把整包标记为可用

### Requirement: 新来源和契约迁移不得破坏当前研究流程
新 provider、第三方候选和 2.0 契约 MUST 以显式版本、非默认切片和可回退默认指针分阶段启用。候选超时、限流、认证失败、字段漂移或拒绝访问 MUST 只影响对应数据集的覆盖状态，不得污染既有三源冻结包、阻断仍具合格输入的其他域，或触发 Cookie/私有接口回退。系统 MUST 在切换默认版本前后验证当前 Handoff 准备、Gate/MCP、正式 dispatch、SEC/Yahoo/Moomoo 降级和 1.1 历史读取；无效 2.0 输入 MUST fail closed，不能静默降级为 1.1 并掩盖契约问题。

#### Scenario: 第三方候选在正式准备时不可用
- **WHEN** 一个已配置的候选来源超时、限流或返回无法验证的字段
- **THEN** 对应数据集记录准确失败或受限状态，既有 SEC/Yahoo/Moomoo 和其他具备合格输入的域继续运行，冻结包中不写入不合格结果

#### Scenario: 2.0 默认切换失败
- **WHEN** 新拓扑或 2.0 契约在准备阶段校验失败
- **THEN** 系统在模型调用前拒绝本次运行并保留诊断，运维可显式回退默认指针，但系统不把该运行静默改写为 1.1

### Requirement: 旧 live 退役必须保留当前功能和必要历史读取
系统 MUST 按当前生产消费者、历史只读/Replay 消费者、测试专用与零消费者四类逐项审计旧 live 代码、专属测试及产物。仅服务退役 full live Council 的新运行创建/派发入口 MUST 删除或拒绝新运行；共享采集、校验、MCP 和必要历史 schema/报告读取 MUST 保持有效。仍被当前流程使用的 `live_*` 共享符号 MUST 先迁移到中性模块或由等价实现替代，禁止按文件名、前缀或历史归属整体删除。退役不得只增加标签而保留可误用的新运行入口；历史可读不要求保留全部旧创建链路。删除前 MUST 同时证明零当前生产调用、必要历史样本可读、旧入口 fail closed 及当前入口前后基线一致。产物处理 MUST 记录准确目标、引用检查与恢复方式，不得删除有效验收记录、私人研究或无恢复保证的文件。

#### Scenario: 调用旧创建入口
- **WHEN** 使用者请求审定为退役的旧 full live Council 创建命令
- **THEN** 命令不存在或在取数/模型调用前明确拒绝，并指向当前 Handoff 研究入口

#### Scenario: 文件同时含共享与旧代码
- **WHEN** 审计发现旧 live 文件仍被当前数据准备或历史读取调用
- **THEN** 保留必要符号，只收缩已证实无用途的分支，并以当前路径及历史样本检查验证

#### Scenario: 中间产物仍被验收索引引用
- **WHEN** 计划删除的日志或产物仍有有效引用或没有明确恢复方式
- **THEN** 保留该目标并记录原因，不将其纳入删除清单

### Requirement: Moomoo 补充字段必须映射到既有研究域和专业能力
系统 MUST 继续使用 Company、Macro、Market 三个稳定研究域，并按数据语义而非 provider 名称分配 Moomoo Evidence。Company 域的 `RESEARCH_REPORT` SHALL 消费合格评级/目标价共识、评级历史和分章节 Morningstar 材料；Macro 域的 `MACRO_CONTEXT` SHALL 消费宏观实际、单独标记的供应商 consensus、日历、官方预测转引及其来源限制；Market 域的 `MARKET_STATE` SHALL 消费共享市场快照、全市场期权统计和 FedWatch 市场预期。期权合约及个股供应商资金数据 SHALL 由 Market Catalyst 的既有 `OPTIONS_FLOW` 专项消费；机构、内部人与空头披露 SHALL 由 `OWNERSHIP_DISCLOSURE` 消费。上述消费以数据合格且本次专项启用为前提，条件接入增强项未取得时保留取舍结果与缺口。系统 MUST NOT 为 Moomoo、Options、Macro 数据或页面栏目新增数据源 Agent。

#### Scenario: Morningstar Evidence 通过 Gate
- **WHEN** 某普通股的分章节 Morningstar Evidence 通过同一 cutoff Gate
- **THEN** 它可进入 Company 域 `RESEARCH_REPORT`，但不得进入 `FUNDAMENTAL_EVENT` 作为 SEC 原始事实，也不得被 Macro 或 Market invocation 消费

#### Scenario: 全市场 Put/Call 统计通过 Gate
- **WHEN** Moomoo 返回美国证券期权市场按日成交量或 OI 的 call、put、total 和 ratio
- **THEN** 统计进入 Market 域共享 `MARKET_STATE` 或作为 `OPTIONS_FLOW` 的明确市场基线，不绑定为任一公司的资金方向事实

#### Scenario: 个股期权和资金流通过 Gate
- **WHEN** 某证券具有合格 options snapshot、IV/HV 或供应商资本流/分布 Evidence
- **THEN** Evidence 只进入该证券的 `OPTIONS_FLOW`，保持证券隔离，不进入共享 Macro 报告或其他证券任务

### Requirement: Moomoo Macro 必须作为二级补充而非官方宏观层替代
当前 provider 视图 MUST 保留 `OFFICIAL_MACRO` 中 BLS、Treasury 和 Federal Reserve 的主源职责，并在 `RESEARCH_SUPPLEMENT` 中逐数据集显示 Moomoo Macro、Economic Calendar、FedWatch 和 Dot Plot 的实际状态。Moomoo 实际值只有在官方主源缺少对应系列或作为冲突/覆盖补充时进入 Macro Context；供应商共识和 FedWatch 概率 MUST 使用独立字段与来源类型，不能替代官方实际值或政策正文。

#### Scenario: 官方系列已经可用
- **WHEN** BLS 已提供同一观察期的 CPI、失业率或非农事实
- **THEN** Moomoo 同类值不覆盖官方 Evidence，只作为二级交叉核对、供应商预期或覆盖说明

#### Scenario: 官方 Collector 尚未覆盖某系列
- **WHEN** Moomoo 提供 PPI、核心 CPI、PCE、零售销售或其他已批准系列，而当前官方 Collector 没有对应事实
- **THEN** Macro Context 可在明确 `SECONDARY_VENDOR`、单位、观察期、发布时间和历史 vintage 限制后使用，不将其重新标记为官方来源

### Requirement: Provider coverage 必须暴露采集与消费两种状态
当前拓扑和每批 provider coverage MUST 分别说明数据集的文档/Spike/采集状态与下游交付状态，并记录合理排除原因。`AVAILABLE` 或 `PARTIAL` 的响应若未进入正式 Collector、Gate/MCP 或目标 Skill，MUST 显示为未完成交付；进入允许列表仅证明交付，实际研究使用 MUST 依据有效报告的引用与解释验证，不能仅凭 adapter、Normalize 或选择数量宣称已消费。

#### Scenario: 采集成功但选择器不匹配
- **WHEN** 合格 Moomoo Evidence 已写入冻结包，但目标 capability 的 Evidence 选择规则没有包含该 semantic field 或 dataset
- **THEN** provider coverage 标记采集成功、消费未接线，并使对应专项验收失败而不是把 Evidence 静默丢弃

#### Scenario: Moomoo 当前批次失败
- **WHEN** OpenD 不可达、权限不足或接口字段漂移
- **THEN** 只降低受影响的数据集和 capability 消费状态，SEC/Yahoo/官方宏观仍按其合格输入继续运行

### Requirement: 三域补全必须先复用既有资料并核对剩余缺口
系统 MUST 分别维护 Company、Macro、Market 的研究问题与资料覆盖，优先使用已下载响应、现有标准化结果和已授权来源。来源计划声明的公司治理、关系、资本配置、指引和事件数据 MUST 与真实采集/消费状态一致；未实现的回退不得冒充可用。候选公司事实、日程、新闻和行业材料 MUST 按语义进入既有输入或专项，保留供应商层级，不能全部归入研报观点。

#### Scenario: Treasury 已下载响应含多个期限
- **WHEN** 同一日期的响应具有合格 2Y、10Y、30Y 数据
- **THEN** 复用响应输出期限事实与可核对的 10Y−2Y 期限差；期限缺失时保留 gap，不额外抓取相同资料或跨日期拼接

#### Scenario: 公司背景来源声明尚未兑现
- **WHEN** 某数据集仅有来源配置，正式采集不存在或资料没有被正确交付
- **THEN** 补接可复用链路或纠正来源状态，保留真实资料缺口，不以方法存在将背景资料标记齐全
