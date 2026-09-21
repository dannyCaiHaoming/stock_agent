## Purpose

为美股普通股持仓研究提供 SEC、Yahoo 与 Moomoo Singapore 组合的只读资料入口，按原始披露、市场数据与供应商研究资料分工，输出可追溯的 point-in-time Evidence。保留既有 capability 路径作为历史责任引用，不再要求所有数据依赖富途牛牛客户端 Cookie 重放。

## Requirements

### Requirement: 三源组合必须按数据集声明职责和区域
系统 MUST 将 SEC 用于原始财报与所有权披露，Yahoo 用于行情、公司行动、基准及可得期权，Moomoo Singapore 用于供应商资金流、机构补充资料、期权补充与研报候选/可读正文。Moomoo 服务区域 MUST 为 SG，研究证券范围仍为美股普通股。系统 MUST 保留来源选择、回退原因与冲突证据，不得将三源任意互换。

#### Scenario: Yahoo 期权受限且 Moomoo SG 有合格快照
- **WHEN** Yahoo 期权失败且已批准的 Moomoo SG 同数据集请求成功
- **THEN** 系统显式记录回退及各源状态，保留 Moomoo SG 血缘，不伪装为 Yahoo 数据

#### Scenario: 资金流不可得
- **WHEN** Moomoo SG 资金流受限而 SEC 持仓或 Yahoo 成交量可得
- **THEN** 资金流仍记录缺口，不以持仓变化或成交量替代供应商资金流

### Requirement: 来源可行性必须独立验证
系统 MUST 分别验证三源真实只读访问、证券身份、字段、时点与使用边界。SEC/Yahoo MUST NOT 依赖 Moomoo OpenD 成功才允许运行；Moomoo SG MUST 在数据集扩展前通过官方 SDK 与本机 loopback OpenD 证明 `OPEND_QUOTE_FEASIBLE`。OpenD 进程存在、Moomoo App 已登录、文档声明及合成 fixture MUST NOT 代替真实 Quote API 验证。

#### Scenario: Moomoo SG 不可调用
- **WHEN** Moomoo SG 存在 OpenD 未就绪、行情未登录、版本不兼容、权限或契约阻断
- **THEN** 系统停止受影响路线，SEC/Yahoo 继续形成可用研究证据，整体完成状态保留 Moomoo 缺口

#### Scenario: Moomoo App 已登录但 OpenD 未验证
- **WHEN** 当前 Mac 的 Moomoo App 已登录，但 loopback OpenD 的 Quote API 状态尚未验证
- **THEN** 系统记录 OpenD 能力未验证，不读取 App Cookie、Keychain 或私有会话文件

### Requirement: 能力矩阵必须反映真实观测
系统 MUST 按 provider、service_region、security、dataset 和字段记录 NOT_ATTEMPTED、AVAILABLE、PARTIAL、SOURCE_LIMITED、UNSUPPORTED 或准确失败状态，并保存尝试时间、OpenD/SDK/API 版本、字段覆盖、限制及证据引用。失败状态 MUST 区分 `OPEND_UNREACHABLE`、`QUOTE_NOT_LOGGED_IN`、`OPEND_VERSION_UNSUPPORTED`、`SDK_VERSION_UNSUPPORTED`、`ENTITLEMENT_REQUIRED`、`RATE_LIMITED`、`API_UNAVAILABLE`、`CONTRACT_MISMATCH` 与来源政策阻断。

#### Scenario: 官方方法存在但尚未请求
- **WHEN** 官方文档列出 Moomoo SG 机构资料方法但本机 OpenD 尚无实际成功响应
- **THEN** 对应能力为 NOT_ATTEMPTED，不能标记 AVAILABLE 或已证明 SOURCE_LIMITED

#### Scenario: 期权只有静态信息
- **WHEN** 合约信息可得而报价、OI 或其他研究必需字段不足
- **THEN** 系统记录 PARTIAL、STATIC_CHAIN_ONLY 或具体字段缺口，禁止推导不受支持的研究结论

### Requirement: SEC 必须保留原始申报语义和覆盖范围
SEC 资料 MUST 保留 accession、申报者、证券映射、表单类型、报告期、公开/提交时间、修订关系和原文定位。13F MUST 使用实际管理人申报/信息表，保留管理人覆盖集合、分页及缺失范围，不把 Companyfacts 或发行人 submissions 当全体机构持仓清单。内部人申报 MUST 区分交易日与申报日、交易代码、直接/间接及衍生品性质。

#### Scenario: 两期机构原文可比
- **WHEN** 同一管理人和证券有两期可比申报，公开时间满足 cutoff 且修订、单位和公司行动已核对
- **THEN** 系统保留两期原值与确定性变化计算，同时披露样本覆盖和申报滞后

#### Scenario: 证券映射或覆盖不完整
- **WHEN** CUSIP 映射未核实或只取得部分管理人申报
- **THEN** 未核实记录不进入证券事实，部分集合不得宣称全市场机构持仓或完整趋势

#### Scenario: 内部人交易分类不同
- **WHEN** 申报包含授予、行权、转让或公开市场交易
- **THEN** 系统保留原始交易代码与性质，不统一解释为主动买卖信号

### Requirement: 行情和期权必须保留字段级时间与口径
Yahoo/Moomoo SG 行情 MUST 保留币种、时区、复权、公司行动和行情延迟；期权 MUST 区分静态合约与动态报价，保留实际可得 bid/ask、last、volume、OI、IV、Greeks 及各字段时点，禁止补造缺失值或历史快照。

#### Scenario: 不同来源的快照时点不同
- **WHEN** 两源期权快照超过允许时间差或字段观察日期不同
- **THEN** 系统分开呈现快照或拒绝组合，不拼接成同一时刻的期权面

#### Scenario: 部分动态字段缺失
- **WHEN** 有可靠报价但缺少 Greeks
- **THEN** 系统保留可用报价和缺口，仅允许字段足够的研究用途，不填零或宣称全字段可用

#### Scenario: 历史行情复权不一致
- **WHEN** 回退来源与原行情采用不同复权方式
- **THEN** 系统禁止静默拼接，核对一致口径后才生成可比序列

### Requirement: 供应商资金流必须保持供应商定义
Moomoo SG 资金流 MUST 标记 VENDOR_CALCULATED_FLOW，保留分类、单位、币种、期间、观察时间、定义及来源版本，不得等同真实机构资金、SEC 披露或可验证买卖方向。

#### Scenario: 返回大小单分类
- **WHEN** 供应商提供整体、特大、大、中、小单资金数值
- **THEN** 系统按原口径保存，专业解释必须明确其为供应商分类统计

#### Scenario: 缺单位或有效时间
- **WHEN** 资金流只有图形或无法核实期间、单位、时点
- **THEN** 系统记录 SOURCE_LIMITED 或 CONTRACT_MISMATCH，不猜测数值语义

### Requirement: 研报和二级机构资料必须分级
系统 MUST 将 Moomoo SG/Yahoo 机构展示与 SEC 原文分别标注，并保存显示来源、覆盖和时间。研报 MUST 区分候选、评级摘要、转载与实际可读正文；自动发现/获取的真实正文才可形成正文 Evidence，单份正文不证明完成多报告比较。

#### Scenario: 供应商引用 SEC
- **WHEN** Moomoo SG 显示来源为 SEC，但系统未取得对应原文
- **THEN** 资料保持 SECONDARY_VENDOR，记录 reported_original_source 而不升级来源层级

#### Scenario: 只有评级摘要
- **WHEN** Yahoo 或 Moomoo SG 提供标题、目标价或摘要，正文不可得
- **THEN** 系统仅生成候选及访问限制，不把评级、新闻或财报冒充研报正文

### Requirement: OpenD 与 Quote API 必须严格受限
系统 MUST 只允许连接 loopback 地址上的用户管理 OpenD，并使用版本化 allowlist 约束官方 Quote API 方法、参数、证券市场、返回契约、频率、分页与总时长。Runtime MUST NOT 构造 Trade Context、调用账户/订单/持仓/资金/交易解锁接口、连接远程 OpenD，或暴露通用 SDK 调用能力给 Agent。

#### Scenario: 调用批准的研究方法
- **WHEN** 请求只包含批准的美股证券、日期、分页和只读 Quote API 方法
- **THEN** 适配器在预算内调用本机 OpenD，并记录 OpenD、SDK 与方法版本及实际字段覆盖

#### Scenario: 请求交易或账户能力
- **WHEN** 调用请求包含 Trade Context、账户、订单、持仓、资金、交易解锁或非 allowlist 方法
- **THEN** 系统在连接或调用前拒绝，不将该能力提供给采集层或 Agent

#### Scenario: OpenD 或响应漂移
- **WHEN** OpenD/SDK 版本、方法可用性、证券身份或返回字段与批准契约不符
- **THEN** 受影响能力熔断并要求重新验证，不扫描未知方法或回退到客户端私有接口

### Requirement: OpenD 认证必须留在用户管理边界
Moomoo ID、密码、二次验证、API 问卷协议和行情登录 MUST 由用户在 OpenD 内完成。系统 MUST NOT 接收或自动提取 Moomoo App/OpenD 的 Cookie、Token、密码、Keychain、配置数据库或交易解锁信息；日志、Git、Evidence、模型上下文与普通缓存不得包含认证材料。

#### Scenario: OpenD 未登录行情服务
- **WHEN** OpenD 可连接但 Quote API 未登录或首次协议未完成
- **THEN** 系统返回 `QUOTE_NOT_LOGGED_IN` 或准确限制，不尝试代用户登录或读取其他客户端会话

#### Scenario: 用户停止 OpenD
- **WHEN** 用户退出或停止本机 OpenD
- **THEN** 后续 Moomoo 请求返回 `OPEND_UNREACHABLE`，既有脱敏 Evidence 仍可读取，SEC/Yahoo 继续独立工作

### Requirement: 采集必须有界并保护原始资料
每批采集 MUST 限制证券、页数、到期日、请求数、并发、频率、重试与总时长；记录来源计划、端点版本、原始 hash 与状态。响应 MUST 在进入缓存或 Evidence 前检查大小、身份、类型、分页与禁止私密字段。公开披露中的申报人身份与私人账户标识 MUST 区分。

#### Scenario: 返回私人账户字段
- **WHEN** 研究端点意外返回用户账号、设备秘密、账户资产或消息
- **THEN** 响应只留受限隔离区并生成脱敏失败，不生成可消费 Evidence

#### Scenario: 公开 SEC 申报人字段
- **WHEN** 合格原始申报包含公开机构或内部人姓名
- **THEN** 系统按研究契约保留公开身份及原文来源，不将其误当用户账号秘密删除

#### Scenario: 分页或预算异常
- **WHEN** 页码重复、覆盖不完整、429 或预算耗尽
- **THEN** 停止受影响请求并保留准确完整性状态，不无限重试或伪装完整集合

### Requirement: Evidence 必须满足来源与 point-in-time 闭合
事实 MUST 含 evidence_id、source_id、source_type、source_locator、security_id、as_of、retrieved_at、公开/可知时间、raw hash、批次与来源版本；Moomoo 来源版本 MUST 包含 OpenD、SDK 和 Quote API 方法标识。PIT MUST 同时约束事实时点及公开版本；获取时间不得替代事实时间。跨源冲突 MUST 保留而不静默覆盖。

#### Scenario: 13F 季末早于截止点但披露晚于截止点
- **WHEN** 持仓报告期早于 decision_cutoff，但对应申报在其后才公开
- **THEN** 系统排除其历史研究用途，不把季末持仓当当时已知事实

#### Scenario: 新快照晚于历史研究包
- **WHEN** 当前采集晚于原 canonical 包 cutoff
- **THEN** 系统形成新时点研究产物与显式缺口映射，不回填历史事实

### Requirement: Agent 只能消费冻结合格研究输入
系统 MUST 通过版本化只读 MCP 按证券、数据集、cutoff 和批次查询冻结结果；Agent MUST NOT 获得秘密、任意 HTTP、Bootstrap、原始隔离区或客户端控制权限。Tool 负责数据与数学，Skill 负责研究解释，采集层不得生成投资判断。

#### Scenario: 专业研究消费
- **WHEN** 合格快照通过 Evidence Gate
- **THEN** 既有专业 Skill 使用 canonical Evidence ID 形成结构化研究输出，并保留三源语义和限制

#### Scenario: 越权请求
- **WHEN** Agent 请求新网络调用、secret reference 或未冻结数据
- **THEN** 系统在访问网络和秘密前拒绝

### Requirement: 完成必须证明三源接入和原缺口增量
Change 完成 MUST 具备 SEC、Yahoo 真实接入，Moomoo SG 至少一个研究数据集真实 Capture → Normalize → PIT → MCP，以及至少一个原缺口核心增量（动态期权、供应商资金流或可比两期机构持仓）被现有专业 Skill 正确消费。其他目标 MUST 有逐项真实覆盖/限制说明、聚焦契约测试和独立复核；有限专项消费不启动 Skeptic、CIO、Risk、完整 Council 或晋升流程。用户已指定截图持仓系统验收时，Change 完成还 MUST 证明同一确认 Handoff 中所有可研究普通股均取得真实 Company Analyst 终态和有效报告，同时保留 ETF、期权等能力缺口。

#### Scenario: SEC 和 Yahoo 成功而 Moomoo SG 全部受限
- **WHEN** 两源形成合格 Evidence，但 Moomoo SG 没有研究数据通过完整链路
- **THEN** 可以报告两源阶段成果，整个 Change 仍未完成

#### Scenario: 三源只有基本行情与候选摘要
- **WHEN** 三源可调用但没有任何延期核心缺口形成实际研究增量
- **THEN** 不得申请完成或宣称原研究缺口已补齐

#### Scenario: 通过有限验收
- **WHEN** 三源接入、核心增量、专项消费、截图持仓普通股报告集、聚焦检查和独立复核均有证据且获人工完成批准
- **THEN** 可以准备收尾，保留已归档任务状态，仅新增明确的缺口证据映射

#### Scenario: 截图持仓只有子任务启动事件
- **WHEN** ALB、MRVL、WOLF 已获得允许派发并记录 `SubagentStart`，但至少一个任务尚无同一父会话下且身份绑定正确的 `SubagentStop` 或有效报告
- **THEN** Change 仍未完成；父线程停止边界必须要求继续等待，最终缺失时由既有 finalizer 非零失败，不得用父线程自报计数补齐

### Requirement: 普通股父调度线程必须等待可验证终态
普通股研究父线程 MUST NOT 将 `SubagentStart`、普通消息、单次 `wait` 返回、父线程自报计数或 Codex 进程退出码解释为任务完成。任何已派发任务尚未产生同一父会话下、task/invocation 身份绑定正确的终态时，系统 MUST 在父线程停止边界阻止结束并要求继续等待；只有全部预期任务均有可验证终态后才允许进入报告归集。该屏障 MUST NOT 生成、修补或替代研究报告；批次超时、取消、非法报告及缺失终态继续由既有预算和 fail-closed 终结器处理。

#### Scenario: 等待被非终态活动提前唤醒
- **WHEN** 父线程的等待调用因子任务启动、进度消息或其他非终态活动返回，且至少一个已派发任务尚无可验证终态
- **THEN** 父线程停止边界阻止结束、列出缺失 task_name 并要求继续等待

#### Scenario: 三个 Analyst 全部完成
- **WHEN** 三个预期任务均在同一父会话下产生身份绑定正确的 `SubagentStop`
- **THEN** 父线程停止屏障允许结束，finalizer 再独立校验报告 Schema、Evidence Closure、证券绑定和完整集合

#### Scenario: 批次预算内始终缺少终态
- **WHEN** 至少一个已派发子任务在批次超时前始终没有可验证终态
- **THEN** 系统保留诊断并非零结束，不绕过屏障或编造报告

### Requirement: 截图持仓必须实际接入三源补充资料
系统 MUST 将确认 Handoff 中 ALB、MRVL、WOLF 的逐证券三源补充资料接入既有数据准备、Gate 和冻结 MCP，形成逐证券背景、来源尝试、覆盖和缺口索引。每股基础背景 MUST 有可引用事实；增强类别允许真实受限。整体 MUST 至少有一只实际持仓的 Moomoo 研究数据和本 Change 核心增量完成真实消费，MUST NOT 用非持仓 AAPL 的样本结果替代。多证券挂接 MUST 保持证券隔离、相同研究 cutoff 和来源语义，禁止覆盖前一证券的补充记录。

#### Scenario: 持仓 Gate 只有原有 SEC/Yahoo 数据
- **WHEN** Gate 缺少三源补充包绑定或实际 Moomoo 研究 Evidence
- **THEN** 标记截图持仓三源接入未完成，即使原有公司报告成功也不判本需求验收通过

#### Scenario: 新补充资料晚于旧冻结截止点
- **WHEN** 缺失资料只能通过当前采集取得
- **THEN** 建立新 cutoff/run_id 和新冻结包，保持确认 Handoff 与原包不变，不回填历史 Gate

#### Scenario: 多股研究实际消费新增资料
- **WHEN** 三只普通股形成有效报告且真实工具返回和引用可追溯
- **THEN** 逐股核对背景资料与限制，并证明至少一只持仓消费新增背景类别和核心增量；ETF/期权保持明确能力缺口

### Requirement: 正式持仓入口必须完成补充资料全链路接入
既有宿主持仓入口 MUST 在用户提供确认 Handoff、既有来源配置和用户管理的 OpenD 后，组织有界采集、逐股补充包挂接、冻结、研究和中文/JSON 输出，MUST NOT 要求用户手工拼包。多包保存、索引、冻结来源包重建校验、逐股请求/MCP 查询和报告引用 MUST 一致闭合；旧单股冻结包读取 MUST 保持兼容。能力适用于确认 Handoff 中支持的普通股，不得硬编码验收三只股票。

#### Scenario: 从确认持仓进入正式研究
- **WHEN** 用户通过既有正式入口提交有效 Handoff 和来源配置
- **THEN** 系统自动完成三源补充数据接入及研究输出；临时脚本或手工 attach 的成功不能替代本项验收

#### Scenario: 多证券补充包重建与查询
- **WHEN** 同一冻结包包含多个证券的补充资料
- **THEN** 校验器重建全部补充内容，逐股查询与引用仅使用允许范围，缺包、错证券、错 cutoff 或重复覆盖均被拒绝

#### Scenario: Moomoo 受限而 SEC/Yahoo 合格
- **WHEN** Moomoo 不可达或研究数据无权限，但其他来源通过门禁
- **THEN** 继续提供合格研究和准确来源缺口；若全部实际持仓均无 Moomoo 研究消费，Change 验收仍未通过，不把部分可用误报为整体失败或三源完成

### Requirement: 修复与重跑必须针对已证实的消费阻塞
系统开发验收 MUST 区分来源接入、持仓输入装配、上下文交付、MCP 调用、模型执行、输出捕获与报告校验。Start、Hook DELIVERED、Stop BLOCK 或测试通过 MUST NOT 单独证明研究消费成功。追加模型重跑前 MUST 基于已有证据写明最早失败步骤、已证实事实、待验证假设、最小修复和预期解除信号；未确定根因时明确标记未知，禁止把重复等待当修复结果。

#### Scenario: 父屏障生效但子任务仍无输出
- **WHEN** Stop 多次 BLOCK 而没有真实查询或合法报告证据
- **THEN** 只认定提前退出保护生效，研究执行阻塞仍未解除；先核对上下文、MCP 和子任务错误再决定修复

#### Scenario: 历史证据不足以判断失败原因
- **WHEN** 已有日志不能区分上下文、MCP、模型执行或输出捕获故障
- **THEN** 明确最早未证实边界和待验证假设，优先确定性检查，必要时经既有宿主入口补最小诊断并按声明预算验证；不要求虚构根因、不无限重试、不扩建通用平台

#### Scenario: 旧专项复核未覆盖新增接线
- **WHEN** 历史 Reviewer PASS 只覆盖 AAPL 三源样本
- **THEN** 保留其限定适用范围，当前 Change 必须补充持仓接入与受影响运行接缝的独立复核

### Requirement: 个股背景必须形成可复用的证据资料包
系统 MUST 为研究证券形成与 cutoff/采集批次绑定的背景包及同源中文展示，覆盖公司档案、业务分部、管理层治理、客户供应商及竞争关系、财务历史、资本配置、业绩指引、分析师预期、事件和股本空头背景十组。每组 MUST 保留 Evidence、来源尝试、覆盖与缺口；事实 MUST 含 source_id、as_of、retrieved_at 及原文定位。基础身份、主营业务与最新适用核心财务 MUST 有真实证据，不能全部以未知占位；其他领域 MUST 区分未披露、未获取、来源受限和不适用。新获取只使用 SEC、Yahoo、Moomoo SG。

#### Scenario: 公司档案可得而分析师预期受限
- **WHEN** 已核实身份、主营业务与核心财务，但三源不能提供可靠预测版本
- **THEN** 背景包保留合格基础资料与预期缺口，不阻断其他事实，也不把当前预期冒充历史预期

#### Scenario: 没有可验证的核心公司背景
- **WHEN** 只取得股票名称、报价或无法引用的业务摘要
- **THEN** 系统不得标记背景包基础验收完成，并指出缺少的原始披露与财务期

### Requirement: 分部与公司关系必须来自明确披露
分部数据 MUST 保留产品/地区或其他维度、期间、单位、合并抵销与重分类依据。客户/供应商/竞争关系 MUST 保留关系类型、原始陈述、有效时点及披露范围；同行分类或价格相关性 MUST NOT 被当作供应链事实。未实名客户 MUST 保持匿名。

#### Scenario: Companyfacts 只有合计值
- **WHEN** 没有原始分部表格或 XBRL 维度上下文
- **THEN** 系统保留合计和分部缺口，不把合计复制成业务线收入

#### Scenario: 仅披露单一客户集中度
- **WHEN** 披露只说明匿名客户占收入一定比例
- **THEN** 系统保留比例、期间和匿名身份，不用模型记忆或行业关系猜客户名称

### Requirement: 治理与资本配置必须保留有效日期和证据范围
系统 MUST 从可得 SEC 年报、代理声明及公司事件披露提取重要管理层/董事角色、控制权、任免、激励、关联交易以及发行、分红、回购和重大投入，供应商摘要作为二级补充。系统 MUST 区分回购授权和实际执行、授予和已发行股本、公开日期与生效日期；治理质量解释由现有 Skill 完成。

#### Scenario: 只有回购授权公告
- **WHEN** 公司公布回购额度而未披露实际回购
- **THEN** 系统记录授权及期限，不计为已支出现金或已减少股数

#### Scenario: 当前高管档案用于历史研究
- **WHEN** 供应商只提供当前职务而无法证明历史任职区间
- **THEN** 该档案仅作当前观察，不能用于历史 cutoff 的管理层判断

### Requirement: 财务背景必须显示真实历史覆盖与可比性
系统 MUST 以最近 3 个完整财年和 8 个独立季度为默认有界目标，保留实际覆盖、单位、财政日历、主体、会计基础、taxonomy 和重述链；营运资本、研发、利息、资产负债权益及资本配置按可得披露扩展。重复申报数 MUST NOT 当期间数；派生季度、TTM、财务比率与估值算术 MUST 由确定性工具在可比输入上生成并保留父 Evidence。

#### Scenario: 累计现金流拆单季
- **WHEN** 两个累计期间同起点、同主体同口径且满足可比条件
- **THEN** 系统可经确定性差额得到单季并记录父事实；条件不足时保留累计值与单季缺口

#### Scenario: 企业历史不足或存在重组
- **WHEN** 发行人不足三年或跨期发生不可比重组/重述
- **THEN** 系统展示可用原始期间与限制，不补零、年化或把前后继主体直接拼接成趋势

### Requirement: 实际业绩与指引及一致预期必须独立建模
系统 MUST 区分实际业绩、管理层指引与供应商分析师预测，并保留目标财政期、指标定义、GAAP/non-GAAP、币种单位、预测发布时间/vintage、样本数和修订。预测差计算 MUST 使用结果公布前的同口径预测；年度 forward EPS MUST NOT 代替下一季度预期。评级/目标价 MUST 标记外部观点，不能变成本系统投资动作。

#### Scenario: 历史预测版本不明
- **WHEN** 当前接口展示历史 EPS estimate 但不能证明其公布前版本
- **THEN** 系统保留供应商展示与限制，不生成已验证的历史预期差或回填历史研究

#### Scenario: 预期为零或口径不同
- **WHEN** 预测基数为零、负值或实际与预测属于不同会计口径
- **THEN** 系统不生成误导百分比；仅在同口径时给绝对差，其他情况明确不可比，不用默认零填补缺失

### Requirement: 事件与空头增强资料不得超出三源证据
事件 MUST 区分发布、发生、预计及确认状态，并核对证券关联、转载与更新；电话会全文和新闻正文 MUST 以三源实际可读内容为准。空头背景 MUST 区分 short interest、short volume、流通盘、统计日与 days-to-cover，不得推算未知借券费率或生成规则挤空评分。

#### Scenario: 财报日仅为供应商估计
- **WHEN** Yahoo/Moomoo SG 展示预期日期而没有公司确认
- **THEN** 记录估计或时间窗口，不输出已确认事件

#### Scenario: 三源仅返回电话会标题或外部链接
- **WHEN** 没有可读全文或链接指向未纳入的第四来源
- **THEN** 仅保留候选定位与内容缺口，不自动扩源或宣称已读全文

### Requirement: 背景补齐必须增加真实研究信息
除原三源与延期核心增量验收外，完成 MUST 提供一只真实普通股的基础背景闭环、十组覆盖记录和至少一个新增背景类别的真实 Evidence，并在既定有限专项消费中正确引用。只有新增 Schema、提示词、候选字段或重包装旧数据 MUST NOT 判定背景补齐完成。

#### Scenario: 分部背景形成实质增量
- **WHEN** 原缺少的可核实分部事实进入 Gate/MCP 并被专业研究引用解释业务构成
- **THEN** 可标记该背景类别已验证，其他受限类别仍保留缺口，原期权/资金流/机构验收不被替代

### Requirement: 三源补充能力必须进入当前 Provider 拓扑
当前持仓研究的权威 provider 拓扑 MUST 引用并锁定 SEC + Yahoo + Moomoo Singapore 的来源计划和数据集能力矩阵，区分基础披露/行情层与研究补充层，并将实际 provider/dataset 状态传递到运行 coverage 和缺口。Moomoo Singapore MUST 显示为通过用户管理的 loopback OpenD 提供的 quote-only 补充层；该视图不得暴露认证材料、客户端 Cookie、账户、订单、持仓、资金或交易能力。历史 `live-us-equity/4.0.0` 未列出 Moomoo MUST 被解释为该 profile 已退役且内容冻结，而不是当前系统没有 Moomoo 补充能力。

#### Scenario: 当前拓扑被查询
- **WHEN** 使用者或运行准备器读取当前 provider 视图
- **THEN** 能解析 SEC、Yahoo、Moomoo SG 的职责层、数据集状态、区域、限制及权威来源文件引用，同时看到 Moomoo 的 OpenD quote-only 边界

#### Scenario: Moomoo 暂时不可达
- **WHEN** 当前 OpenD 不可达但 SEC/Yahoo 的合格输入可用
- **THEN** 当前拓扑和运行 coverage 保留 Moomoo 准确失败状态，其他来源继续工作，不回退到客户端 Cookie 或私有接口

#### Scenario: 查阅退役 live profile
- **WHEN** 工具或维护者直接发现 `live-us-equity/4.0.0`
- **THEN** profile discovery 明确返回 RETIRED/COMPATIBILITY_ONLY，并引导到当前研究输入拓扑，不要求修改历史 profile 的 provider 列表

### Requirement: 新来源必须与既有三源补充包保持明确边界
三域新增的政策、新闻、IR 或公开研究来源 SHALL 通过获准的独立来源包进入共同 Evidence Gate，并保留真实 provider 和来源政策。既有 SEC/Yahoo/Moomoo SG 补充包 MUST 保持三源身份与原有安全边界，不能把外部正文伪装为三源资料，也不能因候选 Skill 适配而扩大 OpenD 权限。

#### Scenario: 公司 IR 正文补充 SEC 披露
- **WHEN** 公开 IR 文档被获准采集且通过时间和来源验证
- **THEN** 它以自身来源进入 Gate，与 SEC 披露保留关系和差异，不重标为 SEC 或 Moomoo Evidence

### Requirement: 高价值接口必须有明确取舍与来源复用依据
本 Change MUST 为营收分部、管理层、财报日历、新闻线索、市场涨跌分布、期权标的总览与历史统计/波动率完成有界候选评估，并核对财务、估值、公司行动和行业关系的既有来源覆盖。每项 MUST 记录研究问题、实际资料缺口、来源证据以及接入、已有来源足够、权限受限或暂缓的结论。系统 MUST 优先复用已获取资料和既有采集能力，不以全部接口接入或调用成功数量作为验收标准。可复用现有链路且确有增量的候选 SHALL 接入；需要新增服务或超出当前研究职责的候选 SHALL 保留后续建议。

#### Scenario: 已有来源能回答同一问题
- **WHEN** SEC、Yahoo 或官方宏观已取得合格字段而补充接口只重复相同内容
- **THEN** 记录已有来源足够并验证其正式消费，不新增重复请求，也不将未调用接口列为系统缺陷

#### Scenario: 候选方法存在但账号不可用
- **WHEN** 文档与 SDK 有该方法而有界验证返回权限不足或缺少关键字段
- **THEN** 保留真实限制与替代来源；评估任务可以完成，但不能把该接口记为已接入

### Requirement: 补充采集必须受共享预算与复用约束
系统 MUST 同时限制方法级、证券级和全批请求/时长预算，重试与分页计入预算；同批共享 Macro/Market 资料 MUST 只按批准参数采集一次并复用。增强项不能挤占核心采集预算。Yahoo 动态期权 MUST 优先复用既有能力接入正式采集，不能仅以配置声明证明可用。

#### Scenario: 多只持仓需要同一宏观资料
- **WHEN** 同批多个任务需要相同指标或市场统计
- **THEN** 它们引用同一冻结资料，共享请求次数不随持仓数重复增加

#### Scenario: 增强项预算不足
- **WHEN** 核心采集后剩余预算不足以获取额外历史或合约波动率
- **THEN** 增强项记录预算排除与影响，不无限重试或扩大请求

### Requirement: Moomoo 能力必须按文档、运行版本和纵向闭环分别晋级
系统 MUST 为每项 Moomoo Quote 能力分别记录官方文档版本、实际 SDK 版本、OpenD server version、方法签名、实际响应字段、权限与最后验证时间。官方 v10.11 文档列出接口或字段只证明 `DOCUMENTED`；只有当前锁定 SDK/OpenD 的真实只读响应成功后才可标记 `SPIKED`，完成版本化 allowlist、Normalize、PIT、正式 Collector、Gate/MCP 和专业 Skill 消费后才可标记 `RESEARCH_VALIDATED`。系统 MUST NOT 因网页标题、方法存在、fixture 或直接 SDK Spike 而跳过中间状态。

#### Scenario: 文档字段未出现在当前 SDK 响应
- **WHEN** v10.11 文档声明 Morningstar 的 `fundamentals_content`、`valuation_content` 或 `pdf_url`，但当前锁定运行版本没有返回该字段
- **THEN** 能力矩阵保留文档字段与实际字段差异，Normalize 输出具体 gap，不将字段加入可用覆盖或宣称 v10.11 runtime 已完成

#### Scenario: 直接 SDK Spike 成功但正式 Collector 未接线
- **WHEN** `get_market_snapshot` 对期权合约返回动态字段，但版本化 adapter、Collector 或 Skill 尚未消费
- **THEN** 能力最多标记为 `SPIKED` 或等价状态，不标记为正式接入或研究验证通过

#### Scenario: 运行版本升级
- **WHEN** 安装的 Moomoo SDK 或 OpenD server version 与批准 manifest 不同
- **THEN** 受影响能力 fail closed，并在方法签名、响应字段、PIT 和聚焦测试重新验证后生成新的 manifest/version/hash，不以版本范围静默放行

### Requirement: 动态期权补充必须形成有界同源快照
系统 MUST 使用批准的只读 Quote 方法取得标的当前快照、到期日、静态合约和选定合约动态行情，并由确定性策略限制到期日、行权价与合约总数。动态快照 MUST 保留实际可得的 bid、ask、last、volume、OI、IV、Greeks、合约属性、币种、交易时段及字段时间语义；静态链、筛选结果或缺失字段 MUST NOT 冒充动态期权面。来源选择声明 Yahoo 主源、Moomoo 回退时，两源都 MUST 有真实采集路线或准确标记为未实现。

#### Scenario: Moomoo 动态期权回退成功
- **WHEN** Yahoo `options_snapshot` 失败，Moomoo 静态链与所选合约动态 snapshot 在预算内成功且通过 PIT/Gate
- **THEN** 系统记录 Yahoo 失败、Moomoo 回退、确定性选择策略和实际字段覆盖，并把同源 Moomoo 快照交给 `OPTIONS_FLOW`

#### Scenario: 只有静态链成功
- **WHEN** 到期日和合约属性可得，但动态 snapshot 权限不足、字段缺失或超时
- **THEN** 数据集保持 `PARTIAL/STATIC_CHAIN_ONLY`，明确缺失 bid/ask/volume/OI/IV/Greeks，不生成完整 options snapshot

#### Scenario: 全链规模超过预算
- **WHEN** 标的返回的静态合约数量超过批准上限
- **THEN** 确定性层按版本化策略选取有限到期日和现价附近合约，保存总覆盖与排除数量，禁止把全链传给 Agent 或循环扩大请求

### Requirement: 高价值 Market、Macro 和研究补充接口必须保持来源语义
系统 MUST 对 Moomoo 的资本分布、全市场期权统计、期权波动率、Macro Indicator History、FedWatch、Dot Plot、Economic Calendar、评级汇总和 Morningstar 分别定义数据集、来源类型、参数预算、分页上限和允许用途。Moomoo 宏观实际值、前值、供应商共识、FedWatch 概率、FOMC Dot Plot、评级和 Morningstar 观点 MUST 保持不同语义，不得互换或覆盖 BLS、Treasury、Federal Reserve、SEC 或 Yahoo 的职责。

#### Scenario: Moomoo 宏观值与 BLS 官方值同时可得
- **WHEN** 同一通胀或就业指标同时存在合格 BLS Evidence 和 Moomoo Macro History
- **THEN** BLS 保持官方主源，Moomoo 作为带覆盖与版本限制的二级补充，冲突并列保留而不选择静默 winner

#### Scenario: FedWatch 概率可得
- **WHEN** Moomoo 返回未来会议目标利率概率
- **THEN** 系统将其标记为市场隐含/供应商市场预期，只允许 Market Context 使用，不描述为 Federal Reserve 的政策承诺或官方预测

#### Scenario: 评级分页仍有后续页
- **WHEN** 机构或分析师评级响应返回非终止 `next_key`
- **THEN** 系统在批准页数内停止，保留未覆盖分页和外部观点限制，不把当前页面描述为全部机构或分析师覆盖

### Requirement: 新能力必须保持 OpenD Quote-only 和内容许可边界
扩展 Moomoo 能力 MUST 继续通过 loopback `OpenQuoteContext` 和逐方法 allowlist；不得开放通用 SDK 调用、Trade Context、账户、用户持仓、订单、资金、交易解锁、远程 OpenD 或客户端私有会话。Morningstar、评级 URL 和供应商分析文本 MUST 标记许可与内容层级；系统不得因取得下载地址而自动下载、再分发或把供应商判断转为确定性事实。

#### Scenario: 新接口返回账户或认证材料
- **WHEN** Quote 响应或错误意外包含账号、Token、Cookie、设备秘密或交易字段
- **THEN** 内容扫描拒绝其进入缓存、Evidence 和模型上下文，并以脱敏错误隔离该能力

#### Scenario: Morningstar 正文可读
- **WHEN** 用户有权通过 OpenD 读取 Morningstar section 正文
- **THEN** 系统仅按内部研究的授权内容层级保存必要正文、section 时间和来源限制，不声明再分发许可，也不自动抓取 `pdf_url`
