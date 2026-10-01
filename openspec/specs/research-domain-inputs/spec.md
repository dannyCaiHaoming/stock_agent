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

### Requirement: Moomoo 公开搜索仅作为独立的有界线索来源
系统 MUST 将 `moomoo-news-search` 对应的公开新闻、公告和 `Research` 搜索结果与 `moomoo_sg` loopback OpenD 分别标识。候选 MUST 保留原始链接、标题、来源类别、`source_id`、发布时间或明确缺失、`retrieved_at` 和研究截止点，并按证券身份、相关性、重复和 PIT 规则筛选。仅有搜索元数据时内容层级 MUST 为 `LEAD_ONLY` 或标题线索；`Research` 类别、评级快讯、二次转引或公告索引 MUST NOT 自动成为独立研报 `BODY_VERIFIED`、发行人原始披露或 Company Thesis 事实。

#### Scenario: MRVL 搜索混入其他公司或相关 ETF
- **WHEN** 搜索命中名称相近的非 Marvell 公司、杠杆 MRVL ETF 或无法核对发行人身份的项目
- **THEN** 该项目不得作为 `US:COMMON_STOCK:MRVL` 的公司事实或研报正文交付，并记录排除原因

#### Scenario: 评级新闻被归入 Research 类别
- **WHEN** 返回标题、时间和 URL，但未取得可核验正文及正文出处
- **THEN** 系统最多将其作为 Company `RESEARCH_REPORT` 发现线索，保留观点/转引身份与正文缺口，不将该维度或整个研究链标为研报正文完成

### Requirement: 公开新闻线索必须按 Company、Macro、Market 语义消费
Company 的合格线索进入现有多维 `RESEARCH_REPORT`，只提示后续核验；普通 `COMMON_STOCK_RESEARCH` 的 Company 首版上下文继续排除专门能力的 `research_discovery`，不得为验收而扩大。发行人事件以 SEC/IR 原文为事实锚点；Market 仅可在标题确属本批截止点前、设定时窗内且与市场研究问题相关时，将其作为有限新闻背景。Macro 官方观察和政策正文仍由既有官方来源承担；Moomoo OpenD 宏观实际/供应商共识是二级补充，公开新闻标题不能替代数值 Evidence。系统 MUST 在单一 MRVL 样本中分别报告来源尝试、Gate 准入、研究工具交付、有效报告引用或未引用原因；不得只凭适配器存在、Gate 准入或 JSON 保存称为 Agent 已使用。

#### Scenario: 公开 Company 线索的实际消费验收
- **WHEN** 同一截止点的 MRVL Gate 已准入公开 `research_discovery` 线索，需要证明其被研究 Agent 实际使用
- **THEN** 验收走现有多维 `FUNDAMENTAL_EVENT → RESEARCH_REPORT` 依赖链，核对 `RESEARCH_REPORT` 的允许 ID、成功工具查询，以及通过 Schema/引用闭包的报告对至少一条新增公开线索的原样引用；报告只可把它作为线索或缺口，不得提升成正文或公司事实。若只有工具查询或有依据的未引用原因，必须如实记录但不得称新增线索已被报告消费，继续保持待研究验证

#### Scenario: 公开线索在混合研究目录中可辨认
- **WHEN** `RESEARCH_REPORT` 的允许目录同时含大量 OpenD 评级快照和已准入的公开标题线索
- **THEN** 同一任务输入明确列出公开线索的原样 Evidence ID，并要求 Agent 至少查询一条，核实其与当前研究问题的关系；采用时在已有 claim 引用中解释用途、标题/链接层级及核验限制。不相关、重复或无新增价值的线索允许排除并记录原因，不为引用数量拼凑主张；未引用仍不得标为报告已消费。本次 MRVL 正例的真实查询及至少一条合法引用验收不变。没有公开线索时不施加此要求，其他研究维度不变

#### Scenario: 标题线索与已核验正文并存
- **WHEN** 公开线索与可用的独立研报正文同时进入 RESEARCH_REPORT
- **THEN** 线索自身保持 LEAD_ONLY，报告整体状态依据已核验正文与研究问题的实际覆盖判断；不得因存在标题自动输出 SOURCE_LIMITED，不得仅因有一份正文就自动宣布充分。没有足够正文时仍保留真实正文缺口

#### Scenario: 配置阻断优先于线索可用
- **WHEN** material_preparation.status 为 BLOCKED_CONFIGURATION，且公开线索可用
- **THEN** 原有 FAILED / evaluation_status=FAIL 与配置缺口要求优先；线索可用不得将配置失败改写成 SOURCE_LIMITED。既有 FAILED 准备状态也按原失败契约处理

#### Scenario: Market 24 小时窗口得到相关标题
- **WHEN** 现有新闻源在本次时窗内无合格项目，而 Moomoo 公开搜索在有界请求内取得身份、时间和相关性均合格的市场标题
- **THEN** Market 可消费明确标为标题线索的项目，保留原链接和来源限制；不得推断正文事件、市场宽度、信用利差或确定性行情方向

#### Scenario: 线索引用沿用现有报告契约
- **WHEN** 验证 Agent 对公开标题线索的实际消费
- **THEN** 报告通过已有 Schema，在已有 claim 引用字段保留原样 Gate ID，只陈述线索存在及核验限制，保留正文缺口；不得向 gap 添加未支持字段、将标题升级为经营事实或为验收强制投资结论，合法保存也不代表独立研报正文完整

#### Scenario: 搜索结果不相关或超过截止点
- **WHEN** 仅有无关标题、未来发布时间或无法证明 24 小时窗口的项目
- **THEN** Market 新闻缺口保持，Macro/Company 不借用这些项目填满各自覆盖；系统记录实际尝试而不制造 `AVAILABLE`

#### Scenario: 既有 OpenD 宏观数据通过 Gate 但报告未引用
- **WHEN** Moomoo Macro History、Economic Calendar、FedWatch 或 Dot Plot 已采集并通过 Gate，但目标任务没有查询或没有形成有效引用
- **THEN** 覆盖报告分开呈现采集成功与未消费，并保持官方/二级供应商、实际/共识/市场预期的语义边界

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

### Requirement: 三域资料覆盖必须沿真实运行逐层核对
对指定普通股与同一 `decision_cutoff`，系统 SHALL 从既有来源尝试、冻结事实、Gate、工具事件和正式报告生成可读的 Company、Macro、Market 消费核对。每域 MUST 分别展示来源状态、合格 Evidence IDs、Gate 允许/排除、实际交付 Agent 的 ID、报告引用 ID 及其限制；只有能从真实产物证明的环节才可标记完成。承载事实的条目 MUST 保留 `source_id`、`as_of`、`retrieved_at` 和来源/运行引用；核对产物不生成新的研究事实或投资判断。

#### Scenario: 来源取得但 Agent 未查询
- **WHEN** 某 Company 事实已通过 Gate 且出现在目录，但工具事件没有交付该事实
- **THEN** 核对显示“可用但未交付”，不写成来源缺失、已研究或报告已引用

#### Scenario: 多域部分受限
- **WHEN** Company、Macro、Market 中一域的某数据集来源受限，其他域取得并实际消费合格事实
- **THEN** 逐数据集保留受限原因及其判断影响，其余域显示实际交付与引用，不把全部三域一概判为完成或失败

#### Scenario: 核对所需运行事件缺失
- **WHEN** 工具事件、Gate 或正式报告缺失而无法证明某项消费
- **THEN** 对应环节显示未验证及缺失证据，不通过推测补齐，也不改变原运行终态

### Requirement: 研究实际使用与来源配置必须分开表示
provider 的声明能力、采集成功、Gate 准入、工具交付、报告引用和 CIO 消费 SHALL 是可分别核查的状态。系统 MUST 只从实际交付事件推定模型可能使用的事实，并以正式报告引用识别已表达的依据；不得仅因资料列在目录、出现在 Prompt 或字段数量非零就声称模型已采用。

#### Scenario: 工具交付但报告未引用
- **WHEN** 某个 ID 在工具成功事件中已交付，却没有出现在对应正式报告的事实引用中
- **THEN** 核对先检查合法 calculation/附件等间接引用路径；直接和间接均无引用时区分“已交付、未引用”，不将其写为未获取或已支撑判断，未引用本身不构成失败

### Requirement: 覆盖核对必须包含应有项与事实正确性
系统 SHALL 根据现有拓扑与本次研究需求明确 Company、Macro、Market 应有数据项、时间窗口及核心/辅助分类，完全未取得的数据项也 MUST 呈现。旧冻结样本用于回归，当前来源检查 SHALL 经现有入口有界执行并单独记录实际尝试时间、缓存命中、失败/未尝试、数据时点和限制；不得用旧样本或缓存成功证明当前远端可用。关键事实 SHALL 抽查原始资料至标准化值、单位/币种、主体、财务期间及发布时间，行情包括交易时段、复权和基准对齐；事实保留 source_id、as_of、retrieved_at，无原始依据标未验证，不新增主观投资评分。

#### Scenario: 应有数据项完全缺失
- **WHEN** 某个本次应有数据项没有任何冻结事实
- **THEN** 覆盖表仍列出该项及失败、未尝试或不可确认原因，不能因只统计已有事实而忽略缺口

#### Scenario: 标准化存在关键单位错误
- **WHEN** 原始来源与规范化事实之间存在影响核心判断的单位或财务期间错误
- **THEN** 记录可追溯错误并在修复及聚焦回归前不声明资料正确，不以引用合法抵消该错误

### Requirement: 消费核对必须按调用隔离并追踪间接引用
系统 SHALL 复用既有 calculation 父 Evidence、附件和正式报告引用关系，在各 invocation 范围内区分直接引用与间接引用，再核对报告至 CIO 的消费；不能从一位 Agent 的交付推定另一位 Agent 已取证。核对产物 MUST 仅用于阶段结束后的开发验收，不注入 Skeptic 独立首轮。不要求引用全部事实，不推断模型内部注意状态；缺少可证明路径标未验证。

#### Scenario: 事实经计算支撑报告
- **WHEN** 正式报告合法引用 calculation，且该调用的实际交付及父 Evidence 可追溯
- **THEN** 父事实标记间接引用，不误报为未使用，也不把此调用的交付状态移给其他 Agent

### Requirement: 恢复收尾必须沿实际影响面核对而不重复历史失败
恢复本Change时 SHALL 逐项区分已实现来源/消费能力、已修共享交接、当前缺少的真实内容证明和真实外部限制。历史批次与旧预算 MUST 保留，不能逐批重新成功才能收尾，也不能将工程优化或定点报告代替最终同批八维内容8/8。当前写入由已批准共享语义交接负责，按对应接缝正负检查及同冻结资料新候选核定准入；不得新增Agent/编排/评分或因旧规划的协议描述要求模型重新承担机械登记。

#### Scenario: 当前工程已修但最低内容尚未核对
- **WHEN** 当前计算选择、限定引用、局部修订和状态归集检查通过
- **THEN** 可标确定性放行，仍按原最低内容逐维核对真实query、主张、期间/单位/主体/来源和上游关系；结构通过、PARTIAL及成本下降均不自动代表内容通过

#### Scenario: 恢复后的资料仍为原历史截止点
- **WHEN** 使用2026-09-28的完整冻结资料在新run_id中补验
- **THEN** 报告明确原资料时间和新执行时间，不冒称当前行情或当前账户分析；归档仍需同批内容、独立复核与人工完成批准

### Requirement: 调试放行必须证明指令所要求的操作实际可完成
研报机械交接修补 SHALL 用冻结失败材料及显式合成草稿，通过实际交付、受限工具/提交、可信装配、原校验、保存/展示和下游读取验证，而不仅检查提示文本或ID存在。至少覆盖准确文档选择、上游计算复用、无计算权限保留原单位三条成功路径，及越权/篡改/跨任务或版本/引用配对不符的拒绝路径。正式和首次定点入口、旧协议和普通股/Skeptic/CIO兼容 MUST 分别核对。检查不得启动模型或将模拟稿视为真实研究。

#### Scenario: 提示要求计算而研报没有该权限
- **WHEN** 指令、权限与提交格式不能共同完成要求的动作
- **THEN** 记录工程阻断并先修复契约，不让用户消耗真实研究额度发现矛盾，不简单归因于模型能力

#### Scenario: 工程路径通过后准备真实验收
- **WHEN** 实际交接正反例、输入增量及独立只读复核已通过
- **THEN** 再列新候选、实际依赖闭包和所需调用数申请授权；原95子/21父已用尽不自动续额，真实内容仍检查依据选择、原文解释、期间/单位及引用关系，不增加语义评分器或跨包伪造完成

### Requirement: 调试放行必须对应已知问题的零模型验证
方案检查、调试前确定性验证和真实研究验收 MUST 分开记录。已知路由/工具/交付缺陷 SHALL 在申请新的真实调用前完成实现与定点检查，并准备可核对的新冻结运行包、任务数和调用预算。方案校验不证明实现通过；执行保存不证明内容充分。模型额度耗尽后不自动续跑。

#### Scenario: 内容修补尚未真实复验
- **WHEN** 同行有限比较问题、广度预计算、研报全引用路径自查和金额参数诊断已写入需求
- **THEN** 验收将每项实现/零模型证据与真实报告结果分列，未实施标待办；旧339项检查和8/8保存不能替代本轮新检查，预算仍以实际批准为准

#### Scenario: 下一轮收尾内容复核
- **WHEN** 获独立新增额度后完成同Gate/cutoff、同材料的基本面→研报补验，并复核原host-v2八维基线
- **THEN** 逐维核对最低内容、核心退化和新旧证据/hash及配置差异；六维仅在未受影响且原证据有效时复用，两项按补验内容判断。允许据此证据组合验收Change，禁止伪造一次新八维运行或严格A/B；真实来源限制可保留PARTIAL，不要求全部COMPLETE或零缺口

#### Scenario: 报告合法保存但内容需要修补
- **WHEN** 旧报告已保存，既有 retry 因 REPORT_ALREADY_VALID 拒绝
- **THEN** 保留旧产物，使用既有新包准备/宿主入口并准确核定调用数；不得删除旧报告、改冻结任务或自动扩建替换框架

#### Scenario: 计算失败未进入查询摘要
- **WHEN** query 已成功或失败，同时 calculate 返回 TOOL_NOT_AUTHORIZED
- **THEN** 现有审计分别呈现 query 统计和各工具错误，计算拒绝不能被查询首错遮蔽；只记录已观测的操作、结果引用和时间顺序，缺失标明

#### Scenario: 引用边界修补后的局部验证与最终验收
- **WHEN** 四处已知问题已完成局部零模型检查，但尚无新真实报告
- **THEN** 仅记确定性放行；申请调用前说明实际入口、依赖闭包、任务数及复用限制，已保存行业/期权不可走失败 retry；无法局部运行时明确最终需新完整八维包，不自动增加预算或跨包拼装为完成

#### Scenario: 任务已启动但报告校验失败
- **WHEN** 市场或研报存在真实启动及失败事件，但没有合法保存报告
- **THEN** 执行状态保留失败，报告消费标无合法报告；不得仅因引用计数为空将任务标为 NOT_RUN，也不得提升为研究完成

### Requirement: 输入优化必须有轻量可定位的消耗与内容差异证据
系统 SHALL 在既有运行事件和消费核对中记录每任务旧/新输入 hash、分区字节/token、重复 ID、留盘/摘要/按需读取差异、实际 Hook 和依赖增量、工具返回量/重复读取及首个失败位置。计数 MUST 标明 tokenizer/版本/编码和范围，区分本地计数、参考编码、估算与实际 usage；缺失标 NOT_OBSERVED，不用字节比例冒充 token 降幅。父子 usage SHALL 按实际归属不重叠汇总，cached 不重复相加。日志 MUST 限于脱敏统计和引用，不复制完整正文、凭据或模型私有推理，不新增观测平台或评分 Agent。

#### Scenario: 初始输入减少但查询膨胀
- **WHEN** 新包装较小而工具多次返回相同内容
- **THEN** 分列初始节省、工具返回、重复读取及可观测累计消耗；无可比基线时不能宣称全流程成本下降

#### Scenario: 分词器或子 Agent 用量缺失
- **WHEN** 只有字节测量、参考编码或父线程 usage
- **THEN** 标明计数及缺失范围，不把约 79% 字节试算当 token 优化，不把父线程当整批用量，也不隐式调用付费接口补测

### Requirement: 研究效果验收必须区分输入等价与模型质量
优化验收 MUST 在同冻结 Gate、任务授权和研究问题下验证资料可达、目录可恢复、数值/期间/单位/来源/限制不丢失及原拒绝行为，并对真实报告按八维最低内容核对 claim、query、calculation 和原文，特别检查反证、否定条件、脚注、来源层级及期间语义。合法 JSON、token 下降或输入等价 MUST NOT 单独表示模型质量不退化。历史报告只有输入、模型及配置可比时才可用于相对结论；否则 SHALL 报告本轮绝对质量与严格 A/B NOT_TESTED，不编造精度百分比或预测准确率。额外模型对照/评分必须另行批准。

#### Scenario: 包装变小但丢失关键反证
- **WHEN** 内容复核发现有效负面观点或财务限定条件未交付、读取或正确解释
- **THEN** 定位包装/读取/推理/引用环节并保留未完成项，不以体积下降或阶段 PASSED 覆盖问题

#### Scenario: 没有同输入旧报告
- **WHEN** 旧报告截止点不同或资料不足
- **THEN** 可分别验收输入等价和本轮最低研究质量，但不能宣称严格 A/B 不退化，也不能自动增加调用获取基准

### Requirement: 八维补全必须区分可修复阻断与真实来源限制
系统 SHALL 对八维应有资料逐项呈现实际取数范围、请求/缓存结果、Normalize/PIT 状态、任务交付与直接/间接引用。缺口 MUST 区分未尝试、内部参数/解析/预算/路由问题、来源权限/无数据、历史时点不足和 Agent 未消费，保留原始错误码和影响；不为此新增一套运行状态机。接口存在和普通 JSON 保存均不得提升研究覆盖。

#### Scenario: 内部参数错误引发 Quote 失败
- **WHEN** 脱敏响应与调用签名证明错误来自本系统传参
- **THEN** 覆盖核对明确工程阻断及受影响维度，修复前不能以来源受限关闭对应实施任务

#### Scenario: 能查询但未形成引用
- **WHEN** 合格事实已交付但报告没有直接或经 calculation/附件引用
- **THEN** 如实呈现未引用；若该事实承担本次要求的核心研究问题，则验收检查报告是否仍有其他合格依据，不能仅凭数量宣称完成

### Requirement: 八维验收必须同时满足执行和实质研究边界
经人工明确批准，本Change最终验收 MAY 使用原共同截止点八维执行基线，加同Gate/cutoff、同材料、受影响的基本面→研报两项补验，前提是其余六维的原最低内容和证据复用适用性均已逐项证实。若复核发现拟复用维度未消费本次要求的已准入核心资料，MUST NOT 用两项补验关闭该维度；可按明确授权准备并运行新的同Gate完整八维批次。验收记录 MUST 分别标明新旧证据/hash、实际运行范围与复用适用性，原报告不得覆盖，不得将跨包结果伪称新同批八维或严格A/B。最终报告仍须满足原实质研究、合法引用和来源限制标准，并经独立复核及人工完成批准；此批准只调整证据组织方式，不降低最低内容。

#### Scenario: 只补受影响两项
- **WHEN** 原八维执行完整、六维证据经复核可复用，且用户批准基本面→研报补验
- **THEN** 分别保存原八维与两项新报告并逐项核对目标，六维不重跑；任一受影响项内容未过仍不允许归档，不把局部运行宣称为新八维全部完成

原八维执行基线 SHALL 使用共同冻结截止点的 MRVL 研究包，八项均具有可验证执行终态和合法报告；最终内容验收按实际可复用性采用上述有条件的组合证据，或采用已授权的新同Gate完整八维批次，并逐项检查核心问题、代表性新资料消费、限制与引用。当前 host-v2 所有权报告仅查询机构汇总、未消费已准入内部人资料，故两项补验条件不成立；本轮 SHALL 以新完整八维批次验证，不将旧六维整体复用。可用核心资料必须产生有依据的解释；合法 gap-only 报告不计研究充分。已证实外部不可得的增强资料可保留具体限制，但参数、解析、路由、持久化或引用缺陷不得包装成可接受 gap。归档 MUST 保留独立复核与人工批准；本验收不代表 Skeptic/CIO 重跑、交易建议或回测通过。

#### Scenario: 所有权旧报告遗漏内部人资料
- **WHEN** 旧八维包已允许内部人交易 Evidence，但所有权报告只查询机构两期，不能回答原最低交易类型/时间限制问题
- **THEN** 该维度不得作为合格复用证据；本轮按明确授权的新完整同Gate八维批次逐维验收，旧报告和失败结论原样保留

#### Scenario: 共享改动影响拟复用维度
- **WHEN** 复核发现六维之一的输入、指令、工具或共享代码变化使原证据不再适用
- **THEN** 标明具体影响及缺证，提出必要补验与预算需求，不直接复用、不自动全量重跑，也不修改原报告或降低该维度最低内容标准

#### Scenario: 八份报告合法但同行未消费
- **WHEN** 八维报告均保存成功，行业报告却忽略已交付可比同行资料
- **THEN** 执行完成与研究充分性分别记录，本 Change 的行业实际消费项仍未完成

#### Scenario: 独立技术任务先于初始并发槽填满而结束
- **WHEN** 已授权的正式八维子任务先提交合法报告，而父线程尚未派满最大并发槽
- **THEN** 按实际身份、证据、引用和 Schema 校验报告并记录其终态，不以“尚未凑够并发数”阻止退出；后续派发仍受最大活跃并发和依赖门禁约束

#### Scenario: 超时后七项保存而技术维无终态
- **WHEN** 父进程超时，技术子任务已启动却无合法 Stop，其余七项已保存
- **THEN** 装配证明明确技术维失败且 `all_reports_valid=false`，不得把结构化基包或父运行 `PASSED` 当八维研究完成；仅在明确新增调用授权后，才允许既有最小依赖 retry 补验技术维并重验八项，旧报告和超时事件原样保留

#### Scenario: 修复后第三方多机构全文仍不可得
- **WHEN** 已正确尝试且现有授权只返回一份可读研究或标题线索
- **THEN** 保留具体第三方全文覆盖限制，以实际内容形成有限研究，不伪造多机构共识；其他七维按各自证据独立判断

### Requirement: 严格八维验收必须核对材料任务实际完成
显式严格验收入口 MUST 在启动正式研究前重验当前 dispatch/index 绑定的材料清单，预期任务恰有一项合法结果且没有缺失或 FAILED。阶段 PASSED、零退出码和 coverage_complete MUST NOT 单独作为放行依据。默认允许部分覆盖的产品路径保持其原有语义。

#### Scenario: 材料阶段带失败项成功收尾
- **WHEN** 三项合法、一项 FAILED，材料汇总仍返回 PASSED
- **THEN** 严格入口停止，正式八维模型调用数为零，失败保留；不能因汇总保存成功而提升研究完成状态

#### Scenario: 正文来源受限但任务已合法执行
- **WHEN** 每项材料任务均有合法结果，其中某项为有真实工具引用支持的 SOURCE_LIMITED 或 BLOCKED_CONFIGURATION
- **THEN** 将该项记为已执行且保留来源缺口；后续仍检查同行事实及核心输入是否满足要求，不能记成正文已取得或研究充分

#### Scenario: 缩小市场准备上下文后验证恢复
- **WHEN** 修补后市场资料发现再次运行
- **THEN** 恢复证明包含实际输入大小/hash、该 invocation 的搜索产物、结束事件和合法结果，只有启动或输入缩小不能证明超时恢复
