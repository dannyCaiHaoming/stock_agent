# multi-dimensional-holding-research Specification

## Purpose

在已确认普通股持仓与公司基本面研究基础上，逐步形成免费公开资料支持的多维研究资料包，明确每个方向的事实依据、分析结论、限制和下游用途，为后续独立反证与组合综合准备充分且可追溯的输入。


## Requirements

### Requirement: 研究阶段必须承接确认持仓并保持角色边界
系统 SHALL 提供显式多维持仓研究阶段，直接承接有效 PortfolioHandoff 与绑定 CouncilRequest，不要求用户重新录入或准备资料。系统 MUST 保留全部持仓且不限制数量，仅对普通股开展本次研究。系统 SHALL 按专业 Skill 分工并记录实际执行 Agent；公司研究仍归 Company Analyst，跨市场研究不得冒充公司结论。新阶段 MUST NOT 自动启动 Skeptic、CIO 决策、交易或修改账户。

#### Scenario: 混合持仓进入新阶段
- **WHEN** 确认输入包含普通股、ETF 与期权
- **THEN** 普通股逐项研究，其他持仓保留未覆盖状态，输出标注研究资料包而非完整组合决策

### Requirement: 来源选择必须以实际可用性和数据语义为依据
各能力 SHALL 声明字段、来源、费用/认证条件、历史覆盖、延迟、限流、缓存和失败原因。事实 MUST 保留 source_id、as_of、retrieved_at、可用的公开时间及证券身份；Agent 获取资料前 MUST 执行 PIT 过滤。历史修订数据不能以观察日期冒充当时已知数据。系统 MUST 区分来源不可用、未采集、尚未披露、字段缺失与不适用；不得买入数据服务、绕过访问限制或无限轮换来源。

#### Scenario: 免费 SDK 未返回所需历史数据
- **WHEN** 实际响应缺少研究所需字段或时间
- **THEN** 记录来源与字段限制，不把 SDK 安装成功记为研究能力完成，不用模型记忆填充

#### Scenario: 修订数据晚于截止时间
- **WHEN** 某宏观或公司事实只有截止时间之后公开的修订版本
- **THEN** 历史时点研究排除该版本或记录无法还原当时值，不发生未来泄漏

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

### Requirement: 基本面深化与事件必须围绕公司关键问题
Company Analyst SHALL 按公司特点深化业务分部、增长驱动、盈利正常化、现金流/资本开支、债务到期、流动性、稀释与估值中适用项目，并区分未披露与未取得。系统 SHALL 提供已公告事件、预期窗口及关键公司新闻的时间线，区分事实、管理层指引、估计日期和解释。缺资料不得强行量化或把日历预估称为公告。

#### Scenario: 资料支持一次性利润调整
- **WHEN** 同口径公开资料足以识别重大一次性项目
- **THEN** 展示原始盈利、调整项及确定性计算，解释持续盈利含义和税项限制

#### Scenario: 困境公司资料不足
- **WHEN** 已知现金余额但缺少现金使用限制或债务到期结构
- **THEN** 保留已知事实，明确不能计算生存期限，不用简单现金债务比替代流动性分析

### Requirement: 行业比较必须说明可比性和传导机制
系统 SHALL 基于明确理由选择同行或行业基准，比较业务、经营指标、估值或相对表现，区分行业周期与公司因素。同行选择及意义由 LLM 判断，计算由工具执行；币种、期间、会计基础和业务差异 MUST 显示。不能取得可比资料时不得生成同业排名。

#### Scenario: 同行业不同商业模式
- **WHEN** 同行具有不同业务结构或盈利状态
- **THEN** 说明差异及适用指标，不机械横比市盈率或以行业标签证明可比性

### Requirement: 宏观市场研究必须共享事实并连接持仓
系统 SHALL 在同一 decision cutoff 下分别形成 `MACRO_CONTEXT` 与 `MARKET_STATE` 两项共享研究输出。`MACRO_CONTEXT` MUST 覆盖适用的利率、通胀、经济活动与政策环境，区分观察期、发布时间和修订版本；`MARKET_STATE` MUST 覆盖适用的大盘、风格、波动、信用或流动性状态，并区分市场事实、解释和不确定性。两项输出 SHALL 分别说明对各持仓的具体传导路径、假设和反向情景，MUST NOT 将宏观判断或市场状态转换为确定性择时规则，也不得把共享叙述冒充公司事实。

#### Scenario: 多只普通股共享宏观环境
- **WHEN** 同批次有多只普通股且两项 capability 均具备合格输入
- **THEN** 系统各生成一份共享报告，各股分别解释敏感性；原始共享资料不重复采集，Macro 与 Market 的覆盖和缺口可独立核对

#### Scenario: 宏观资料可用但市场状态资料受限
- **WHEN** `MACRO_CONTEXT` 具备合格证据而 `MARKET_STATE` 的必要快照缺失或过期
- **THEN** 宏观报告继续形成，市场报告记录准确限制，系统不把宏观完成状态复制为市场完成状态

### Requirement: 所有权披露必须保留滞后与交易类型
系统 SHALL 在可取得资料范围内分析机构持仓变化及内部人交易，区分持仓日期、公开日期、修订、买卖与授予/行权等交易类型及原始数量。资料不足时不得声称聪明钱正在流入，披露持仓不得等同于完整投资组合或实时买卖。

#### Scenario: 两期持仓变化
- **WHEN** 具有可比机构披露
- **THEN** 展示两期原始值、变化、公开时间和覆盖限制，不将市值变化全部归因为主动增持

### Requirement: 期权与资金行为必须限定可推断范围
系统 SHALL 对普通股相关的可用期权快照研究期限、成交量、持仓量、价差及有依据的隐含波动率/偏斜；缺失或过期报价 MUST 限制分析。系统 MUST 区分交易量、持仓量、卖空统计、基金申赎与资金净流量，禁止用代理指标冒充直接资金流，禁止从成交量或持仓量单独推断买卖方向。该能力 MUST NOT 表示期权持仓估值、保证金或对冲决策已经完成。

#### Scenario: 只有单次期权链快照
- **WHEN** 没有历史持仓量或成交方向
- **THEN** 只解释该快照支持的结构，不生成持仓量变化、历史分位或看涨资金流结论

### Requirement: 多维研究必须形成可消费的同源产物
系统 SHALL 输出版本化结构化研究包与同源中文报告，包含持仓/请求绑定、cutoff、逐证券及共享维度报告、执行状态、研究充分程度、实际评价状态、主张/假设/计算/引用、缺口、观察条件和覆盖清单。所有引用 MUST 解析到当前允许的事实或明确标记的派生研究主张；研究主张不得冒充原始事实。不同维度冲突 MUST 保留，不得由拼接程序解决投资分歧。

#### Scenario: 基本面与技术结构方向不同
- **WHEN** 公司经营改善但价格结构偏弱
- **THEN** 两个判断各自保留依据和窗口，在研究包列出分歧及待解释问题，不自动产生买卖建议

### Requirement: canonical 交接包必须区分结构可解析与下游就绪
系统 SHALL 为最终交接包选择一个基础 run，并锁定 PortfolioHandoff、研究请求、证券身份、decision cutoff 与 Evidence Gate。每只普通股已有且兼容的 EquityResearchReport MUST 被引用为 `COMPANY_RESEARCH`；报告缺失、绑定不兼容或 Evidence 无法针对目标 Gate 闭合时，系统 MUST 保留具体缺口，且不得标记为 `DOWNSTREAM_READY`。Schema、绑定和引用可被程序读取时 MAY 标记为 `STRUCTURALLY_CONSUMABLE`，但该状态不得替代下游就绪判断。

补充报告只有在证券身份、capability、输入绑定、时间口径及 Evidence closure 针对目标交接包重新验证后，才 MAY 纳入 canonical 包。来自不同 run 或不同 decision cutoff 的补证 MUST 保留原始 provenance，并且在未统一验证时只能作为能力验收证据，不得静默合并为同一次用户研究。

`unresolved_cross_dimension_questions` MUST 记录报告中真实存在的分歧、限制、观察条件或待证伪问题，并引用相关报告；归集程序 MUST NOT 新增投资判断。若该集合为空，系统 MUST 提供 `no_unresolved_reason` 或等价的明确原因。存在实质冲突却没有问题或空值原因时，交接包 MUST NOT 标记为 `DOWNSTREAM_READY`。

#### Scenario: 兼容公司报告进入最终交接包
- **WHEN** 同一基础 run 中每只普通股都有通过绑定和引用校验的 EquityResearchReport
- **THEN** `COMPANY_RESEARCH` coverage 引用对应报告，消费方无需在交接包之外寻找公司研究

#### Scenario: 公司研究引用全部缺失
- **WHEN** 交接包可以通过基础 Schema，但普通股的 `COMPANY_RESEARCH` 全部为 `NOT_RESEARCHED`，而仓库中存在本次输入对应的公司报告
- **THEN** 系统 MAY 保留结构化产物用于诊断，但 MUST 拒绝 `DOWNSTREAM_READY`

#### Scenario: 不同截止时间的所有权补证
- **WHEN** 所有权报告来自不同 run 或不同 decision cutoff，且尚未针对目标 Evidence Gate 重新验证
- **THEN** 将其作为所有权能力验收证据单独引用，不加入 canonical 用户研究包，也不改写基础包的时间口径

#### Scenario: 报告之间存在待反证问题
- **WHEN** 已验证报告对趋势、经营驱动或风险给出不同窗口或相互制约的观察条件
- **THEN** 在 `unresolved_cross_dimension_questions` 中保存问题及报告引用，不由确定性归集器选择哪一方正确

### Requirement: 阶段验收必须有限且评价实际内容
系统 SHALL 按 Design 阶段顺序实施并逐阶段交付，来源核对随阶段推进，不以全部来源可用作为首阶段前置。价格技术、基本面/事件、行业、宏观为核心研究项，MUST 有真实资料及 LLM 实质输出；研报、所有权、期权/资金专项允许限定来源验证后记录 SOURCE_LIMITED，但 MUST NOT 标记为研究 PASS。核心项缺实质证据时相关任务保持未完成。最终 SHALL 区分实现、真实研究、来源受限与人工接受，不以平均分、字数、空泛 NO_TRADE 或固定结论证明完成。

#### Scenario: 专项免费来源不可用
- **WHEN** 声明的来源尝试预算用尽仍无可靠资料
- **THEN** 保存实际失败和影响，停止该来源尝试，继续不依赖它的工作；集中提交受限项供人工接受，不购买、不凑数或无限补跑

#### Scenario: 已有真实报告可以复用
- **WHEN** 已有报告的输入、方法版本与本次验收项仍一致
- **THEN** 复用明确绑定的证据，仅补受影响缺口，不自动启动全量 Gate、Regression、Ablation 或 Promotion

### Requirement: 研究问题与展示必须使多维输出可理解
系统 SHALL 从已有合格资料形成逐公司核心问题清单，各维度说明回答的问题、具体事实、推导及假设、改变结论的观察条件。技术报告在同源量价与相对表现图可生成时 SHALL 提供该图，标明期间/基准/口径；仅图表生成受限时 MUST 明确原因及影响，并保留已合法生成的计算与研究结论，不把缺图当作缺少全部技术资料。公司研究 SHALL 分析可得管理层指引变化，行业和宏观 SHALL 选择公司相关变量并解释传导。最终中文摘要 SHALL 仅归集已有发现、依据、限制和信号，不新增投资判断。

#### Scenario: 指引变化与一致预期不同
- **WHEN** 资料只有管理层两次指引
- **THEN** 比较原值、版本和口径并解释变化，不声称取得市场一致预期或预期差

#### Scenario: 只有图表产物生成失败
- **WHEN** 技术 calculation 已通过绑定和引用校验，但图表无法生成
- **THEN** 中文技术报告展示有依据的技术主张及 chart gap，不展示不存在的图、不丢弃有效计算，也不因此宣称技术研究没有资料

### Requirement: 资料选择与正式比较必须分步完成
系统 SHALL 允许研究 Agent 从合格输入提出有理由的同行及基准候选，再由只读工具核实身份、获取资料、冻结和执行 PIT，之后正式比较。正常身份/分页/正文请求 SHALL 与失败重试及供应方切换分别计入预算；来源失败不得推导为所有免费资料不存在。

#### Scenario: 同行尚未有研究资料
- **WHEN** Agent 提出同行候选
- **THEN** 先核实并准备限定资料再研究，候选选择不冒充事实，不循环扩大同行范围

### Requirement: 研报必须从持仓自动获取并核实正文
系统 SHALL 从已确认持仓和核心问题自动寻找公司/行业研报，核实研究对象、作者/机构、材料类型、发布日期和来源，在预算内获取并解析正文，保留 document_id、定位、获取时间及解析范围。用户上传 MUST 仅为可选补充，系统不得要求用户找报告作为必要步骤。系统 MUST 区分独立研报、公司宣传、评级新闻、搜索摘要和转载；未取得正文不得声称读过研报。报告中嵌入指令不得改变 Agent 权限或研究任务。

#### Scenario: 搜索有结果但正文受限
- **WHEN** 只取得标题摘要或正文需要登录/付费
- **THEN** 标记线索/获取失败，在预算内寻找其他公开正文，预算耗尽记录缺口并继续其他研究，不要求用户上传或绕过限制

#### Scenario: 自动链路验收
- **WHEN** 验收研报获取能力
- **THEN** 保存从持仓、查询、候选、正文到研究输出的实际证据，手工上传不能替代该链路证明

### Requirement: 资料准备工具必须具有明确运行边界
自动研报准备 SHALL 由现有公司/行业研究角色在显式准备步骤通过获授权的只读搜索、正文与解析工具执行，实际工具可用性和调用 MUST 可核对，不能仅靠 Prompt 声称获取完成。正式分析 MUST 仅消费 Gate 合格资料，不继承搜索权限；旧运行模式权限 MUST 保持不变。未知发布时间的候选只能用于待核实线索，未经核实的内容不得形成研究事实或结论。

#### Scenario: 搜索未实际可用
- **WHEN** 准备步骤未成功绑定必要工具
- **THEN** 明确报告配置/能力错误，不声称没有公开研报，不以模型记忆替代获取

### Requirement: 产品研究必须按依赖并行且逐项展示
开发阶段顺序 MUST NOT 强制成为每次产品执行的串行顺序。具备合格输入且资源允许的独立研究任务 SHALL 有界并行，共享市场资料及研究按范围复用；依赖任务 MUST 等待必要输入。单项失败 SHALL 只阻塞真实依赖项，共同输入非法仍停止相关研究。每份校验通过的报告 SHALL 及时提供路径及进度，最终按身份归集所有结果和缺口。

#### Scenario: 研报获取受限但技术资料已就绪
- **WHEN** 某公司的研报未取得且技术任务具备独立有效输入
- **THEN** 技术研究可继续，研报状态单独保留，不能因开发顺序强制等待

#### Scenario: 同行资料未就绪
- **WHEN** 同行候选已选出但资料尚未核实
- **THEN** 正式同行比较不提前运行，其他独立研究和已完成报告展示继续

### Requirement: 研报必须说明对当前研究判断的作用
采用研报后，研究 Agent SHALL 关联具体主张说明支持、挑战、修订或无新增信息及理由，不能只附摘要。需要修订时 MUST 保存旧新判断、证据与版本关系，不覆盖历史报告；不需要修订时不得为了体现价值强制改变结论。程序 MUST NOT 代替 Agent 作出修订判断。

#### Scenario: 研报提出不同盈利假设
- **WHEN** Agent 判断其影响当前公司结论
- **THEN** 明确受影响主张与假设，解释保留或修订原因并追溯依据，不仅罗列评级差异

### Requirement: 研报利益关系必须基于明确披露
系统 SHALL 保留材料中明确披露的赞助、付费委托及其他相关利益关系和定位；无法确认时 MUST 标为 UNKNOWN，不得推断独立或不存在关系。Agent SHALL 按具体内容解释使用限制，不因标签自动否定报告或生成确定性可信度评分，不要求额外背景调查。

#### Scenario: 研报没有可确认的利益关系信息
- **WHEN** 读取材料未找到可确认披露
- **THEN** 输出 UNKNOWN 并保留研究内容及其他来源限制，不声称无利益关系

### Requirement: 每个维度必须回答明确的最低研究问题
各维度 SHALL 覆盖 Design 第 5 节最低问题：技术的趋势/相对表现/波动量价/推翻条件；基本面的驱动/盈利现金流/估值假设/关键未知事件；研报的依据假设/分歧/判断作用；行业的相对位置/行业因素/可比性；宏观的相关变量/机制/反向情景；所有权及期权资金的实际观察/覆盖时效/推断边界。适用问题 MUST 有具体回答与依据，条件不适用或资料缺口 MUST 指明原因和影响；逐项缺口不能替代核心能力的实质样本标准。

#### Scenario: 技术报告只列指标数值
- **WHEN** 报告未解释趋势、相对表现或量价关系且没有具体缺口原因
- **THEN** 即使 Schema 合法也不满足研究内容验收，不用新增指标数量弥补解释缺失

### Requirement: 研报内容必须分层溯源并比较假设
研报研究 SHALL 区分已核实事实、未独立核实的转引、作者观点、预测与估值假设，保留页码/章节、单位、期间、source_id/as_of/retrieved_at 和可用原始出处。未能取得转引原始资料时 SHALL 明示限制并保留有价值内容，不自动升级为核实事实。比较 SHALL 解释共识、分歧、时间与信息集差异、方法及假设变化，并关联公司/行业主张；不得用评级投票产生动作。

#### Scenario: 预测期间在未来
- **WHEN** 截止时间前发布的研报预测未来年度收入
- **THEN** 可以作为当时已知的预测引用，明确目标期间，不能写成已实现收入；截止时间后发布的报告仍排除

#### Scenario: 转载与版本变化
- **WHEN** 多个页面转载同一研报或同一机构发布新旧版本
- **THEN** 转载只计一份来源，新旧版本标明时间和假设变化，不冒充多位独立作者的共识或同期冲突

#### Scenario: 表格金额无法辨认
- **WHEN** 正文解析缺页或数字单位不清楚
- **THEN** 明确解析范围和受影响判断，不猜测关键数字；仅一份正文时不宣称完成多报告对比

### Requirement: 开发证据时间与用户研究包必须区分
开发阶段验收 SHALL 允许分别绑定各自 cutoff；一次用户研究包 MUST 声明统一决策 cutoff，每项资料分别保留观察/公开/获取时间和时效。阶段报告复用 SHALL 检查身份、方法、窗口及事实适用性，仅更新不适用部分或标记缺口，不要求无关阶段重跑。所有普通股的每个维度 MUST 有结果或具体缺口，样本能力 PASS 不能替代实际批次覆盖。

#### Scenario: 历史时点缺少期权快照
- **WHEN** 已有核心报告的历史 cutoff 无可靠期权数据
- **THEN** 保留该维度缺口；另行取得当前快照只能用于明确当前时点的产物，不拼成历史同一次研究

### Requirement: 受限任务必须明确交付与延期能力
研报、所有权和期权/资金的条件任务 SHALL 分别定义可得与受限路径。可得路径 MUST 实现并验证实际研究；受限路径 MUST 保存限定尝试、原因、影响、未实现或未验证的子能力及明确责任，不能以未执行、代码错误、Change 已归档或配置存在代替。部分可得 MUST 保留已完成子能力。当前完成状态 MUST 以 SEC + Yahoo + Moomoo Singapore 数据集能力矩阵、实际 Capture → Normalize → PIT → MCP → Skill 消费证据及当前批次 coverage 为准；产品说明 MUST NOT 再把已归档 `capture-futu-client-research-data` 描述为未来延期目标，也不得把该 Change 归档解释为所有研报、13F、期权或资金行为在任意证券与 cutoff 下均可用。

#### Scenario: 只有内部人披露可得
- **WHEN** 内部人资料可用但机构可比持仓资料受限
- **THEN** 完成可用部分，单列机构子能力状态及证据，不将整个维度伪装成通过或全部不可用

#### Scenario: 已归档能力在当前批次受限
- **WHEN** 历史验收证明某数据集曾成功，但当前证券、权限或 cutoff 下无法取得合格输入
- **THEN** 系统保留历史能力证明并将当前覆盖标记为 SOURCE_LIMITED、PARTIAL 或准确失败状态，不引用已归档 Change 代替本次 Evidence

#### Scenario: 用户接受受限子能力延期
- **WHEN** 已保存限定来源尝试、具体失败、影响及明确责任，且用户接受本次受限结果
- **THEN** 条件任务可按 `SOURCE_LIMITED_ACCEPTED` 或等价状态收尾，但对应 capability 仍不得标记为 `RESEARCH_VALIDATED`

### Requirement: 当前多维草稿与报告必须遵守一致的结构契约
系统 MUST 为当前草稿和正式报告使用一致的权威嵌套结构定义，并锁定实际使用的契约版本/hash；历史版本仍按其原契约读取。系统 MUST 在派生计算、渲染与正式保存之前完整校验字段结构，另行执行身份、来源、PIT 和证据闭合校验。仅在 invocation 中声明 output_schema 不构成原生强制输出约束的证明，系统 MUST 核实实际生效边界并保留执行端校验。

#### Scenario: 草稿包含缺失或错误类型的嵌套字段
- **WHEN** claims 缺 question、data_gaps 缺 impact、limitations 项为对象或草稿含不允许的顶层字段
- **THEN** 系统在正式报告保存之前返回明确错误码、字段路径与预期结构，不产生原始 KeyError，不将草稿标记为有效报告

### Requirement: 多维输出纠正必须有界且由原 Agent 执行
可纠正的输出契约错误 SHALL 将原草稿、锁定契约与具体错误反馈给原 Agent/原会话；每任务初次提交后 MUST 最多允许一次纠正，重派不得重置预算。系统 MUST 保留原始输出、纠正输出及关联记录，并对纠正结果重跑完整校验。Python 或父线程 MUST NOT 代写研究判断或引用、静默删改主张以通过校验；缺失的实质内容只能由原 Agent 根据本次冻结资料补充。身份错配、越权引用、来源与时点违规 MUST 准确失败，不得伪装为纯格式纠正。原会话不可续接、超时或纠正仍失败 MUST 形成明确终态。

#### Scenario: 首次输出结构错误而原 Agent 纠正成功
- **WHEN** 首次草稿被结构校验拒绝，原 Agent 在一次纠正预算内提交新草稿并通过全部校验
- **THEN** 系统保存两次提交的追踪证据，仅将有效正式报告用于依赖任务，且冻结输入和身份绑定不变

#### Scenario: 纠正预算耗尽或发生不可纠正错误
- **WHEN** 纠正后仍非法、原会话无法续接或检测到身份错配及越权引用
- **THEN** 系统记录准确失败并结束该任务，不无限重试、不新建 Agent 绕过预算，也不将实现错误记为 SOURCE_LIMITED

### Requirement: 依赖任务必须按有效报告与明确终态推进
系统 MUST 仅在上游正式报告通过完整校验后解锁下游；纠正中不得提前认定成功或终态失败。上游最终失败 MUST 使依赖任务形成可追溯的 dependency-blocked 终态，独立任务继续执行，父线程不得无限等待缺失报告。调度终态齐全、报告结构可消费、报告有效与核心材料已消费 MUST 分别判断。

#### Scenario: Company 基础研究纠正期间有等待中的研报任务
- **WHEN** FUNDAMENTAL_EVENT 首次提交失败且仍在一次纠正预算内
- **THEN** RESEARCH_REPORT 保持等待；只有有效报告保存后才启动，若最终失败则记录 dependency-blocked，Macro 与 Market 不受该依赖阻塞

#### Scenario: 全部任务已结束但仍有非法报告
- **WHEN** 启动器或调度流程完成，而某任务输出无效或被依赖阻塞
- **THEN** 系统保留逐任务失败，不以 STRUCTURALLY_CONSUMABLE 或进程成功声明研究全部通过

### Requirement: 宏观市场能力拆分必须版本化并保持历史可读
新运行 MUST 使用包含 `MACRO_CONTEXT` 与 `MARKET_STATE` 的新版报告、研究包、stage 和 dispatch 契约，不得继续写入新的 `MACRO_MARKET` 报告。历史 `MACRO_MARKET` 报告和 `holding-research-bundle/1.1.0` MUST 继续按其锁定版本读取和校验；系统 MUST NOT 将一份历史合并报告自动复制成两份已验证的新能力报告。跨版本纳入新研究包时 MUST 显式标记兼容来源、实际覆盖和未拆分限制。

#### Scenario: 创建新的多维研究运行
- **WHEN** 当前入口准备新的研究任务集合
- **THEN** 任务、输出 schema 与 coverage 分别包含 `MACRO_CONTEXT` 和 `MARKET_STATE`，且不产生新的 `MACRO_MARKET` 任务

#### Scenario: 读取历史合并报告
- **WHEN** 消费方打开锁定旧 schema 的历史 `MACRO_MARKET` 产物
- **THEN** 旧产物仍可验证和展示，但只标记为历史合并覆盖，不自动满足新版两个 capability 的完成条件

### Requirement: 三域验收必须证明资料增量和受限边界
本次验收 MUST 在同一确认 Handoff/cutoff 下证明三域核心资料获取与真实研究消费，至少包含新增政策正文、市场新闻/跨资产输入，以及自动发现、去重并具有可核实正文定位的 issuer/IR 公司材料。核心项缺证据 MUST 保持未完成。独立研报全文与专有资料属于增强项；在限定来源验证后仍受限时 MUST 保存候选、失败、影响与具体覆盖，并仅在人工明确接受后按受限项收尾。公司 IR 不得冒充独立研报，但可在通过正文身份、去重和引用闭合后满足 Company 核心材料消费；新闻摘要和安装成功不能替代任何正文。已有证据只有在输入、实现版本及契约仍适用时才能复用，不要求重跑无关研究。

#### Scenario: 只有结构更新而无新增资料
- **WHEN** 三域任务和报告 schema 已通过测试，但未取得新增政策、市场和公司材料
- **THEN** 系统只能报告工程实现进度，不能判定三域信息能力补齐

#### Scenario: 独立研报正文确实受限
- **WHEN** 免费来源的有界真实尝试已结束，只有摘要或公司 IR，且用户明确接受该缺口
- **THEN** 该专项保留受限状态及影响，不宣称独立研报能力通过；其他核心项仍须真实闭环

#### Scenario: 当前版本的 Company 依赖链接受验收
- **WHEN** 完成确定性失败样例验证与宿主入口的 Company 依赖链验证，再进行同批三域验收
- **THEN** FUNDAMENTAL_EVENT 和 RESEARCH_REPORT 使用同一 Handoff/Gate/cutoff 与当前实现绑定，后者真实消费并引用去重后的 issuer 正文，逐股保存定位证据；单任务成功、跨批次报告拼接或结构可读均不替代该证明

#### Scenario: 验收中其他维度仍有引用失败
- **WHEN** INDUSTRY_COMPARISON 等任务仍出现证据闭合失败
- **THEN** 本次引入的回归必须修复并验证；声称既有且无关须提供可比基线与影响分析，保留失败状态且不得豁免核心项或宣称全包成功，独立复核核对该结论

### Requirement: Moomoo Evidence 选择必须按 dataset 和 semantic field 闭合
多维研究准备 MUST 为每项批准的 Moomoo 数据集维护显式的 capability 消费映射，并在 dispatch 前验证本次启用能力按规则应接收的合格 Evidence 实际进入目标任务的 `allowed_evidence_ids`。映射 MUST 覆盖分章节 Morningstar 与评级、机构/内部人/空头、Macro 补充、全市场期权统计、个股期权快照与供应商资金数据；不得仅依赖与实际 semantic field 不匹配的通用前缀。过期、去重、主源覆盖、专项未启用和预算裁剪 MUST 保留排除原因；只有缺少合法排除原因的应交付资料未交付才构成路由缺口。

#### Scenario: Moomoo 资料已冻结但未进入任务
- **WHEN** 数据准备包包含本次启用 capability 按规则应接收的合格 Moomoo Evidence，无合法排除原因，而其允许列表中没有相关 ID
- **THEN** 准备阶段报告 capability 路由不闭合并拒绝把该数据集记为已消费

#### Scenario: Moomoo 资料进入错误任务
- **WHEN** 某证券的期权、资金、评级或所有权 Evidence 被选入错误证券或错误 capability
- **THEN** 身份和数据集校验 fail closed，不由 Agent 自行忽略或重新解释

#### Scenario: 资料被合理排除
- **WHEN** 已采集资料因过期、重复、主源覆盖、专项未启用或预算被排除
- **THEN** 记录数量、原因与影响，不触发路由故障，也不宣称该资料已被使用

#### Scenario: 资料交付但没有研究引用
- **WHEN** Evidence 已进入允许列表但有效报告没有引用或解释它
- **THEN** 状态只证明交付，不证明实际使用；验收检查代表资料的正确引用，不强迫每条 Evidence 都被引用

### Requirement: OPTIONS_FLOW 必须消费有界动态结构而非静态目录
`OPTIONS_FLOW` MUST 优先消费同一 cutoff、同一标的和明确交易时段的有界动态期权快照，至少说明实际可得的期限、行权价、bid/ask、volume、OI、IV 与字段时间。只有静态链或部分字段时 SHALL 输出 `SOURCE_LIMITED` 或 `PARTIAL` 及具体影响；不得用全市场 Put/Call、个股 capital flow、short interest 或静态合约数量替代合约级动态结构，也不得由单次快照推断主动买卖方向或 OI 变化。

#### Scenario: 动态快照字段足够
- **WHEN** 选定合约的价差、成交量、OI、IV 和时间语义通过 Gate
- **THEN** `OPTIONS_FLOW` 可解释期限、流动性和波动结构，同时保留单次快照不能证明方向或变化的限制

#### Scenario: 只有全市场 Put/Call 统计
- **WHEN** 合约级快照失败但美国市场级 option volume/OI ratio 可得
- **THEN** 统计只能作为共享市场背景，个股 `OPTIONS_FLOW` 仍保留合约级资料缺口，不把市场比率归因于该公司

#### Scenario: 供应商资本流可得
- **WHEN** 个股 capital flow 或 distribution 通过 Gate
- **THEN** `OPTIONS_FLOW` 或对应 Market 专项将其作为独立 `VENDOR_CALCULATED_FLOW` 观察，不与期权成交量、Short Interest、13F 或真实买卖方身份合并

### Requirement: Company、Macro、Market 和所有权研究必须保留供应商层级
专业研究 MUST 将 Moomoo Morningstar/评级视为外部观点，将机构/内部人/空头数据视为二级披露补充，将 Macro History 视为二级供应商序列，将 FedWatch 视为市场预期。Agent MUST 对每项主张引用目标 capability 允许的冻结 Evidence，并说明与 SEC、BLS、Treasury、Federal Reserve 或 Yahoo 主源的关系、冲突及限制；不得把供应商覆盖或当前值升级为官方事实、独立研报共识或历史 vintage。

#### Scenario: Morningstar 只有一份可读材料
- **WHEN** `RESEARCH_REPORT` 只取得一份 Morningstar 正文或部分 section
- **THEN** 报告可以分析该材料对当前主张的支持、挑战或限制，但不得声称完成多机构独立研报比较

#### Scenario: Moomoo ownership 与 SEC 冲突
- **WHEN** Moomoo 机构汇总或内部人标签与 SEC 原始申报不一致
- **THEN** `OWNERSHIP_DISCLOSURE` 以 SEC 原文为事实锚点并保留供应商冲突，不静默覆盖或生成确定性可信度分数

#### Scenario: Macro 补充只有供应商值
- **WHEN** Moomoo 提供某项宏观实际或 consensus 而官方主源未覆盖
- **THEN** `MACRO_CONTEXT` 明确说明二级来源、观察期、发布时间和 revision/vintage 限制，并将 consensus 与 actual 分开引用

### Requirement: Moomoo 扩展验收必须证明专项实际消费
本 Change 的完成 MUST 至少对一只当前确认持仓普通股证明动态 options snapshot 的 `Capture → Normalize → PIT → Gate/MCP → OPTIONS_FLOW` 闭环，并对 Company、Macro、共享 Market 三域分别证明至少一项资料完成正式交付与报告中的正确引用/解释，来源允许为合格 SEC、Yahoo、官方宏观或 Moomoo，不要求每域 Moomoo 成功。三域覆盖及剩余缺口清单和候选取舍 MUST 完整；最低验收样本不代表全部信息已覆盖。Adapter 测试、AAPL 直接 Spike、配置 hash、静态链和 provider `AVAILABLE` 状态均不能单独替代该验收。受权限或免费覆盖限制的增强项可以保留 `SOURCE_LIMITED_ACCEPTED`，已有来源足够或复杂扩展的候选保留明确取舍；动态期权核心、三域使用证据或消费路由回归未完成时不得归档。

#### Scenario: AAPL Spike 成功但持仓未消费
- **WHEN** AAPL 的直接 SDK Spike 成功，而确认持仓证券没有动态期权和目标任务引用证据
- **THEN** 只保留能力可行性证明，Change 完成条件仍未满足

#### Scenario: 当前持仓没有可交易期权
- **WHEN** 确认持仓普通股均确实没有合格期权合约或当前权限无法取得动态快照
- **THEN** 系统保存逐证券真实尝试和影响；该核心条件只有在用户明确接受范围调整后才能改为受限收尾，不得用市场级统计或非持仓样本自动替代

#### Scenario: Macro 资料未进入研究而 Market 已成功
- **WHEN** Company 和 Market 已有有效使用证据，但 Macro 没有任何合格来源完成正式交付与使用
- **THEN** 三域验收未完成，不用 Market 成功替代 Macro

#### Scenario: Moomoo 受限但官方宏观满足研究
- **WHEN** Moomoo Macro 不可用，而合格官方宏观资料完成交付与正确引用
- **THEN** Macro 域可通过验收，同时保留 Moomoo 数据集限制

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

### Requirement: 研报观察条件引用必须闭合且不丢失有效内容
`RESEARCH_REPORT` 正式报告的观察条件、失效条件及其他 Claim 引用 MUST 指向同一报告真实存在的 Claim ID，并保持报告、Evidence 与附件引用闭合。悬空引用 SHALL 在保存和下游交接前按现有有界纠正规则交原 Agent 处理；无法纠正时保留明确失败及已合法完成的独立维度，不得通过删除观察条件、创建虚构 Claim 或只因 JSON 可解析就标为完成。

#### Scenario: 观察条件引用不存在的 Claim
- **WHEN** `RESEARCH_REPORT` 草稿出现 `DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING`
- **THEN** 将该报告内 Claim 条件引用错误纳入现有一次原 Agent 纠正入口，返回具体引用路径及报告内合法 Claim IDs；纠正后重新执行全部契约校验，仍非法则该任务失败且下游不可将它视作合格研报研究

#### Scenario: 纠正次数已用尽或错误不在允许范围
- **WHEN** 原任务的一次纠正已用尽，或报告失败属于 Evidence/PIT/权限违规
- **THEN** 本次新增的条件引用纠正路径不得继续调用或承接这些错误，保留失败；不得扩大通用重试、删除内容或放宽校验

#### Scenario: 研报正文来源受限
- **WHEN** 正文不可得但报告合理记录 `SOURCE_LIMITED` 与受影响判断
- **THEN** 保留合法缺口及其他维度已完成结果，不为使研报维度显示 COMPLETE 而伪造引用或正文
