## Context

动机及已知错误见 [proposal.md](proposal.md)。当前 ALB 问题不能归结为未交付要求：Company 和 Fundamental 已查询正文却形成假缺口/错引，Technical 已有逐主张计算选择机制却遗漏局部对应，原 CIO Prompt 已要求核对来源、窗口和反证。现行 CIO v2 只给 key_facts 直接 Evidence 支持，macro_market_transmission 缺逐项支持，挑战检查只要求至少一条处置。新的输出接缝能让取舍可见，但不能机械证明自然语言正确。

设计沿既有研究与交接路径，不引入外部依赖。实施点为 common_stock_stage、multidimensional_stage、independent_skeptic_stage 的现有主线程调度/宿主/Hook/状态读取，calculation_handoff/research_submission 的选择与验证接缝，以及 predecision_cio_stage、cio_handoff、cio_local_revision、fixture_mcp 的既有交付/装配/收尾路径。技术约束见本 Change 四项 delta Specs；列表输入/刷新/批次归集由 enable-bounded-stock-list-research-refresh 接线，本 Change 不建立列表调度后端。主规格中 2026-10-03 限定版条款继续表示旧交付，不适用于本次修复完成标准。

原 started_at 到 finalizer generated_at 为 5166.903 秒，不是已证明的通信耗时。现有 _run_cio_process 在 Popen 返回后将 timeout_seconds 传入 communicate；旧事件缺准备/创建/清理/校验分段，不能据此确定历史超额原因。

## Goals / Non-Goals

**Goals:**

- 让同来源章节的标题、正文及截断限制以同一定位语义实际到达显式新版普通股作者（单股及已确认持仓），将交稿核对落实到真实提交接缝，不靠 ALB 专属分支。
- 将作者来源取舍、全部正式目标挑战和关键事实/传导的精确支持持久化、验证并同源渲染。
- 在不改变投资语义的前提下，由可信层装配技术身份，复用原计算与查询证明。
- 为 Company、多维、独立 Skeptic、CIO 及父依赖等待保存固定 deadline、可信进度/最后有效事件和分段时间，终态后不空等。
- 准确区分交付字节、重复读取、父子 usage 与费用证据，在不减少研究内容/反证的前提下削减机械重复并有界停止消耗。
- ALB 必须新上游/CIO 实质通过；用不同证券/资料结构验证通用接缝，把确定性实现、另获批准的真实执行、独立内容裁定、人工完成和发布分开。

**Non-Goals:**

- 不用关键词、主张数量、文本长度或投资评分代替内容裁定；不建立模型评委。
- 不新增 Agent、CIO 子 Agent、提交工具、计算权限、网络接口、通用协议框架或第二套编排器。
- 不改历史报告/Schema 字节/运行锁/FAIL，不扩展为当前行情、历史 Replay、账户适配或交易决策。
- 不增加 timeout，不改代理、认证、沙箱、权限、Hook 修订次数或环境阻断上限。
- 当前只创建规划；本文所述所有产品能力均待显式 apply 实施和验证，不能视为现已可用。

## Decisions

以下为待 apply 的新版设计，不是已实现能力。旧计划中仅新单股的交付/计时范围现扩为单股及已确认持仓的新版普通股研究；旧包和原执行授权不迁移。新增自选股输入及列表刷新仍仅在配套 Change 中实现。

### 1. 定位是提取结构，不是 Evidence 选择器

将 multidimensional_stage._text_locator 的小型结构提取抽成同仓 helper，新版普通股 Company 的 _build_evidence_period_index 与多维列式目录调用同一新版逻辑。以显式 `research-evidence-delivery/1.0.0` 标记绑定新准备 manifest、任务、packet 和实际交付；无标记分支保留旧投影，不能通过当前源码改变历史交付含义。

新版定位保留 source_id、申报/章节元数据、section_locator、content_kind、text_length、truncated（缺失为未知），以及可定位的期间和原引用。同一来源/章节的标题与正文同时保留，不输出投资摘要或替作者推荐某条 Evidence。query 仍返回原事实和 source_id/as_of/retrieved_at，目录工具仍只提供元数据。

HEADING_ONLY 只在整个文本符合章节标题结构时成立：规范化空白及标题中的引号变体，按少量明确 SEC 章节名称/别名识别可选 Item 编号和尾部页码。测试包括真实 Risk Factors 和 “Management ’ s Discussion and Analysis of Financial Condition and Results of Operations” 标题，以及含同样首句但后接实质内容的负例。长度不能决定类型。已知章节非标题文本按明确截断状态区分 SECTION_EXCERPT/SECTION_TEXT；缺少关键结构或覆盖信息则 UNKNOWN。SECTION_TEXT 只描述当前抽取对象，不证明全文完整。

不复用 issuer document 构造中的长度过滤/最长去重作为这一定位策略；它们处理文档对象，不应决定研究作者看到哪条 Gate Evidence。

**替代方案：** 只加 Prompt 无法解决定位/处置接缝；按最长文本自动替换引用会代替作者判断；统一重写旧目录会污染历史兼容。选择小型新版 helper 和显式分支。

### 2. 研究方法替换相关旧段落，不添加自动语义循环

更新 company-research、technical-structure 的阶段适用段落与 Fundamental 实际 minimum_questions/任务 instruction，并核对生成 packet、Hook 可见指引和版本镜像。方法顺序为：定位相关来源 → query 实读 → 对核心主张/缺口逐条核对 → 选择精确 Evidence/计算 → 交稿。Company 核对已读正文与缺口；Fundamental 核对主张与假设的实质正文支持；Technical 核对每项实际采用指标/窗口和本条 calculation_selections，连同摘要、失效与观察条件。

仍由原作者选择依据、解释限制和决定是否形成判断。复用 assemble_calculation_selections、research_submission 和原 Hook 局部纠正；不扩大可改字段或次数，不根据正文猜缺少的选择。实际对象存在/身份/查询/计算关系属于程序验证，选择是否支持措辞属于内容复核。ALB 的 claim 名称、Evidence 和数值只进入开发验收对照，不写入产品分支或模型预设。

**替代方案：** Python 扫描数字自动补引不能证明语义，也违反职责分离；只让 CIO 避开旧错误不满足新上游修复标准。

### 3. 新写入用显式 v3，历史契约保持原字节

新增 `predecision-cio-synthesis-v3.schema.json`（`predecision-cio-synthesis/3.0.0`），配套新的研究请求契约 `predecision-cio-request/3.0.0` 和新版语义草稿 `native-cio-draft/2.0.0`。请求 v3 只允许已授权来源绑定为 SINGLE_STOCK_RESEARCH 或真实 PORTFOLIO_HANDOFF，输出模式固定 RESEARCH_SYNTHESIS；沿原阶段目标允许集校验，不借版本变更扩大持仓证券准入。新单股 prepare 默认选择新版；已确认持仓的新准备须显式启用新版资源锁。账户适配仍未评估、Risk=NOT_RUN，PORTFOLIO_ADVICE 和动作模型前拒绝；保留原身份/PIT/禁止动作字段约束。将请求/输出/草稿版本和资源 hash 写入可信 manifest/invocation 及冻结契约。未知版本、错配或缺依赖拒绝，不按草稿字段推断版本。无账户列表属于后续独立 Change，采用其显式请求版本，不能将列表伪装成 v3 单股或持仓。

沿 _output_schema、_native_output_schema、_assemble_native_output、assemble_cio_draft、Stop/finalizer/checker 和 artifact reader 增加明确版本路由。共用 native_cio_schema 的默认旧格式保持，新增格式只由已绑定新版调用选择。更新 cio_local_revision 的合法协议路由，不改变最多一次局部纠正；若新字段超出原允许修订边界则正常失败，不借新 Schema 自动扩权。

旧 request/synthesis v1/v2、native draft v1、MRVL、持仓和 fixture 的读取/已有执行边界保持，不改旧 Schema 文件或给旧包补标记。新格式不匹配时不能自动回退 v2。资源锁和版本镜像只更新批准的新研究版本，不移动生产晋升指针。

**替代方案：** 在 v2 原地增必填字段会破坏旧运行锁；按字段存在自动升级难以审计且可能绕门禁。选择新版本。

### 4. 来源处置按原对象定位，不新增投资重要性筛选

v3 的 `source_dispositions` 为小型列表，每个已交付非 Skeptic 报告恰有一项：

- `report_id`：当前报告短引用选择，正式值由原 reference map 还原。
- `disposition`：ADOPT / LIMIT / REJECT / NOT_USED。
- `reviewed_claim_ids`、`reviewed_gap_ids`：实际复核的原对象 ID 列表；无稳定 gap_id 时为空，不生成原报告中不存在的 ID。
- `rationale`、`judgment_impact`：作者对采用、纠正、限制或不采用的理由和判断影响；无稳定 ID 的缺口可在理由中指明原文本对象。

列表不强制引用报告所有 claim，不机械设数量门槛；但已知 ALB 错误的实质处置由本次内容验收逐项检查。一个报告总处置可在理由中区分内部不同主张，不能把 LIMIT 一词当已说明取舍。

Skeptic 沿原 `challenge_dispositions`，v3 覆盖目录内目标证券全部正式 `(report_id, challenge_id)`，不是 Python 选择“重要”挑战；无挑战时允许空列表。checker 只核对来源存在、类型、唯一性、覆盖、实际 read 和同源绑定，不评判 rationale 的投资合理性。缺口不强制转化为反证挑战。

**替代方案：** 自由 limitations 难以定位取舍；建立通用论证图超过当前目标；规则选挑战会固化主观判断。选择报告级小型处置和原正式对象。

### 5. 计算支持沿原完整报告精确选择并装配

不增加工具或模型侧第二个大目录。read_cio_reports 继续交付获准完整报告，保留既有重复 input_evidence_refs 无损共享。作者在 v3 每条 key_fact/传导中提交 `calculation_selections`，每项仅选择 `(report_id, source_claim_id, calculation_id)`；其余研究文字、直接 `evidence_refs` 仍由作者提交。报告短引用沿原映射还原，本地 claim_id 不占用短引用保留命名空间。

可信层从实际已读报告重验三元组，原 source_claim_id 必须引用所选 calculation_id；不能选择仅在附件存在但原主张没有采用的数值。v3 正式条目将选择装配为 `calculation_support`，只复制并绑定原记录，不由模型抄写数值/hash：

- 原报告 ID、schema_version、content/file hash、原主张 ID 和 invocation；
- calculation_id、method、value、unit、input_evidence_refs；
- artifact_ref、原产物/收据 hash、可用 tool_event_hash；
- 从原产物取得的 as_of、窗口、价格口径、目标/基准身份，保留该计算真实存在的语境，不为无窗口的金额换算编造窗口。

复用 research_submission.selected_calculations_for_report、calculation_handoff 和原动态收据/technical/market 预计算验证器。动态计算用原成功 receipt/tool event，预计算用原 artifact/schema/结果身份；不把只覆盖动态 ledger 的 _dependency_calculation_records 当作完整结果目录。选中的原计算产物及其校验所需账本/事件必须在 prepare 冻结输入闭包中，由 reader/checker 重验；不能运行时访问未冻结任意路径。

直接事实引用仍用 collect_evidence_refs 和本 invocation _mcp_query_ids 验证。`input_evidence_refs` 是原计算血缘，单独按 Gate/PIT/产物验证，不能混入当前 query 集合或替代直接事实查询；不修改全局 collector 来放宽其他路径。原输入事实的 source_id/as_of/retrieved_at 从冻结 Gate 保真核对，若不能闭合则拒绝，不由作者或程序猜补。中文展示采用计算及语境，同时清楚区分它与直接 Evidence。

每条 key_fact 至少有直接 Evidence 或合法计算支持。传导增加 `support_status`：SUPPORTED 时至少一类非空支持，UNVERIFIED_UNKNOWN 时允许无可得支持但必须有具体 limitations，不准声称已验证方向。该状态由作者声明，非自动内容认证。已有事实/计算可得却未经分析仍由内容验收判缺口。

**替代方案：** 只留报告 ID 不能定位本条指标；要求 CIO 自己算或抄技术元数据会扩大工具面并制造漂移；把所有计算输入当直接 query 既失真又浪费上下文。选择原三元组和可信装配。

### 6. 同源消费者与接缝校验同步更新

新 JSON、中文 Markdown、历史读取和当前使用的报告消费者均按版本展示来源处置、挑战影响、事实/计算支持及限制；不重新生成研究文字。fixture_mcp 只适配原 read/query 的新版交付，无新工具。实际 tools/list 与 CLI 白名单交集仍为 query/read_reports。

验证必须覆盖 prepare → 生成 launcher 命令和实际 stdin/Schema → 原本地 MCP transport read/query → 作者合成草稿 → 原 Stop/装配 → finalizer/checker → 中文渲染，而非只断言 Prompt 字符串。零模型模拟执行仅证明这些接缝，不计作真实 ALB 研究或真实资源加载。

**替代方案：** 仅更新 Schema 会造成 producer/consumer 漂移；只改 Markdown 会把引用校验留在旧接口。选择完整现有接缝的纵向切片。

### 7. 四阶段固定 deadline 与分段计时不承诺操作系统级端到端抢占

沿 Company 的 _run_company_process、多维/反证原 subprocess 调用和 CIO 的 _run_cio_process 接入同一小型确定性预算/计时 helper；仍由原 launcher 执行原模型进程，不新增 supervisor、服务、线程调度后端或第二套编排器。各宿主保存 UTC + monotonic 的准备、进程创建、通信、清理、校验/渲染边界。`research-execution-budget/1.0.0` 冻结 stage/run/任务集合、实际 timeout、父等待范围、清理 grace 及派发额度；`research-execution-observation/1.0.0` 绑定实际事件、时间和最终状态。替换原单 CIO 拟议 timing 名称，CIO 也使用同一研究观察契约。计时来自宿主而非模型草稿，总时间不倒填 generated_at 或形成循环 hash。

预算范围明确为创建加通信；父依赖等待在同一阶段固定期限内。deadline 在 Popen 前计算一次，返回后 communicate 使用 deadline - monotonic_now；剩余非正时归集超时并清理。持续输出、重试、Hook、等待返回或状态读取均不刷新期限。阶段总 timeout 沿原批准值，不自动加长；下一阶段须独立获批且受调用计划总上限约束，不能把跨阶段串行时间伪称某一次通信。实际运行前冻结每阶段值和总预算，当前规划不授权任何数值额度。

同步 Popen 无法可靠抢占：如其自身长时间阻塞，返回后立即识别超额并记录创建时间，不能声称创建中强制准时取消。其他同步 I/O 也保留同样保证边界；不靠静态配置或源码 hash 宣称 OS 强制准时退出。可控制的等待调用、文件锁和状态读取使用有限等待/大小边界，剩余耗尽不再等。

四阶段清理复用已具备的专属本组边界；Company/多维/反证不足的分支补齐已有 CIO 的 TERM/KILL/drain/原字节和权限错误原则，而非将其现状误报为全具备。清理使用独立有界 grace，不延长研究预算；超时124、中断130、非法编码、清理期中断、本组/无关进程和 remote UNKNOWN 逐阶段测试。UTC 与 monotonic 差额显示可见异常；不据平台时钟行为推断远程等待或暂停长度。离线准备到启动间隔与通信分开，历史不补时间。原 ALB 超额根因保持 UNCONFIRMED，未复现的 Hook 防重入疑点不改次数边界。

**替代方案：** 延长 timeout、无限长 wait、keep-awake 或修代理不能解决终态空等；新监控平台超过目标。选择原四宿主内的小型可信计时/预算接缝和明确保证边界。

### 8. 新报告按真实依赖重做，调用预算留在真实运行批准边界

确定性实现后先以实际版本锁/输入/hash 得出每份报告及缓存的失效/复用表。错误 Company/Fundamental/Technical 必须新研究；依赖新 Company/Fundamental 正文/hash 的行业/研报及包消费者按原准入检查，失效者重做，原独立 Skeptic 是否仍可复用须依据其输入/版本/允许集与隔离证明，不能凭“反证不看正向”直接假定可复用。资料、冻结计算和未受影响报告仅在原验证仍有效时复用，沿已有准备/恢复/导入路径绑定新包，不手工混拼。

此表生成后才能列准确父/子调用数和总预算，当前不猜固定次数、不预授权真实运行。真实步骤读取运行手册对应章节，以原 cutoff 为修复样本；新增资料/cutoff 另获授权。只能通过宿主 Terminal 的 run-product-smoke.sh，第一次关键失败按批准停止条件保留产物，不能自动追加尝试。独立裁定由用户或其本次明确授权复核者完成，不联系暂停 Reviewer 或其他会话。

**替代方案：** 全链无条件重跑浪费成本；只跑 CIO 无法证明上游纠正；手拼包会破坏身份闭合。选择实际最小失效闭包加独立运行批准。

### 9. 可信状态投影只补本组生命周期，不另造任务数据库

复用 read_multidimensional_task_state、read_skeptic_task_state 及原 research_task_state MCP。Company 增加相同边界的状态投影；各阶段统一暴露 `research-progress/1.0.0` 的小型旁证视图，CIO 从自身宿主事件读取而不是新增 Agent。输入为已冻结任务/依赖、派发/Hook/提交/校验事件和本组进程结果；输出为 run/stage/task/invocation/父子绑定、状态、最后有效 event_id/hash/time、等待依赖、elapsed/remaining、报告结果及 content_acceptance。旧原状态 enum 可保留，统一观察映射分开表示 PENDING/RUNNING/TERMINAL 与 SAVED/FAILED/TIMED_OUT/INTERRUPTED/BLOCKED/NOT_STARTED；REPAIR_REQUESTED/StopBlocked 不成为终态。

状态来自原事件与产物重验，不从文件存在、模型文本、普通 stdout、目录访问或 self-report 推断。查询本身不算任务进展；有效进展为本组新增合法派发/启动、已验证工具取证/提交及最终 Stop/校验。长模型思考期间可能没有事件，因此缺进展先标注诊断，不宣称模型死锁或内容失败。冻结 `no_progress_diagnostic_seconds = min(600, stage_timeout_seconds)`；达到阈值产生一次带最后事件和对象的诊断，此后仅在状态变化或固定 deadline 到期更新，禁止诊断刷屏延长期限。用户可在另获批准的运行计划中选择更严格诊断间隔，但不得扩执行预算。

主线程派发前、每次 wait 返回后、最终返回前读取可信状态。等待切片上限取 min(原600000ms长等待上限, 剩余阶段预算, 距下一诊断边界)，全部终态立即归集；关键依赖失败立即标记阻断，不等其成功稿。对仍有效运行的子任务不反复 follow-up/list；状态绑定不可信则明确失败/停止相关派发，不让 LLM 猜。状态读取的锁等待由剩余预算约束，避免在可信性路径本身无限阻塞。原 Hook 次数/防重入/字段修订边界不增加。状态工具不返回正文，也不把正向主张交给独立首轮 Skeptic。

**替代方案：** 心跳视作研究进展会掩盖空转；仅靠协作通知会遗漏真实终态；新增持久化 scheduler 会制造第二事实源。选择原事件投影、小型观察契约与现有主线程状态核对。

### 10. usage 逐 invocation 留证，明确统计范围后才聚合

用 `research-usage-observation/1.0.0` 保存原公开运行事件的确定性投影：run/stage/task/invocation、模型、可确认父子/session、event_id/hash、增量或累计口径、scope（SELF/INCLUDES_CHILDREN/UNKNOWN）、input/output/cached/total 的可用字段与 UNKNOWN 原因。仅从本次授权运行包读事件，不扫描用户私人 session DB；事件源的 source_id/as_of/retrieved_at 和实际获取血缘保留。字段名按实际事件格式显式解析，未知格式保留错误/缺失，不猜金额或以 token 总和补不存在的口径。

同 invocation 的累计事件只取可确认最终快照，增量事件按稳定事件键去重相加；累计/增量混用或重放日志必须能识别来源，否则不计为可信总数。父/子必须经实际派发/Hook/session绑定证明，不能按文件夹推断。只有非重叠 scope 的 invocation 集才可合计；可能含子级或未知的父级与子级分列，聚合标 PARTIAL/UNKNOWN 并给缺失覆盖。cached_input 若为 input 子集，不再次相加；没有版本化实际计费口径/价格时只报 token，不估计实测费用。

同旁证记录 prompt、原始/模型响应、native/正式输出的 bytes，按原 read/query 事件统计调用次数、report_ids、完整响应 hash 和重复读取；bytes 与 usage 是两个维度。模型前失败记 NOT_STARTED + usage NOT_APPLICABLE，不把未知失败消耗写0；复用命中记原报告/当前验证而非新模型调用。实际 token 只有结束事件可见时无法提供在途硬费用上限，进度明确这一点。每次新派发前与 usage 更新后核对批准调用额度/固定阶段时间/可观测 usage；越界不启动下一模型，未知 usage 仍受调用/时间硬约束，不能据 UNKNOWN 继续无限运行。

**替代方案：** 父子次数当计费请求、字节当 token、累计事件全部相加均会造假收益。选择原事件证据+范围标注，不新接收费仪表服务。

### 11. 无损减重与跨证券验证同时守住质量底线

继续使用 cio_handoff 的短引用/完整报告投影无损共享和 Skeptic 的分页定位，不新增与报告并行的全文大目录。研究作者先定点定位/读取所需对象；仅机械身份/重复血缘可由可信层装配/共享。新增 v3 字段与 usage 旁证也计入输入/输出净成本；旁证不塞进研究 Prompt。对无变化的完整大包重复读显示相同 hash/次数及是否已有新查询/主张/阶段事件，不替作者禁止有需要的合法重读，不把解释用途的自然语言判成机械正确。展开完整语义全等且净小才启用压缩，否则沿旧完整表示。

确定性矩阵涵盖 ALB 结构、至少一种非 ALB 结构（标题变体、短实质文本、正文缺失/截断、不同窗口/单位）、单股/持仓输入，以及 Company/多维/Skeptic/CIO 成功、局部失败、终态未通知、空 wait、持续输出、状态锁超时、总预算耗尽。这些只是零模型产品接缝，不签推理质量。另获批准的真实验证必须包括 ALB 新上游/CIO 内容裁定和至少一个非 ALB 新版本样本的实际执行/内容核对；不默认重跑 MRVL或任何证券，也不使用旧稿回签。token 优化结果以同等信息的受控字节/usage 口径和真实执行覆盖分别呈现；没有可比 usage 就报告未测。

**替代方案：** 只 ALB 通过、砍 Agent、削正文、改便宜模型或追加同义 Prompt 均不证明稳定且可能降质。选择通用接缝、最小失效闭包及质量/执行/消耗分列验收。

## Risks / Trade-offs

- [新方法/结构不能保证模型正确消费] → 新上游和 CIO 逐项独立内容核对，未通过不勾内容任务，不再次整体豁免。
- [标题识别有变体/歧义] → 精确结构正反例、UNKNOWN、保留全部原条目，不能以分类替代实读。
- [计算绑定扩展可能漏冻结依赖或重复血缘] → 沿原成功验证器、prepare 冻结闭包和无损共享，验证跨 run/hash/窗口/类型负例与输出字节，不塞第二份全文目录。
- [版本路由遗漏 Stop/reader/fixture 等共享消费者] → 验证全接缝和旧分支，旧 Schema 字节/历史 hash 不变，不将读取兼容等同当前执行许可。
- [合法引用仍可能不支持研究措辞] → checker 只记机械结果，内容对照单独裁定；不能编码 ALB 主观结论或补引。
- [同步创建、系统暂停、I/O 不能强制端到端时限] → 明示预算阶段和不可抢占边界，分段/差额不足则保留未确认；不宣称旧 86 分钟问题已定因。
- [usage 源缺失或父子范围未知] → PARTIAL/UNKNOWN 与覆盖列表，不重复求和、不估伪费用；token 后置可见时不承诺在途硬限额。
- [无进展不等于模型挂死] → 诊断与执行终态分开，固定 deadline 到期才按执行超时处理；终态已知时立即结束等待。
- [跨证券/列表与当前内容切片被混为一项完成] → 本 Change 跨证券证据单列，列表输入/刷新由配套 Change 验收；两个 Change 不互相自动 apply 或共享旧运行额度。
- [当前工作区含其他 Change/用户修改] → 实施只改本范围 hunk，记录基线；共享文件不能安全分离时停止相关发布，不回滚无关修改。
- [真实运行或独立复核授权尚缺] → 完成授权内确定性部分，真实/内容/最终任务保持未勾选，清楚报告阻断。

## Migration Plan

1. 完成本 Change 规划与 strict；规划完成不是 apply。所有 Tasks 从未完成开始。
2. 获本 Change 显式 apply 后，依次实施定位/研究方法、CIO v3、四宿主预算/状态/清理、usage 与无损上下文接缝；每切片聚焦验证通过才勾选。读取开发流程；不默认启动真实产品、网络或专项 Eval/Replay。
3. 新单股 prepare 选择新版，新持仓研究按明确版本标记启用；旧 manifest/Schema/运行目录不迁移。确定性检查旧 MRVL/v1/v2/持仓/fixture 的原读取/执行边界，不回签旧内容。配套列表 Change 仅消费本 Change 合格的新接缝，新增请求路由仍需其独立 apply。
4. 保存跨证券/多任务确定性结果、最小失效闭包及真实调用计划，另获本次 ALB 与非 ALB 样本/阶段/完整版本锁/预算批准后执行，留存实际加载、引用、状态、时间、usage 缺失覆盖及清理证明。
5. 交付 ALB 新上游/CIO 原字节及问题对照、非 ALB 新版本内容/稳定性核对和净上下文测量；取得独立裁定及人工最终完成批准后才同步主规格、归档并限定提交/推送，不以本 Change 通过宣称两类列表完成，不切分支/合入 main/建 PR 或自动晋升。
6. 新版失败则停止新运行、保留失败包，不改旧包或自动回退模型/Schema；是否改方案或新增尝试由后续明确授权决定。回退仅针对尚未发布的本次实现和新准备选择，不清理用户修改、不修改已生成报告。
