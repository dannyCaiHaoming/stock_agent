## Context

动机见 [proposal.md](proposal.md)。现有 research_input 仅显式区分 SINGLE_STOCK_RESEARCH 与真实 PortfolioHandoff；单股身份核实已限制普通股/市场/币种/申报制度并验证来源/PIT，不能用它宣称任意代码都可研究。现有 Company 已有仓库外逐证券 IncrementalPlan/View/严格报告复用，多维只有有限依赖恢复，独立 Skeptic 与 CIO 均有原阶段准备/冻结/校验路径；尚无完整无账户列表输入和全研究链列表刷新证明。

本设计只扩展既有入口，不把“列表”做成新的 Runtime。前置 `repair-single-stock-evidence-consumption` 负责通用内容/处置/精确计算、四阶段固定 deadline、可信任务状态和 usage；本 Change 负责列表输入与绑定、增量/失效计划、原调度接线、报告复用和批次归集。前置接缝未完成时可以做本 Change 授权内确定性输入工作，但不能假装新列表执行已可用或自动 apply 前置 Change。

## Goals / Non-Goals

**Goals:**

- 两种来源模式均完整可追溯，不改 Intake 事实确认、不伪造账户；既有单股读取保持。
- 按证券/任务/实际依赖确定失效，仅重做必要研究；输入列表、预算和执行成果分别存证。
- 有界并发/时间/usage 在整个批次共享，逐项失败及待运行可见，恢复保持原件并重新验证。
- 报告及支持包长期可读，当前复用与历史判断/时间分开；两个模式及刷新独立验收。

**Non-Goals:**

- 不新增券商或来源、交易接口、订单/换汇/账户写入，不开放 PORTFOLIO_ADVICE、ETF/期权研究、多资产 Risk 或证券排名。
- 不新增 Agent、Memory 调度权、模型评委、后台轮询/定时刷新、作业队列服务、第二编排器或历史数据库。
- 不把保存的报告提升为 Evidence，不改变 Skeptic 独立首轮隔离，不由 Python 选择投资结论。
- 不承诺外部服务永远快、所有旧报告跨 cutoff 可复用或在途 token 可硬截断；不延长原阶段 timeout，不自动续额度。
- 本文是待显式 apply 的设计，不表示列表入口/Schema/复用/批次执行当前已经实现。

## Decisions

### 1. 自选股用第三种显式输入，持仓继续引用原 Handoff

新增 `stock-list-research-request/1.0.0`，input_kind 固定 STOCK_LIST_RESEARCH，输出范围固定研究。持仓分支继续原 PortfolioHandoff + 独立 CouncilRequest，不再复制私人账户事实到列表对象。两者由 `stock-list-refresh-request/1.0.0` 保存刷新指令：request_id/hash、source_mode、原件 ref/hash、可选 previous_result ref/hash、所请求阶段/问题/cutoff及预算授权引用。原件不可变，刷新只生成新对象。持仓事实增删/数量/现金改变回 Intake 重新确认；只改问题/范围/阶段无需重新确认账户。自选股增删创建新列表请求，不需伪造账户确认。

自选股请求保存 ordered items，每条具有 item_id、原输入标签/市场/问题、用户输入来源、identity_status 与经核实 security/identity_sources 或明确失败原因。未核实值不冒充正式证券；按既有 resolve_single_stock_identity 的受支持普通股范围逐项核实，输入不授权新来源或突破市场/申报准入。失败项保留原标签和来源，不派正式研究；其余合法项可继续。重复 canonical 身份保留输入映射，同身份不同问题作为不同研究需求保留，不能按 ticker 或显示顺序抹掉问题。承载事实的条目及身份来源保留 source_id/as_of/retrieved_at，事件类 envelope 的时间不冒充原来源时间。

research_input 增加第三模式的显式 validate/subjects/binding/load 路由；audit/stock-list-request.json 绑定 frozen manifest，不因文件缺失自动回退 Handoff/单股。一项列表也仍是列表。沿现有 latest 准备→资料取得→共同 cutoff 冻结：保存 preparation_request/hash与实际响应获取时间，最终请求是新冻结对象；历史 cutoff 不推进，缺合格旧冻结对象模型前拒绝。

**替代方案：** 空 Handoff 违反账户语义；拆成无关联单股请求会丢列表 lineage 与总预算。选择独立输入 envelope，共用既有身份/研究 adapter。

### 2. 新协议路由保留完整来源模式和成员绑定

新列表阶段采用 `stock-list-stage-binding/1.0.0`：绑定列表/刷新请求hash、输入模式、原 Handoff 或列表原件、成员集合hash、stage和当前目标 item/security。Company、多维与 Skeptic 在现有 Schema family 中新增列表支持版本，不原地改旧 Schema；task/report/invocation 的关联值由可信层生成。具体版本号按 apply 时实际版本清单的下一未占用版本确定，首次实现切片即冻结准确映射及测试；不按自然语言或字段猜新旧格式。

列表研究级 CIO 新增 `predecision-cio-request/4.0.0`，显式支持 STOCK_LIST_RESEARCH 或持仓列表刷新绑定，每次当前 CIO invocation 的 target_scope 为一个核实证券，复用前置 Change 的 synthesis/3.0.0 与 native-cio-draft/2.0.0。原 v1/v2/v3 源模式和执行范围不变；v4 保留 Gate、完整 read/query、计算支持和全部当前目标正式挑战，并在准备时冻结获准目录，不在模型运行时任意裁切源报告。列表共享的多证券报告只获准当前目标所需且原契约允许的内容；直接 Evidence 仍由本 invocation query。禁止将 A 的 claim/calculation/challenge 当 B 的支持，版本/成员/hash/允许集错配拒绝。

CIO 仍是原主线程阶段，逐目标调用不是新增 CIO Agent。最终列表只输出机械索引及逐目标原稿链接，不由 Python 生成相对排名/总体投资立场。持仓模式亦为研究综合，不授权当前组合动作、账户适配或 Risk 执行。原 fixture/Risk 不改。

**替代方案：** 原单股协议静默接受多目标会绕目标门禁；一份跨列表自然语言综合难以区分证券支持关系。选择显式版本绑定和原 CIO 的逐目标 invocation。

### 3. 数据计划和研究报告失效分两层，前置于模型

数据层复用既有 ResearchMemory/IncrementalPlan、dataset checkpoint、内容寻址原件和 View；按 security/dataset/来源策略预算刷新，不另建批量缓存。新列表不改变资料版本/原检索时间或其他证券水位，来源失败、checked_no_change、缓存命中、有效新增/修订分别保存。公开同证券资料可跨两模式共享，账户/列表问题/私人报告绑定仍隔离。

研究层新增 `stock-list-refresh-plan/1.0.0`：source/previous/current request ref/hash、resolved cutoff、完整版本锁、每项输入映射、每任务 role/stage/security/question、所需 View/Gate/允许集与实际依赖hash、RUN/REUSED/BLOCKED/REMOVED/NOT_REQUESTED、理由、可复用原报告/原验证与当前重验、准确父/子计划和预算分配。plan_hash 绑定新请求和可执行集合，模型无权改计划或推进 checkpoint。若计划后的资料/依赖变化，拒绝陈旧派发并由确定性准备生成新计划；新增模型额度需再获批准，不能边跑边无限扩闭包。

变化传播表：

| 变化 | 数据准备与报告动作 |
| --- | --- |
| 固定 cutoff/资料/版本/问题均同，仅新 run、无变化检查或顺序 | 必须当前准入/完整包重验；语义指纹相同者 REUSED，原时间/hash不变 |
| 新增证券 | 新成员数据/报告初始化及实际共享依赖消费者；未受影响旧项重验，不全链重跑 |
| 删除证券 | 当前计划 REMOVED、不派发；历史和checkpoint不删除；实际依赖成员集合的共享任务失效 |
| 新行情/披露/口径修订 | 相关数据集增量，更新引用该对象的任务及依赖闭包；不吞修订、不按最新日期伪覆盖 |
| cutoff推进 | 重新 Gate/View、窗口/PIT和报告适用检查；绑定旧cutoff的报告不冒充新综合，不能证明可迁用就 RUN/BLOCKED |
| 问题/模型/Skill/Schema/Adapter/Risk Policy/数据版本 | 对对应语义/执行依赖报告及消费者失效；身份/窗口/引用门禁重验 |
| 已知内容错误、缺收据、损坏或未确认隔离 | 拒绝内容通过缓存，保存旧原件/裁定，计划必要重做或阻断 |
| 仅Handoff数量/现金变化 | 需新账户确认；公开资料可兼容复用，报告私人输入绑定不同不静默重签，依实际准入重做/重验 |

不能承诺“新增一只只跑这一只所有情况”：Macro/Market 或同行选择若实际依赖成员集合，受影响任务也需重验/重做。重做依据是可信输入/版本/依赖，不是 Python 的投资重要性评分。

**替代方案：** ticker+TTL或全批hash会误复用/误失效；全面重跑成本高且掩盖依赖。选择两层计划及最小实际闭包。

### 4. 必要报告复用扩展现有持久化接缝，而非新平台

Company 沿已有完整历史包、reusable_report、输入 fingerprint及当前 source freshness校验。多维、Skeptic、CIO 仅为本列表刷新所需，扩展同一研究报告保存/读取边界的类型和索引字段（report_kind、原source binding、版本、实际依赖、允许集/隔离、完整对象引用）。沿既有仓库外内容寻址对象+原子有效索引，不另造一套DB、租约、任务队列或通用跨Agent知识图。

原 JSON/中文、请求/资源锁、View/Gate/被选择 Evidence及计算/收据、依赖报告hash和原执行/隔离证明作为最小完整包。可信 finalizer验证后才索引，失败只保留尝试。当前 REUSED 引用原包并写 `stock-list-report-reuse/1.0.0` 证明（原报告身份/hash、当前请求/任务/输入指纹、重验项/时间、允许的绑定关系和限制），不把原报告复制改成当前run/invocation或更新generated_at。消费者需显式接受“原报告+当前复用证明”，原报告内部闭合仍按原请求检查；不能直接将原 IDs 当新报告 IDs。

Skeptic独立首轮允许集/任务模型/版本/隔离证明单独重验，旧“没看正向”不自动证明当前可复用；针对性反证依赖正向报告hash者随对应变化失效。历史判断不升级事实，当前内容裁定与机械重验分列。原临时run移走时只从长期完整包验证；必要对象缺失/私人上下文权限不足明确拒绝，不补模型、不绕权限。

**替代方案：** 全链禁复用不能满足重复运行成本目标；改写原报告绑定会污染历史；新报告仓库重复架构。选择仅所需报告类型的既有保存/校验扩展。

### 5. 原主线程消费计划，全批只拥有一份预算

新增列表计划读取/验证和机械归集函数，接入原 portfolio-council 阶段指引及 CLI/宿主参数；Python只规划/核验/写产物，不直接启动模型或当研究CIO。主线程在每个获批阶段运行既有coordinator/角色/Hook，按计划填充就绪槽位；默认沿原并发3，若获批计划指定不同正整数则显式冻结。全批并发限制是同时活跃研究子任务总量，不是每只股票各3；不同阶段coordinator不同时各拥有全额。先使用现有阶段屏障，再在阶段内按原输入顺序有界轮转就绪任务，不新增抢占/优先级评分scheduler。

`stock-list-budget-allocation/1.0.0` 引用前置研究执行预算/usage契约，记录全批硬调用额度、固定总执行期限、阶段/任务可用额度、独立清理grace及观测token额度/UNKNOWN政策。分配只可消耗剩余预算，stage timeout不超过原批准值及批次剩余时间；切波次/切证券不重置总deadline。父/子调用数按实际coordinator和task计划列清，失败在模型前或真实调用后分别记，不能用task数推费用。token后置可见/父子范围未知沿前置Change规则单列，不宣称在途硬限额。

全部可复用时不启动模型；预算不足完整保留pending并NOT_STARTED/BUDGET_EXHAUSTED，不隐去证券或隐式延长。用户仅要求某阶段时，下游NOT_REQUESTED。正式运行仍仅宿主Terminal `scripts/run-product-smoke.sh`，准备/确定性工具不借此启动模型；不建设批量bash循环绕过原准入。

**替代方案：** 各证券独立全额跑完会乘法放大并发/成本；第二批量launcher会绕版本/加载证明。选择现有调度的计划参数与全批共享额度。

### 6. 失败归集与显式恢复只读旧成果

使用 `stock-list-research-result/1.0.0` 引用请求、plan、完整输入映射、run/stage/task/invocation、RUN/REUSED/原因、原报告/hash及execution/persistence/content_acceptance。批次机械aggregate为COMPLETED/PARTIAL/FAILED/INTERRUPTED/BLOCKED（只按所请求任务真实覆盖，不按投资评分）；研究充分性/内容裁定另列，即使机械COMPLETED也不自动内容PASS。REMOVED和NOT_REQUESTED不冒充成功；SUPPORTED、SOURCE_LIMITED、身份/执行失败等类型不互换。中文页面/CLI沿现有读取/渲染入口同源展示完整列表及逐稿引用，不新增自动刷新按钮或后台服务。

单项失败只阻断实际依赖，不占无限等待槽；无依赖任务可在剩余额度继续。共享库不可安全写、可信状态漂移、批次中断或总预算耗尽停止相关派发，原数据/checkpoint/合格报告仍保留。父等待和最后有效事件沿前置Change，不靠自报进度；只能清理本组，远程取消不能证明时UNKNOWN。

恢复是显式新刷新请求，引用旧result但生成新plan；重新验证来源/版本/允许集/原件hash/保存状态。已合格成果若兼容则REUSED，失败/过期项及闭包RUN/BLOCKED；不自动重启、追加局部修订、换模型或循环排障。源码/权限/模型额度不足不绕过工具，保存具体最小需求。

**替代方案：** any-failure全批rollback丢成果；自动resume会隐式花费；多数成功算全绿会丢覆盖。选择逐项状态、现有持久化和显式新请求。

### 7. 两模式刷新验收与真实调用分开批准

确定性矩阵沿实际输入解析/身份/标准化→Memory增量→View/Gate→新绑定/plan→原coordinator/Hook/MCP作者合成稿→原装配/校验→持久化/复用/中文索引，替身只放外部transport、时钟和模型执行边界。覆盖两模式、列表长度大于并发、重复/歧义/未支持成员、无变化/增删/换证券、cutoff/披露/版本/依赖变更、成功与局部失败混合、空wait/终态未通知、共享故障、预算耗尽、旧目录移走、漂移拒绝和显式恢复。检查实际请求范围/调用差额/产物hash，不只断言Prompt。

另获真实授权计划必须包括两种模式的具体样本列表、阶段、cutoff、来源、完整版本锁、准确父子数、数据/时间/观测usage上限和停止条件。默认以每模式至少2个合格证券证明列表而非单股；样本数不成为产品数量上限，真实持仓须用户有效确认，不合成假账户。取得初次真实研究及同cutoff无变化刷新的宿主加载/执行、严格复用、实际调用/usage覆盖和独立内容核对；其他变更/故障可用标记为受控的确定性矩阵验证，不自启真实失败注入或等待外部自然更新。没有授权或输入则相关验收保持未完成，不缩成另一模式。

本Change不启动 Runtime Eval/Replay/Regression/Calibration/Ablation/Promotion，也不将对已有冻结报告的只读复用检查叫Execution Replay。前置ALB实质修复和非ALB新版本证据可复用为底层接缝依据，但不替代本Change两模式实际列表证据。由用户或本次明确授权复核者裁定，不联系暂停Reviewer或另起Agent。

**替代方案：** 只单股ALB验收不覆盖列表；大量真实故障试跑浪费预算。选择聚焦确定性矩阵+两模式获批真实初次/无变化刷新证据。

## Risks / Trade-offs

- [版本路由触及多个生产者/消费者] → 新版显式绑定及拒绝负例，原Schema/报告hash不变，真实加载与静态配置分列。
- [复用过宽或过窄] → 问题/cutoff/来源语义/版本/真实依赖分别列原因，未知拒绝；输入指纹不包含无语义观察噪声但不删除PIT和私有绑定门禁。
- [共享Macro/同行任务的实际列表依赖] → 对成员集合依赖显式失效，不承诺增一只永远只跑一只；不为未来可能依赖扩建图平台。
- [长期包缺对象/私有权限或保存失败] → 既有完整包原子有效索引与当前复用证明，不补hash、不改旧稿、不自动模型替代恢复。
- [全批预算不足/usage源不完整] → 完整pending清单、固定调用/时间边界及PARTIAL/UNKNOWN token，不能无限续期或以父子相加造账。
- [真实持仓输入/运行授权尚缺] → 确定性工作不受阻，但真实两模式任务保持未完成，不索取凭据、不伪造Handoff。
- [前置Change尚未实现/验收] → 本Change只接线已合格接缝；共同真实证据需要授权且明确对应哪项任务，不把依赖当实施/运行许可。
- [工作区已有其他Change与用户修改] → 仅本范围hunk，其他任务不编辑/读取状态作进度推断；归档前不能安全分离就暂停发布。

## Migration Plan

1. 完成两Change规划coherence与strict。当前仅规划，所有Tasks未勾，不调用模型/Provider、不修改产品代码或主规格。
2. 获本Change显式apply后先实施输入/绑定与旧分支确定性验证；底层执行接缝沿前置Change独立授权实现，不自动扩大apply。
3. 在现有Memory/报告校验上扩展必要类型与复用证明，再实现两层计划、原调度预算/状态接线、结果索引/中文消费者；各切片聚焦验证通过才勾。
4. 完成零模型两模式/增删/变更/失败/恢复矩阵与旧兼容；确定性生成实际真实调用/数据预算计划供批准，不能先跑后补授权。
5. 经本次具体范围/预算批准才由宿主取得两模式初次/无变化刷新与独立内容核对证据。缺输入/权限/预算则仅暂停对应真实任务，保存已完成结果。
6. 满足Specs/Tasks和独立裁定后请求人工最终完成批准，随后按开发流程同步/归档/限定提交推送；不切分支、合入main、建PR或晋升。
7. 新分支失败即停本次运行保留原件；回退仅本次未发布代码/新准备选择，不回写旧报告/锁、不自动退协议或模型、不删除用户dirty。
