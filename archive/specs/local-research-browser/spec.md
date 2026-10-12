# local-research-browser Specification

## Purpose

为本机用户提供按 Macro、Market、Company 分类的研究资料浏览入口，读取已保存事实、冻结版本、图形和报告，准确呈现时间、来源、覆盖与变化，并通过独立只读消费边界支持后续研究能力扩展而不干扰既有 Agent 调度。

## Requirements

### Requirement: 已有持久化资料必须完整解析且缺陷修复独立于浏览
系统 MUST 在保存 Research View 前确认所选事实版本已持久化且可校验，失败不得提交可被误认有效的 View 或推进对应成功状态。浏览 MUST 对所选 View 的唯一引用逐条核对，给出引用总数、成功解析数、缺失数和校验失败数；分页不得改变完整性结论。缺失引用不得被静默跳过或表述为来源未采集。已有有效部分可继续阅读，但不完整 View MUST 明确警告，不得参与完整版本比较的成功验收。

#### Scenario: View 含有数据库中不存在的引用
- **WHEN** View 引用 N 个唯一版本，但只有 M 个版本存在且校验通过
- **THEN** 明确列出其余引用的缺失或校验失败原因，不能以 M 条成功读取及零损坏宣称 View 完整，也不能从最新事实目录补入旧 View

#### Scenario: 修复历史引用
- **WHEN** 对既有 MRVL 数据执行独立离线修复
- **THEN** 先只读预检，仅依据可验证的原始冻结对象和原 cutoff 重建；保留旧 View/报告及原 hash，记录修复前后映射与原因，重复执行不重复产生修复版本；证据不足则保留未解决状态，不猜测匹配、不补采、不调用模型、不推进采集水位；写入失败可恢复且不留下半成品。稳定目录写入须具备实际授权，浏览不触发修复

### Requirement: 默认阅读必须呈现有意义的指标与逐项证据
Company 默认页面 MUST 按公司概览与日期、核心财务、行情估值、披露与研究组织。核心财务至少适配营收、净利润、稀释 EPS、经营现金流、资本开支、现金和债务中已保存且口径可识别的字段；缺项分别说明原因，不要求新采集或新计算。默认展示中文名称、单位、币种、财务期间和适当显示精度，详情保留原值。逐日价格长表、原始 Evidence、hash、checkpoint 和 attempt MUST 默认收起或置于独立详情，不得占据主阅读流程。

#### Scenario: 无模型报告但已有财务事实
- **WHEN** 所选有效 View 有可识别的营收、利润、EPS 或现金流
- **THEN** 无需模型报告或专用图形附件即可显示对应指标和期间表；可比历史足够时绘制同指标趋势，不得以附件未生成隐藏已有数值

#### Scenario: 从数值查看证据
- **WHEN** 用户打开任一指标或图表点的来源详情
- **THEN** 可定位其事实版本或附件行、所选 View/报告绑定、source_id、as_of、retrieved_at、期间、单位及已有原文链接；派生指标保留既有计算及输入引用，不以笼统来源首页冒充逐项证据。正文未保存时说明仅有链接或摘录

### Requirement: 图表可用性必须由实际数据及语义决定
图表 MUST 核对实际非空数据、可识别指标和时间轴后才标为可用；财务指标分别成图，同一序列不得混合币种、金额与每股值、季度与累计或年度期间。相同 period_end 不代表同一财务期间，必须同时识别 period_start 和期间类型；不能确定时表格展示并说明不可比。价格口径一致，成交量独立分区，不能只画价格却宣称已显示成交量。历史估值仅消费已有合格序列，不增加估值算法。

#### Scenario: 只有单点或多个不兼容期间
- **WHEN** 某指标只有一个有效观测或存在不可比较的期间
- **THEN** 单点显示指标/表格而不伪造趋势；不兼容期间分组，缺口不填零，不将其他财务指标拼接成曲线

#### Scenario: 切换版本及同截止点的不同运行
- **WHEN** 用户切换已保存 View，或存在相同 security/cutoff 但不同 run 的附件
- **THEN** 标题日期、指标、图表、来源随所选版本一致切换，附件须验证 run、证券、cutoff、版本及 hash，不能只按 cutoff 匹配；最近检查和最近报告可独立展示，但必须明确不是所选历史版本的事实

### Requirement: 浏览端必须具有独立的只读能力契约
系统 SHALL 接收显式本地 Memory 位置、可选冻结产物目录和浏览筛选，以确定性读取、校验和格式化生成页面。服务 MUST 仅允许本机访问；启动、阅读、搜索和页面刷新不得调用 Provider、模型、研究调度或修改事实、checkpoint、报告、复用事件及数据库版本，不得创建缺失的 Memory。网页停止、依赖未安装或展示失败 MUST 不影响原有采集、研究及保存。

#### Scenario: 数据库不存在或版本不兼容
- **WHEN** 配置位置缺库、权限不足或数据库版本不受支持
- **THEN** 页面或启动诊断明确原因，不创建或迁移数据库，其他可独立读取的资料仍可浏览

#### Scenario: 同时研究和浏览
- **WHEN** 现有采集器提交资料且用户正在浏览
- **THEN** 浏览使用完整已提交版本，读取有界且不长期占用事务；短暂繁忙显示可重试状态，不干预采集器或使用忽略 WAL 的不一致读法

### Requirement: 分类必须依据研究对象与能力
系统 SHALL 提供 Macro、Market、Company 导航，按对象、能力和产物类型归类；Agent 名称仅作来源信息。共享报告 SHALL 保留单一报告身份并可从多个相关栏目访问。公司列表 MUST 标为已保存公司，仅凭库中存在记录不得声称是当前持仓；首版不推断持仓身份。每家公司 MUST 至少以验证后的 ticker 或 `security_id` 标识，公司名称只在合格资料存在时显示，缺少名称不得阻止浏览。

#### Scenario: 同行或历史股票存在于资料库
- **WHEN** 公司有资料但没有本次明确的持仓绑定
- **THEN** 公司可搜索和查看，但不显示当前持仓标记

### Requirement: Company 必须支持资料和研究分别浏览
系统 SHALL 提供公司搜索、列表、详情与已有版本选择。详情 SHALL 以概览、财务、行情与估值、研究记录、数据来源五个主要阅读区域组织；披露与事件在财务或研究区域按时间线呈现。数据表和原文可用性不得依赖模型报告存在。财务期间、单位、币种、会计口径、来源值与派生值 MUST 明确；缺少专用附件时保留已有事实表，并说明专用图形未生成。

#### Scenario: 已采集但未研究
- **WHEN** 公司已有事实和 View 但无有效报告
- **THEN** 展示资料、图形中实际可用部分及“尚无研究报告”，不自动调用模型

#### Scenario: 估值或财务不适用
- **WHEN** PE 亏损不适用、历史 EPS 不足或财务期间不可比
- **THEN** 分别展示原因，缺失不填零，不跨口径连接趋势，不以最新预测回填历史

### Requirement: 已保存披露与公司事件必须转化为可读事实时间线
系统 SHALL 将所选 View 中已经保存的 `business`、`management_discussion`、`risk_factors`、`ownership_insider_transaction` 及后续明确支持的事件事实，按公开时间、报告期、表单类型和来源组织为公司披露与事件时间线。默认卡片 MUST 显示人类可读标题、事件/披露类型、日期、有效摘录、来源状态和原文入口；不得只展示 semantic field、hash 或原始价格/事实列表。相同申报中的目录短句、标题片段和实质正文并存时，展示层 SHALL 保留可追溯性并优先正文、折叠明显目录占位，不能删除或改写底层事实。Form 4 等结构化内容 SHALL 确定性解释交易类型、数量、价格及交易后持有量中实际存在的字段，但不得据此生成投资影响判断。

#### Scenario: 同一披露同时含目录占位和正文
- **WHEN** 同一来源、表单、报告期和语义字段存在短目录片段与可验证正文
- **THEN** 时间线默认展示正文并标记存在折叠的重复片段；来源详情仍可查看各事实版本，不把目录文字当作事件解读

#### Scenario: 只有披露事实而没有研究解读
- **WHEN** 公司已有 10-K、10-Q 或 Form 4 事实，但没有绑定的 Company Agent 或多维研究报告
- **THEN** 展示可读事实时间线并明确“尚无已保存研究解读”，不得把事实摘录冒充模型结论，也不得在浏览时调用模型

### Requirement: 已保存 Company Agent 报告必须按真实契约完整呈现
系统 MUST 为受支持的真实报告契约提供版本化适配。对 `equity-research-report/1.0.0`，页面 SHALL 展示报告状态、`research_summary`、六个命名研究章节、claims 及其证据关系、assumptions、催化剂与反证、invalidation conditions、reevaluation triggers、monitoring indicators、data gaps、confidence 和 confidence rationale；不能依赖不存在的顶层 `summary` 字段，也不能假定 `sections` 为数组。研究结论 MUST 保持原报告的 security、run、cutoff、View、附件和 hash 绑定，页面不得用最新事实改写历史报告。已有 `FUNDAMENTAL_EVENT`、`RESEARCH_REPORT`、`OWNERSHIP_DISCLOSURE`、`INDUSTRY_COMPARISON` 多维报告 MAY 作为补充研究卡片显示，但只有绑定闭合且格式受支持时才可呈现为有效解读。

#### Scenario: 真实 Company Agent 报告存在
- **WHEN** 报告索引指向校验通过的 `equity-research-report/1.0.0` 包
- **THEN** 用户可以阅读报告状态、摘要、六个章节、主要证据与假设、反证/失效条件、监控、缺口及置信度依据；页面不退化成原始 JSON、空章节或只显示元数据

#### Scenario: 稳定 Memory 没有报告索引
- **WHEN** 当前稳定公司 Memory 只有事实和 View，或前次运行仅为 `--prepare-only`
- **THEN** 明确显示“尚无已保存 Company Agent 报告”，不得表述为报告损坏、持久化失败或没有公司事件；报告渲染能力使用契约有效的确定性样本验收

#### Scenario: 多维研究报告缺失或绑定不闭合
- **WHEN** 某种补充研究能力没有已保存报告，或报告的公司、run、cutoff、证据或 hash 不匹配
- **THEN** 分别显示“未生成”或“绑定校验失败”，不借用其他运行的报告，不推断该类事件、机构动作或外部观点不存在

### Requirement: Macro 与 Market 必须按现有产物覆盖呈现
系统 SHALL 从一个或多个显式配置的运行目录读取已支持的宏观、市场与研究产物，并可从显式配置的运行根目录仅发现直属且具有已知 manifest 的运行子目录；不得无界递归扫描磁盘。Macro SHALL 展示实际保存的 CPI 指数、失业率、10Y 收益率及来源时间；不得将 CPI 指数直接标为通胀同比。Market SHALL 展示已保存基准的日线图、已有收益/波动/回撤/成交量计算和研究报告。缺失计算或不足窗口 MUST 显示原因，不要求运行 Agent 或补采才能打开页面。

#### Scenario: 只有一次宏观快照
- **WHEN** 仅有一次合格宏观观测且无可验证历史序列
- **THEN** 展示该观测，不伪造趋势或涨跌；资料无 historical vintage 时明确其限制

#### Scenario: 配置目录消失或基准历史不足
- **WHEN** 冻结目录不可用或 252 日指标输入不足
- **THEN** 显示对应来源不可用或历史不足，其他栏目继续工作，不宣称长期历史已完整保存

#### Scenario: 同一产物从多个目录被发现
- **WHEN** 多个配置目录包含相同稳定身份和内容 hash 的产物，或包含身份相同但内容不同的产物
- **THEN** 相同内容只展示一次；内容冲突以数据冲突提示隔离，不按目录顺序静默覆盖

### Requirement: 时间选择必须绑定已保存版本
系统 SHALL 默认展示各对象最新可用的已保存 View 或快照，并提供其历史版本列表。页面 MUST 显示资料截止、观察期和报告研究时间；来源与数据状态详情 MUST 可查 source_id、as_of、retrieved_at，以及存在的公开和检查时间。最新资料与最近报告可以日期不同，但 MUST 分别标记。日期区间筛选只改变图表显示窗口，不能冒充任意时点研究重建。

#### Scenario: 新资料与旧报告并存
- **WHEN** 数据已更新但最近有效报告仍绑定旧 View
- **THEN** 最新资料页标明各自日期，打开报告仍使用原证据和附件，不以新数字替换旧报告

#### Scenario: 用户选择没有保存版本的日期
- **WHEN** 该日期没有实际 View 或快照
- **THEN** 显示可选的已有版本及实际截止点，不悄悄生成或伪装一个该日期版本

### Requirement: 历史比较必须保持事实与判断边界
系统 SHALL 支持同一公司的两份已保存 View 比较，区分新增、修订、仅出现在一侧及未变化事实；比较 MUST 使用已选事实身份、逻辑键、内容版本及期间/单位，而非仅按数值或 Evidence ID。仅出现在一侧不得被解释为真实事实消失。报告 SHALL 支持原文并排阅读，不自动总结 Thesis 变化或生成投资判断。

#### Scenario: 检索时间改变而事实不变
- **WHEN** 两个 View 引用相同内容版本但检查时间不同
- **THEN** 不标为事实修订；变化来源和无法比较的字段可查

### Requirement: 图表和报告必须绑定可验证来源
系统 SHALL 复用已验证图表附件与报告包，核对证券、run、cutoff、版本和 hash，并提供表格替代、实际窗口、单位和缺口。价格/成交量、相对表现/回撤、财务趋势、历史估值四组核心展示路径 MUST 各自产生有效图表或带具体原因的限制卡，不要求所有组都有有效曲线。历史不足或附件缺失 MUST 保留明确限制；单项损坏只隔离对应展示。浏览层不得新增估值或主观研究算法。可信来源链接 SHALL 支持用户主动打开，页面自身不得自动加载外部脚本、图片或数据。

#### Scenario: 附件被修改或旧报告没有图表
- **WHEN** 某附件校验失败或旧报告未提供该附件
- **THEN** 拒绝展示该附件为有效图形，分别标为损坏或未生成；仍展示可独立验证的报告内容，不改写历史

### Requirement: 展示适配必须支持增量扩展与兼容降级
系统 SHALL 按产物类型、schema version、能力及对象选择读取与呈现规则。已有类型增加证券和记录 MUST 自动进入浏览；新增受支持字段或能力 SHALL 可以局部增加映射或适配器，不要求修改研究调度或所有 Agent 输出。测试样本 MUST 使用对应生产 schema 的合法结构，不得以简化的旧假格式替代真实契约并宣称兼容。未知版本 MUST 显示最小产物信息及暂不支持提示，不猜测字段含义、不泄露未审查原始内容且不阻断其他页面。浏览适配是否完成 MUST 不成为任何 Agent 能力开发、运行或自身验收的前置条件。

#### Scenario: 后续 Agent 产生新类型报告
- **WHEN** 配置目录出现浏览端尚未支持的格式
- **THEN** 安全提示该产物未支持；已有 Company、Macro、Market 页面仍可正常读取

### Requirement: 浏览必须限制文件与私人上下文暴露
系统 MUST 只读取显式准入目录及校验通过的对象引用，拒绝路径穿越、符号链接逃逸及任意文件读取请求。页面、接口和下载 MUST 默认排除原请求中的私人提问、账户/组合上下文、凭据和本机绝对路径；已验证报告正文可保留研究解释。来源文本与 Markdown/HTML MUST 安全呈现，不能执行附带脚本；首版不提供完整原始报告包下载。

#### Scenario: 恶意文本和越界附件
- **WHEN** 来源包含脚本或附件引用指向准入目录外
- **THEN** 脚本不执行，越界请求被拒绝，接口不返回私人字段或原始路径

### Requirement: 资料状态必须可理解且互不混淆
系统 SHALL 将数据覆盖、来源检查状态、执行状态和研究充分性分别展示，保留原始状态可查；首页和公司列表优先展示资料截止、最近实际检查、报告研究截止、覆盖提示与最近报告。最近检查 MUST 来自与该对象绑定的最新采集尝试、复用事件或等价已保存检查记录，不得用报告首次存储时间冒充。checkpoint、采集尝试、覆盖、待补缺口和版本细节 SHALL 放入可展开区域。无变化检查、来源失败及未尝试 MUST 不混为同一种状态。重新扫描操作 MUST 明确只重新读取已配置本地目录，不得表述为联网刷新资料。

#### Scenario: 检查成功但复用旧研究
- **WHEN** 最近检查未产生新事实且报告被复用
- **THEN** 展示实际检查时间与原报告时间，不声称模型本次重新研究

### Requirement: 浏览验收必须覆盖真实阅读与隔离行为
验收 SHALL 使用既有 MRVL 真实 Memory 验证公司搜索、事实、View、状态和实际可用附件；真实报告存在时继续验证其原包阅读，稳定 Memory 没有报告索引时 MUST 正确显示“尚无报告”，并以明确标记的确定性报告样本验证报告页面。其他确定性样本 SHALL 覆盖历史比较、Macro/Market 完整与受限情况、新格式兼容、并发和安全边界。MUST 实际查看桌面及窄屏页面，核对中文、轴、负值、缺口、长表和导航；仅文件生成不算视觉通过。无真实 MRVL Memory 时 MUST 记录该项阻断，不换证券冒充验收；缺少真实宏观、市场、MRVL 报告或第二份模型报告不要求新增来源访问或模型运行，也不得阻止已实现浏览能力按上述证据收口。

下一版验收 MUST 对目标 MRVL 有效 View 证明所有引用成功解析且校验通过，并核对已有营收、净利润、稀释 EPS、经营现金流从冻结来源到页面的数值、期间、单位和证据。已保存且有效的数据因引用或映射错误未显示 MUST 阻断验收；真正没有的历史 PE/报告不阻断，但必须记录原因。发现的旧不完整 View 保留可见警告；不得删除引用以凑齐完整率。视觉验收 MUST 实际完成“找到最新营收及期间→查看趋势→打开对应来源→切换历史版本”阅读路径，并确认默认页不展开价格长表和内部状态。原测试通过及旧 verification 记录不得替代本轮验收。

本轮补充验收 MUST 使用真实 schema 有效的 `equity-research-report/1.0.0` 样本检查状态、摘要、六章节、claims/证据、assumptions、反证、失效、监控、缺口与置信度依据，并使用包含正文/目录重复及 Form 4 的事实样本检查事件时间线。若稳定 MRVL 仍无报告索引，真实页面的“尚无报告”与样本报告的完整渲染 SHALL 分别验收。8-K、业绩新闻稿/电话会、公司指引、一般新闻、外部研报和历史 PE 等尚未保存的数据 SHALL 记录为后续数据缺口，不得阻断本 Change 对已有数据正确展示的验收，也不得被页面表述为“无事件”“无观点”或“无估值历史”。

#### Scenario: 浏览前后持久化状态验证
- **WHEN** 执行搜索、详情、版本比较和页面刷新
- **THEN** 确认浏览未产生数据库 DML、迁移或外部采集，事实、checkpoint、报告与复用状态无浏览导致的变化；并发写入测试单独核算写入器的预期变化

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
