## 当前状态

- **2026-10-12 最新独立授权接缝修复（旧Change及产品验收继续暂停）**：用户要求“只输入LITE，必要时在宿主界面批准，之后自动继续”，不得把CLI、文字同意或模型字段当真人批准。本轮复用原authorize-single-stock及资料/任务接口，新增[原生审批本地适配](../../../product/tools/single_stock_approval.py)：research_authorize_single_stock标记布尔true的anthropic/requiresUserInteraction，受支持Claude Code按[官方契约](https://code.claude.com/docs/en/mcp#require-approval-for-a-specific-tool)逐次完整真人审批；不单独依赖可被Hook自动回答的elicitation。初始化clientInfo仅兼容性检查，不认证caller；未知/旧/未初始化宿主拒绝，受信本机原生宿主必须实际兑现门禁，自定义SDK自动放行不受支持。私有源/目录/联系配置由安装方一次放入既有稳定Company私有文件，非逐股票授权；本轮未设置真实配置。批准范围锁定证券、问题、来源预算、截止、一次准备及一次Company研究，内部连接hash由服务端取得并重验；ref只关联本会话快照，不是批准凭据，模型无approved/私有凭据参数。批准后的同一次调用自动准备并返回原next_tool及限定company_authorization，主线程据此自动接回原任务/Company-native，不再让用户执行CLI或重复转参。
- **本次确定性结果与边界**：[新增15项审批测试](../../../tests/test_native_single_stock_approval.py)及11个受影响模块合计**158项/92.686s/OK**；命令/原stdout见本会话Bash记录，语法/空白、git diff --check及派生所有权检查通过。合成宿主同一stdio PID：初始化/工具清单→仅LITE请求→精确审批操作（模拟批准后的投递）→原authorize→合成资料真实解析/冻结/绑定→原任务准备/query/submit/read；配置字节不变，无CLI人工步骤/模型/网络。负例覆盖无原生门禁、伪造approved/文字/未签发ref、跨会话/重放、错范围、过期、配置/源/连接变化及原子授权竞态、采集失败不重试、冻结中撤销配置不绑定/建任务；模拟拒绝时宿主不投递授权工具且无业务副作用，不冒称真实UI拒绝观察。原CLI/非Company角色接口回归保留；专业权限、MCP配置、Market/Risk/模型后端未改。只经原生成器刷新主线程及Council派生，仍PREPARED_NOT_LOAD_VERIFIED。**实际Desktop原生审批显示/拒绝、当前私有配置、实际Company自动委派均未验证，不能宣称用户界面验收通过**；真实产品验收保持暂停，无真实授权/研究/重启、无提交推送。后续仅在新的明确使用授权下加载新版并确认宿主兑现门禁；不支持即报告限制，不用聊天确认兜底。

- **2026-10-12 最新独立修复授权：产品验收暂停**。只修“分析LITE”单股入口衔接，先做确定性测试；不恢复本Change、旧研究窗口、Market/Risk任务或旧acceptance，不新建Change/验收体系，不运行真实股票研究。已定位原断点：portfolio-council只有普通Python准备函数名，研究MCP只暴露已冻结任务工具且启动要求冻结连接，造成先有资料才能准备的循环。沿现有Company稳定私有文件新增主线程 `research_prepare_single_stock`，复用原normalize/identity、collect_single_stock_research_data→collect_single_stock_snapshot、Gate和freeze_latest_research_request；成功后返回精确next_tool衔接原research_prepare_task，不启动Agent或旧Stage控制器。
- **本次实际接线与验证**：[单股薄接线](../../../product/tools/single_stock_preparation.py)、[研究MCP](../../../product/mcp/research.py)及现有prepare CLI增加一次/单证券/有期限的操作方本地授权；无授权返回具体authorization_action，来源准入与预算、私有文件、精确旧连接hash、原子一次尝试和冻结后重验保持。私有路径、SEC联系身份和连接凭据不入模型参数/结果；专业工具白名单、MCP配置、Market/Risk代码未改。已用原生成器仅刷新主线程CLAUDE.md、Council派生Skill和所有权登记，配置/专业派生字节不变，仍PREPARED_NOT_LOAD_VERIFIED。新增[全新请求测试](../../../tests/test_native_single_stock_preparation.py)在无冻结资料的同一stdio PID中完成明确授权操作→合成LITE真实解析/采集/冻结→绑定→原任务准备及context；另验证无授权、错误证券/参数、到期/源暂停/源hash变化、权限/symlink、失败不重试、授权撤销、精确冻结hash及专业无准备权限。实际运行13个受影响模块（native单股/动态连接/研究工具/操作方/提交/读取/workspace/export/宿主/Skill、原单股、原采集），**173项/94.656s/OK**（最终接线含Market/Skeptic/CIO工具manifest及原任务准备Schema保持不变的显式回归）；语法/空白及git diff --check通过，原始命令/stdout见本会话Bash记录，不新增证据副本。当前实现与确定性接缝完成；真实宿主加载、真实取数和Company推理均未验证，本轮未改实际私有授权/绑定、未重启产品服务、未启动模型、未提交/推送。产品验收保持暂停；后续仅按新的明确授权及必要一次代码加载条件使用入口，不自动恢复LITE或旧队列。

- **2026-10-12 用户停线**：旧 OpenSpec Change 停止实施，不恢复下述旧授权、研究窗口或迁移验收，不归档、不发布、不恢复长 acceptance。当前独立授权只修复产品实际 BUG“活动MCP仍绑定旧研究任务”：复用现有任务准备与鉴权，实现稳定服务上的动态任务接入并做聚焦确定性回归；不新建Change、不扩展Agent架构、不运行完整股票研究。后续LITE Company使用另按当前任务授权及实际服务加载条件推进。以下历史状态与失败证据保留，不作为本轮执行队列。

- **2026-10-12 独立 BUG 修复与聚焦结果**：实现仅涉及 `product/mcp/research.py`、`product/tools/research_connection.py`、`product/tools/prepare.py`；沿既有私有接入文件每RPC取得当前角色绑定快照，操作方新增 `prepare bind` 显式、带有效期、核对原connection_hash并原子换绑。MCP注册/启动配置、Agent/Skill和原Company业务接口不改；原角色、task_ref/token、请求/input/Gate/cutoff、Evidence、资源锁与数据权限校验保留。新增[动态任务回归](../../../tests/test_native_dynamic_task_binding.py)实际在同一持续stdio PID中先完成合成LITE查询/提交/回读，再在启动后准备MRVL新任务并显式换绑，完成同接口闭环；新旧MCP配置字节及工具manifest不变。旧任务、混用/错误token、错角色、到期授权、越界Evidence、文件权限/symlink/缺失、source完整性错误均拒绝，拒绝不写研究产物或占稿件额度。
- **本轮实际验证与下一步**：`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_native_dynamic_task_binding tests.test_native_research_connection tests.test_native_research_tools tests.test_native_operator_preparation tests.test_native_research_submission tests.test_native_research_reading tests.test_native_product_workspace -q`，**93项/48.446s/OK**；原始stdout和命令见本会话Bash记录。这只证明确定性接缝，非股票研究、原生模型/内容或迁移验收；旧16/22和未完成项不变。真实产品活动MCP是否已加载本轮代码尚未验证，本轮未重启服务、未换绑实际私有运行、未运行LITE Company或完整研究、未提交/推送。下一步先按宿主支持的动作一次重新加载新版MCP；随后新的合法任务只需原prepare及私有bind，不改配置或逐股票重启，再按当前有效授权单独用LITE验证Company。顺序换绑不承诺同角色多请求同时活动；历史无到期字段文件仅保持原读取兼容，新bind必须声明有效期。操作说明已就地更新[INSTALL](../../../product/hosts/INSTALL.md#私有连接任务复用与实际加载)，没有追加或恢复长acceptance。

- `source_id`: `native-market-extra-controlled-acceptance`
- `as_of`: `2026-10-11T15:52:56.305325Z`
- `retrieved_at`: `2026-10-11T15:52:56.305325Z`

- **最新授权与范围**：用户在指令修补完成后额外批准一次独立Market受控验收，单列新增授权，不重置历史3/3。使用原冻结MRVL/SPY、原模型映射/时间/质量，确认最新Agent/Skill实际加载，正常原生首派，自主研究及完整血缘、合法引用、提交、双方完整回读和内容/操作验收；失败即停止，不改代码/Spec/测试标准、不自动修复或重跑、不扩展范围或追加长acceptance。原精确血缘缩减停线及未授权op修补边界保留。
- **本次独立验收停止结论**：仅沿既有零模型入口准备一次新任务`t.f91ae63c34039ddf89a385ed`和增强小包；input.json、gate.json及唯一precomputed逐字节等于原`t.c050e88edbb7bf44f6dd7690`，证券/基准/角色/权限/cutoff不变，旧任务和失败稿未改。私有输出位于既有core-first根的`independent-market-instruction-acceptance-20261011T154244Z`。唯一向原产品会话`local_59a63f0e-2b11-4419-8db4-5b82a963703d`交付任务的SendMessage被宿主auto权限分类器以`Instruction Poisoning`拒绝，未投递；未换工具绕过、重试或进入开发。15:52:56Z核对该会话仍idle、lastActivityAt=14:00:10.290Z。最早实际阻断是任务投递权限，不是已证实的Market研究/加载失败；实际最新加载及本次父子模型未取得，研究未启动，无本次作者、提交或双方回读，内容NOT_REVIEWED、完整验收未通过。原始准备stdout、拒绝工具结果和宿主metadata见本会话对应工具记录；不新增验收文件。以首次准备15:42:44Z计的主动停线15:56:59Z/硬截止15:57:44Z不续期；本次已提前停止，未消费新增研究首派，不自动恢复。
- **实际完成与剩余**：原15项完成保留；唯一正常Market作者真实取得27项完整计算目录、nullable目录路径成立，5.1.4.1据实际证据完成，当前**16/22**。5.1.4.2、5.1.5.1、5.1.5.2及6.1–6.2.2共6项未完成，整体迁移未达标。分母22仍仅来自原任务拆分，没有增加功能或窗口。见[最新正式终态](acceptance.md#唯一干净market终态目录通过两稿拒绝与三次停线)。
- **正式运行终态**：唯一`t.c050e88edbb7bf44f6dd7690`经正常market-native首派干净作者ab082a7cf5613cf40；本次父/子各19条assistant记录model均gpt-6-luna，实际11项角色工具及8方法输入来源可核对，不当API次数、费用或Provider wire。首个CATALOG调用真实使用另一模式null，total=27、next_offset=null；随后六项血缘只读首段32/1518，未完整分页。首稿SCHEMA_PATTERN_INVALID，唯一修订缺op、LOCAL_REVISION_OPERATION_INVALID，两个失败回执均保留、额度0；没有accepted报告或专业/父线程双方完整回读。目录PASS、正式研究FAIL、最终内容NOT_REVIEWED、操作FAIL分列，不相互替代。
- **预算耗尽与历史保护**：两次主线程诊断加本次正式失败已达**3/3**，产品最近metadata为idle、lastActivityAt=13:07:25.095Z；原窗口起点12:52:28.217595Z、主动停线13:06:43.217595Z、硬截止13:07:28.217595Z，不续期。不再prepare、恢复作者、派第四次模型、重开主会话、改旧锁/稿件或提交第三稿。必要新增官方取证未执行，原11次保留；当前无开发会话native Goal清除接口，未执行或伪称已清除，不改Hook、权限、全局配置、进程或私人状态代替。用户新授权的LITE产品试跑是独立请求，不恢复本Change或重置MRVL消耗。
- **已定位但未实施的修补**：native首稿回执缺revision_format_guide，既有纯补丁要求每个change有op，旧维护入口已有完整guide可复用。只定位到机械反馈交付缺口，尚未更新相关handoff Spec/Design、修改产品代码或增加修补测试；本轮未授权该修补，不实施。缺op拒绝、引用门禁及完整重验保持，不自动补op、选引用、放宽路径或恢复第二稿。将来即使补guide，也不证明完整血缘或研究质量已修复；实际加载/研究效果仍须相应授权与证据。
- **适用证据复用**：Company/独立Skeptic/同主线程CIO/原fixture Risk及三稿内容PASS按[第九核心闭环](acceptance.md#第九正式原件核心闭环通过与market未恢复)复用，Risk APPROVED/SAFE_NO_TRADE和原报告未改，不重跑或回签为本轮执行。旧Market的0调用、两个占位参数诊断、未派发错误准备及各时点失败全部留在现有acceptance；本次目录成功不改写它们或认证其唯一底层根因。
- **既有分层检查**：原宿主运行tests.test_native_calculation_pagination，17项/11.402s/OK，只证明确定性目录/分页/nullable及安全契约。原84项与共享接缝30项仅按未变范围复用，不冒称本轮重跑；既有strict、文档与敏感值排除检查见[本轮诊断检查](acceptance.md#最新goal授权与一次原生目录诊断)和[准备/合并记录](acceptance.md#最新修复请求后的定位与合并安排)。本次终态后的文档同步检查另据实际结果更新，不能用测试或勾选替代正式研究/内容PASS。
- **准备与成果保留**：本轮实际新准备2项，漏SPY基准的`t.b3f53c9e6e16c44f04496a84`未派发；仅正确项进入一次正式运行。正确项input/Gate/唯一precomputed与原冻结任务原字节相同，角色/证券/权限/cutoff不变；错误项、旧任务/hash及失败稿不改。不新建平行状态文档或追写原件。
- **上一轮指令修补与剩余边界**：仅修改[Market共享角色](../../../product/agents/runtime_market_catalyst.md:23)的精确引用/必需分页表述及[technical-structure](../../../product/skills/technical-structure/SKILL.md:10)的ID/事实正文歧义，经既有生成器刷新对应两份Claude指令和原所有权登记；没有增加方法、工具或控制层。完整血缘、数值及数据校验均未改，精确血缘缩减停线结论保留。指令修补及本次权限阻断均未证明活动宿主加载、模型执行/内容/操作成功，op反馈仍未修补，3/3及16/22和六项未勾不变。新增一次授权的实际准备与停止见本节本次独立验收结论；没有加载/重启宿主或发布，用户及其他Change修改保留。
- **上一轮指令修补聚焦证据**：本会话实际运行9项现有确定性用例，0.761s/OK：tests.test_native_host_templates中共享来源、Claude工具/方法、Market原生绑定3项；tests.test_native_product_workspace中就地正文、Skill派生、保持无关文件的刷新3项；tests.test_native_calculation_pagination中目录精确引用、完整血缘分页重建、真实完整血缘提交装配3项。随后经product.tools.package_content.prepare_claude_workspace刷新前确认仅两项已审阅来源变化、预期派生差异仅两份指令；刷新后INSTRUCTION_STATIC_CHECK_OK、GENERATED_DISCOVERY_REFRESH_OK，MCP配置字节及角色frontmatter未变，来源/派生正文一致，仍为PREPARED_NOT_LOAD_VERIFIED/UNVERIFIED。原始stdout及执行命令保留在本会话对应Bash工具记录；未改测试文件、不追加acceptance，静态指令断言不证明Skill推理效果。
- **上一轮确定性证据**：本会话实际执行 `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_technical_research tests.test_native_calculation_pagination -q`，28项/11.758s/OK，覆盖现有数值、精确引用、完整分页及拒绝边界。随后源码外内存合成253行、仅计算20日窗口，分别把窗口外基准volume、close、adjusted_close、stock_split设为非法值，四个反例均被原全局检查拒绝，输出COUNTERCHECK_OK；原始stdout为本会话对应Bash工具记录，观察时点为2026-10-11T15:13:23.695832Z。未修改或执行旧冻结任务，不新增报告/acceptance记录；这些证据不证明指标级精确血缘已交付或Market操作已修复。

## 1. 接替与规格

- [x] 1.1 已记录旧路线接替、未完成与失败保留，完成原Proposal、9份Specs、Design与Tasks及对应strict/文档检查。本次确认的规划调整不代替后续apply或实际运行，最新检查只见当前状态与现有验收记录。

## 2. product就地原生接线

- [x] 2.1 已交付当前product薄发现/配置，无业务源码副本；单一正文、解释器/模块根、默认无研究连接、角色映射、所有权/刷新及冲突/漂移/symlink/旧配置迁移正反例通过。本机配置不发布，静态准备不认证新会话加载。
- [x] 2.2 原prepare/研究MCP真实stdio的绑定、错角色/凭据/跨任务拒绝、Skeptic禁读、查询/计算/报告分页、提交及完整精确读取通过；历史/独立入口和inherit保持。只证明对应确定性接缝，调整后准入流程的适用性另由4.4核对。

## 3. 旧控制实际裁剪

- [x] 3.1 已迁移Hook中的计算/金额业务校验并更新消费者，算法、来源/期间/单位及历史负例通过，正常校验不再依赖整个旧控制器。
- [x] 3.2 已按消费者裁剪旧正常Hook派发/父Stop/状态/启动/探针及专属辅助，保留零副作用退役拒绝、合法业务/历史和显式维护；受影响负例通过，无正常回退、无真实Eval/Replay。

## 4. 稳定方法与调整实施

- [x] 4.1 已完成原共享角色、Claude主线程/INSTALL/README精简，保留方法、权限、来源、分页和完整读取；对应结构/治理/历史/独立入口、版本及文档检查通过。本次新增流程差额见4.3，不以旧完成宣称新指引已生效。
- [x] 4.2 已分列静态发现、候选、已加载内容与当前来源，支持获准非执行观察和有效去重证据复用；就地/导出结构回归及来源指引检查通过，不认证新会话执行。
- [x] 4.3 收敛自有主线程、INSTALL、必要README/portfolio-council和受影响角色说明，实施一次完整交付、业务准入/显式诊断分离及分类停止；通过原生成器刷新必要派生。验证精确角色/工具/inherit、共享来源和安全范围不变，事故时间线与必做四绑定巡检退出正常路径，已有目录说明足够时不追加同义提示。
- [x] 4.4 核对现有逐调用准入、Skeptic禁读及原作者有限修订是否支撑调整；只对实际缺口在既有接缝最小修补。以对应错请求/角色/任务/旧活动绑定、PIT/资源漂移、修订上限/完整重验及旧启动拒绝正反例验证，未变证据注明理由复用；无缺口则记录无需Python修改，不新增调度/重试器或全仓测试前置。
- [x] 4.5 实施检查及实际准备/运行授权成立后，为新产品会话一次准备当前就地发现/必要连接、原fixture新任务与冻结Market新任务/私有产物，明确核心CIO依赖齐后准备。验证身份/权限/旧产物未覆盖、来源与必要观察入口、模型/任务/时间/取证上限及一次交付完整性；不得复制源码、创建新数据来源或凭本规划启动产品，静态准备不勾实际执行。

- [x] 4.6 在开发侧操作方scripts/prepare-native-agent-grant.py复用原agent_grant并重验明确现有任务，机械派生精确mcp_arguments及可直接转交的specialist_args；恢复锁内prepare.py原字节，保留原平铺/完整授权、资源锁及旧任务/hash。收敛主线程/INSTALL对顶层授权、draft语义、专业完整转交及写入前格式纠正的稳定说明，经原生成器刷新。验证最小范围/私有写入/旧格式兼容、资源漂移/缺授权/错token无写入及合法原路径恢复，不放宽MCP、不增加工具/任务/作者/后端、自动注入或重试器；实际模型参数和研究效果仍由5.1.3–5.1.5验证。

## 5. 就地链路闭合与有限真实Claude验收

- [x] 5.0 原D6-D共享Skill来源观察、单次调用、终态预算与前后完整性已通过；只保留原时点成果，D6-A/C原失败保持，不认证新会话来源/工具/模型或内容。
- [x] 5.1.1 验证新会话核心Company/Skeptic与主线程的当前来源、实际模型、角色/方法及精确工具；先独立Skeptic后Company，首轮实际输入/工具隔离成立。证据在核心CIO消费前核对，不要求Market先通过；模板、自报和旧会话观察不能代替。见[核心执行节点](design.md#511-核心原生执行与独立首轮)。
- [x] 5.1.2 原SEC-AAA fixture的新Company/Skeptic自主查询、必要授权计算、合法提交及精确完整回读成立，任务/请求/Gate、原值/期间/单位、引用血缘和分页覆盖可对应；原作者修订仅按既有一次上限。旧两稿不拼接为本轮新执行，未查引用/缺页/安全失败不通过。见[新正反报告](design.md#512-新fixture正反报告)。
- [x] 5.1.3 核心正反依赖与5.1.1核心必要证据齐后，由同一产品主线程准备CIO任务、完整消费、自主综合、提交触发原fixture Risk并完整读取最终产物；实际消费、risk_status/risk_support/fixture_decision和同主线程身份可核对。Risk否决和原修订总上限保持，不等待独立Market、不建CIO子Agent或Risk执行器。见[核心综合](design.md#513-同主线程cio与原fixture-risk)。
### 5.1.4 独立Market路径与正式执行（原5.1.4拆分）

- [x] 5.1.4.1 **实际证明原生目录路径并处置有据缺陷**。原两次主线程诊断保持FAIL且不重复；按[Design最新修复合并顺序](design.md#当前剩余工作方案仅规划)，在有效来源、冻结绑定、权限、模型/预算及必要观察入口成立后，合并到唯一正常Market首派作者的首轮目录业务调用，不另建诊断任务或专业。验收：实际返回目录且路径可用，必要有据修补已聚焦检查/加载，才勾并继续研究；准备/首派/静态Schema或确定性测试不等于通过。拒绝、不能合法表达、资源漂移、必要缺证或到时就停止，不继续选择/提交，不改旧锁/稿件。目录通过不替代完整研究、干净上下文或旧失败唯一根因；没有项目缺陷证据无需代码修改。
- [ ] 5.1.4.2 **完成唯一独立新Market正式执行与证据核对**。最新修复合并顺序下，来源/授权/冻结绑定/权限及必要观察成立后，沿既有准备/连接使用原冻结MRVL/SPY TECHNICAL_STRUCTURE输入、Gate/cutoff/precomputed，正常market-native首派一位干净作者；其首轮实际目录成功证明5.1.4.1后才继续研究，拒绝即终止。实际首派及初始输入须证明未恢复历史失败作者、未注入诊断脚本/旧稿/开发选定计算，不能只凭新ID或fork模板。最多15分钟、14分15秒主动停线，首稿加最多一次该任务原作者allowed_paths精确修订。验收：自主读取计算目录、选择研究所需结果并完整读取所需血缘，合法提交，专业/父线程双方按精确回执完整回读；原角色/8方法/11工具、批准模型及来源/授权/隔离证据齐全。见[独立切片](design.md#514-独立冻结market切片)。不要求消费全部27项或越权查询OHLCV，不以空选择/合法不足稿/诊断成功代替研究，不解封旧稿、不重跑核心；再失败不自动追加。

### 5.1.5 内容与操作分别裁定（原5.1.5拆分）

- [ ] 5.1.5.1 **补齐Market基本内容裁定，复用核心三稿PASS**。使用5.1.4.2同一次正式任务的完整报告及真实计算返回，按[现有technical-structure四问题](../../../product/skills/technical-structure/SKILL.md:12)核对趋势、相对基准、波动/回撤/量价及推翻条件，检查依据、数值/期间/单位/方向、重要反证与限制；不规定选哪项计算或固定观点。验收：在现有acceptance给出简短内容裁定；核心错误FAIL，无稿/未完整读NOT_REVIEWED，未尝试支持的资料不足不能通过，不改写原报告content_verdict。Company/Skeptic/CIO继续引用原完整审阅及未受影响理由，不另派Reviewer或重读重跑来重复取证；最终仍须四稿均有适用PASS。
- [ ] 5.1.5.2 **补齐Market一次交付的操作可用性裁定**。与5.1.5.1独立核对5.1.4.2的同一执行过程，不再创建任务或重开窗口。验收：稳定说明和一次完整任务交付后，作者自主完成必需研究、合法提交与双方完整读取，未靠开发线程运行中补参数、调用顺序、指标或观点；正常权限批准、既定证据核对及产品主线程履职不误判为干预。复用核心适用操作证据，Market未完成研究即不通过，即使没有开发干预或已有合法报告；过程PASS也不替代5.1.5.1内容PASS。见[内容与操作](design.md#515-内容与操作可用性)。

**执行依赖与变更理由**：原5.1.4拆为“路径判别/有据条件修补”和“正式执行”，原5.1.5拆为“内容”和“操作”，避免一项同时代表实现、诊断及所有验收；不删除任何有效完成条件。执行观察顺序为：唯一正常干净作者首派 → 首轮实际目录成功并完成5.1.4.1 → 继续研究完成5.1.4.2 → 5.1.5.1与5.1.5.2分别裁定 → 6.1。最新修复委托只合并路径观察与正式执行，不提前勾路径，不删除任何结果门禁；一次正式执行的同一组证据供后两项共用，不是四个模型窗口。所需观察入口在执行前明确，随首派才产生的实际记录按Design时点核对，不要求事先已有新作者执行证据。

**删除的重复或过时前置解释**：核心三稿重新审阅/重跑、先找到新代码缺陷才诊断、必须修改代码才可正式验收、跨独立任务强制恢复历史失败作者、必须追清Provider唯一根因或固定新增一次导出均不作为待办。沿既定总边界，仅现有材料不足时最多一次必要合并官方取证，既有11次保留、拟累计12；诊断已用该额度则不另增。旧D8–D16及其他结束安排只供历史，不恢复余额。4.x及5.1.1–5.1.3保留原证明范围；如出现实际缺陷，只处理受影响接缝，接口/设计确变才同步规划。完整八维、ALB/非ALB、完整MRVL链、账户、其他宿主及Promotion按[关系表](design.md#承接与后续需求)保留，不增加为本迁移前置。

## 6. 人工完成与限定发布

- [ ] 6.1 **汇总有限迁移验收并取得有效完成批准**。5.1.4及5.1.5全部通过后，在现有acceptance汇总原目标、实际变化、核心/Market执行、四稿内容、操作可用性、证据复用与遗留限制，并核对必要Specs/Tasks均有适用证据。验收：汇总结论与实际产物/原记录一致，明确人工完成批准或届时有效的达标后完成委托；不把历史委托当本次执行许可、现时PASS或已人工审阅报告。Provider wire、精确费用等非必需未知如实披露，不因此无限补证；必要模型/工具/隔离或内容缺证仍阻止完成，不以LOC、任务数、规划或诊断通过代替。
- [ ] 6.2.1 **同步主规格并成功归档**（原6.2第一部分）。依赖6.1及届时有效收尾授权，按已验收差额同步主规格、验证OpenSpec一致性并执行成功归档。验收：主规格包含本Change实际生效契约，归档保留全部原失败及完成证据，记录实际检查与归档结果；未通过或未批准不归档，不自动启动Eval/Replay/Promotion。此项完成不等于已提交或发布。
- [ ] 6.2.2 **限定提交并推送已成功归档的迁移差额**（原6.2第二部分）。依赖6.2.1及当时发布授权；只处理已审阅且可归属本Change的hunk，核对相应验证与敏感信息，排除本机配置/私人材料/Tiger/Intake及其他Change。product/.mcp.json仅从索引移除并保留磁盘，旧Capsule及公共fixture模板保留。验收：限定提交和推送成功，报告远端hash及剩余工作区；无法分离、含敏感信息或检查失败就停止相关发布，不force push。当前达标后限定收尾委托有效，但未达标不执行6.1–6.2.2。
