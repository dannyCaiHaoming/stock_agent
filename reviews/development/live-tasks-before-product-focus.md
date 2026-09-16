2026-09-10 NASDAQ HTTPS 定点修复：36 项受影响确定性测试及严格校验通过，一次有界真实目录请求 HTTP 200，200 行/声明总数 7139，明确 PARTIAL；原文与页面 hash 已保存。Task 1.5 完成，当前 19/24。证据见 `reviews/development/nasdaq-tls-fix.md` 及对应 evidence JSON。未启动行情/SEC/模型，不以目录成功关闭 2.6、5.2–5.5。以下失败与进度记录保留为历史。

2026-09-10 v4 实施完成：Task 1.1、1.3、3.1、4.3、5.1 经 175 项 live 接缝测试与严格校验关闭，当时 18/24。完整证明见 `reviews/development/live-admission-v4-verification.md` 及 tests JSON；本轮个人研究批准不再写成上游 AUTHORIZED。真实宿主单股已尝试一次，在第一个 NASDAQ 目录请求以 NASDAQ_TRANSPORT_FAILURE 停止，退出码 2，未调用行情/SEC/模型；实际命令、输入/错误 hash 见 `live-admission-v4-host-attempt.json`。当时 1.5、2.6、5.2–5.5 保持未完成；不将传输失败当安全研究通过。以下 13/24 等为调整与实施的历史阶段。

2026-09-10 历史拓扑批准记录：用户批准 NASDAQ 股票池、yfinance 主行情、AKShare/东方财富受控备用、SEC 披露，并同步本 Change 四类规划产物。此前唯一东方财富/禁止 Yahoo 的表述仅为历史阶段，现行规则以 Design 1、1.2 和当前任务行及 Specs 为准。本轮不修改实现或重新试拉。1.2、4.3 恢复未完成；新增 1.5、2.6，其余已完成项仅保留未受影响机制的原证明，不代表新拓扑通过。

## 1. 数据访问条件与输入契约

2026-09-10 当前批准调整：用户对“个人研究运行批准与上游许可核实状态分离，后者保留 UNVERIFIED，继续真实单股→三股验收”的请求答复“批准”。完整范围、记录标识与停止条件见 Design 1.3。本次只完成规划同步；未开始新数据请求或模型运行，也不将此批准作为 Task 5.5 的最终完成批准。

受影响的 Task 1.3、3.1、4.3、5.1 恢复未完成，当前 13/24；原因分别是双状态新契约、锁与重验、来源/报告说明、新接缝证据。原 167 项测试及 220 文件 hash 仍是旧快照证据，未受影响请求预算/身份/PIT/Risk 机制按 hash 和差异复用，不能直接证明新准入契约。2.4/2.5 已完成部分不抹去，但其准入调用接缝须纳入 5.1 的受影响补验。以下阶段进度是历史，不覆盖当前复选框。

2026-09-10 数据接缝收尾：Task 2.1、2.4、2.5、5.1 完成，整体 17/24。新增备用身份负测、主源版本错误不得被过期回退掩盖、Yahoo 读取中限长和发送前范围检查；当前 167 项 live 测试全部通过。完整任务/规格映射、命令、220 文件 hash 与执行输出见 `reviews/development/live-data-seams-closeout.md` 及对应 tests.json。Task 2.6 的真实主行情调用仍与 5.2 合并，不提前勾选；来源准入、真实目录和单股/三股研究、独立复核与人工批准仍未完成。下文计数仅为历史阶段。

2026-09-10 最新：profile 3.0.0 与目录/主备来源版本锁已接通，底层上下文重验、Schema/模型/选择漂移负测及文档样例通过；Task 1.3、3.1、4.3 完成。证据及适用范围见 `reviews/development/live-topology-v3-verification.md`，完整当前 live 测试日志与相关文件 hash 见同目录 `live-topology-v3-test-result.json`。158 项 live、36 项共享接缝均通过；真实模型/网络未运行。整体 13/24，其余项不因局部证明自动关闭，下文进度按历史阶段解释。

2026-09-10 最新续进：已接入主备 collection、SourceSelection/snapshot v3、备用行情身份原文重验、冻结/PIT/估值/prepare 及报告来源展示；155 项 live 确定性测试全部通过、无跳过，严格校验通过。完整本轮文件 hash 与适用范围见 `docs/data/nasdaq-primary-backup-progress.md` 最新节。profile/discovery/Trace 的当前拓扑版本锁尚未同步，相关整项任务仍不勾选；不以合成 prepare 成功冒充真实 Council 运行，整体仍 10/24。本记录更新下文较早的“主备 collection 尚未接通”进度，不扩张旧证据。

2026-09-10 本轮 apply：合并依赖安装、版本锁及 90 项限定确定性测试通过，Task 1.2 完成。新增 NASDAQ 目录及 v3 来源角色的离线接缝，修复 Yahoo 429 立即停止；具体 hash/命令/范围见 `docs/data/nasdaq-primary-backup-progress.md`。这些只部分覆盖 1.3、1.5、2.4，仍不勾选。NASDAQ 官方条款新增核对见来源记录；正式访问依据未确认，1.1、真实目录及 5.2/5.3 保持阻断，不请求真实行情或运行模型。整体 10/24，主备 collection/profile/Trace 尚未接通。

历史选型记录（已被本文件顶部批准取代）：2026-09-10 用户曾确认 AKShare/东方财富替代 Yahoo 为唯一行情源、SEC 保留。当时恢复 1.2、1.3、2.1、2.4、2.5、3.1、4.3、5.1 共 8 项未完成，表示旧 Yahoo 证明不能自动覆盖新源；1.4 未追加试拉次数。本段不再规定当前主备拓扑，当前状态以任务复选框为准。

历史技术试拉批准：2026-09-10 用户允许尝试 Yahoo 与 AKShare，并批准将有限技术试拉与正式来源准入分开。适用范围及批准原意保存在 Design 1.1；此前“用户暂停 Yahoo”的阶段记录仅作历史。当时新增 Task 1.4，不清空旧任务或扩大原验收证明；Task 1.1 仍受正式来源准入约束，试拉成功也不能勾选 1.1、5.2、5.3。

2026-09-09 后续范围澄清：用户明确仅暂停 Yahoo，允许继续 SEC、离线契约及合成测试。此前暂停记录不再表示全部实施停止；不自动换源，不取消真实数据准入与验收要求。

2026-09-09 实施记录：Task 1.1 的来源核对已记录于 `docs/data/us-equity-sources.md`，但 Yahoo 自动化访问许可尚未确认，状态为 `BLOCKED_PENDING_AUTHORIZATION`。依本任务及 Specs 暂停；未启用采集、未自动换源，所有复选框保持未完成。

- [x] 1.1 交付 `docs/data/us-equity-sources.md`：分别核对 NASDAQ 股票池、Yahoo/yfinance 主行情、东方财富/AKShare 备用及 SEC 的使用条件、免费范围、未知额度、身份与最小域名；按 Design 1.3 保存本次个人研究批准、范围及记录 hash，与上游许可核实状态独立记录；未核实保留 UNVERIFIED，不伪造 AUTHORIZED/VERIFIED。有效个人批准允许限定运行；缺批准、暂停、超范围、明确 DENIED 或实际拒绝仍停止，不修改代理。
- [x] 1.2 更新 `pyproject.toml` live 可选依赖及锁，同时固定已选 yfinance、AKShare 和交易日历；实际验证组合兼容、SDK 参数与请求/解析边界，fixture 不依赖 live 安装或联网。已在新的独立合并环境实际验证，见 `docs/data/nasdaq-primary-backup-progress.md`。

2026-09-10 换源实施第一阶段：`docs/data/eastmoney-adapter-progress.md` 保存依赖、真实 SDK 离线解析、日历及 fixture 隔离证据和完整文件 hash。Task 1.2 完成；Task 2.1/2.4 仅新增独立请求接缝，尚未连接正式采集、身份及缓存，不勾选。来源准入未确认，不新增试拉或运行模型。
- [x] 1.3 版本化 SourceAccessProfile、UniverseSnapshot、SourceSelection、fact/snapshot/profile 与身份映射契约，区分 provider/client/data_role；验证合法单证券选择、未知来源、无选择记录混用、伪装 trial 和锁漂移，新增 live-source-access/4.0.0 双状态契约并显式版本化 snapshot/profile，统一 canonical 准入判断；覆盖 APPROVED + UNVERIFIED、无批准/暂停/未知值/超范围/DENIED/未来时间/批准 hash 错误，旧 v1/v2/v3 包保持原语义，不改写历史锁。
- [x] 1.4 按 Design 1.1 在独立外置目录完成 Yahoo 与 AKShare/东方财富各一次有界技术尝试，先锁定版本/请求范围，执行前核对请求次数、响应读取上限和零重试；不能满足预算则记录 NOT_RUN。保存实际命令、trial_id、参数差异、状态/行数/时间/响应 hash 或具体失败，更新 `docs/data/us-equity-sources.md` 的脱敏结果。验收目标是如实可审计的尝试及预算/隔离，不强制数据成功；不得伪造 AUTHORIZED、写入产品缓存或启动 Council，不修改产品依赖/代理/原生权限，不运行全量 Gate。

2026-09-10 Task 1.4 证据：`docs/data/us-equity-sources.md` 最新技术试拉节。Yahoo 一次匿名初始化请求 404 即停，未到行情端点；AKShare/东方财富一次有界请求返回 7 条 MSFT 日线。外置目录 `/private/tmp/stock-agent-source-trial.JhvGbZ`，脚本及结果完整 hash 见来源记录。试拉与正式准入分开，Task 1.1、5.2–5.5 不变；未运行 Council 或更换产品行情源。

- [x] 1.5 在既有 live 数据目录实现 NASDAQ 股票池有界分页、去重、外置缓存和版本化快照；测试默认部分结果、空页/重复/总数变化、预算/拒绝停止、观察时间与 source_asof 区分、ADR/未知身份及符号映射冲突。满足 Design 1.3 准入后保存一次有界真实目录采集的页面 hash 与完成度，未覆盖全池不得宣称完整，不增加投资排序或全市场行情下载。

## 2. 真实只读采集与冻结证据

阶段进度：Task 2.2 已实现离线 submissions/companyfacts 解析及 8 项合成测试，记录见 `docs/data/sec-parser-progress.md`。尚缺真实采集、分页及披露原文部分，不勾选完成。

2026-09-10 续进：Task 2.2/2.4 增加限定 SEC GET、外置追加缓存、有限重试/预算和采集→解析→原文保存接缝；18 项合成测试通过。实际范围与剩余缺口见 `docs/data/sec-collection-progress.md`，未发起真实网络或模型请求，任务仍不提前勾选。

2026-09-10 后续：历史分页已接入，文本提取新增字符定位/原文 hash/预算及缺口标记，25 项聚焦测试通过。版本与适用边界追加于上述记录；财务可比计算、披露选择/附件和完整 live 接入未完成，Task 2.2/2.3 保持未勾选。

- [x] 2.1 复用既有 market/collection/security_metadata 与 Yahoo、东方财富有界适配，接入主行情及备用的证券身份和 SEC 封面绑定；验证 ticker/交易所/USD/普通股/股类、原文字节血缘、未完成时段、复权/缺失 actions 与身份冲突，不以 NASDAQ 目录行或样例前缀替代身份核实。
- [x] 2.2 在 `product/mcp/live/sec.py` 实现 CIK/submissions/companyfacts 和指定 10-K/10-Q/8-K 原文读取，保存 accession、公开时点、期间/单位及原文定位；用响应样例验证 YTD/单季、年度重复、修订、不同单位和缺指标不填零，数值与来源关联真实一致。
- [x] 2.3 实现可追溯披露片段提取及有限财务比较，使用固定章节/长度预算并记录截断；以业务/风险/管理层讨论样例、恶意指令文本和可比/不可比期间测试确认不引入投资判断，派生计算携带公式、父证据和版本。
- [x] 2.4 复用外置追加缓存与 transport 预算，按 provider/client/adapter/version/口径独立键；零网络验证发送前范围限制、读取限长、真实请求计数、401/403/429 停止、有限暂时故障重试、去重/原获取时间和隐私，不移植试拉全局 monkeypatch。
- [x] 2.5 在主备采集→来源选择冻结→既有 PIT Gate 验证唯一 cutoff、时效及交易时段；覆盖未来公开/获取、过期、非法元数据、父证据排除及切源不能掩盖完整性错误，专业输入和估值使用同一已选合格价格，不改 fixture 时间政策。

- [ ] 2.6 在现有 collection 增加 canonical 受控来源选择：主源优先，仅可用性故障一次备用；401/403/429/认证挑战/身份或完整性异常不得切源。逐证券冻结 SourceSelection、失败链、原文 hash 和 Evidence，报告展示实际来源/回退原因。以零 LLM 正负测试覆盖成功、不允许回退、两源失败、缓存及禁止字段/日期拼接；实际主行情调用与单股验收合并，不为备用增加模型运行。

## 3. 复用 Council、宿主入口与风险接缝

2026-09-10 用户已批准 Design 2.1 的限定调整，替代下文历史“待批准”状态。Task 3.2/3.5/5.1 的受影响增量需验证真实 SubagentStart 上下文交付、回执、底层绑定与 fail-closed；既有完成部分不扩张为新版已通过。5.2 必须包含新交付的实际加载与执行证明；仍不提前关闭 2.6、5.2–5.5。本批准不是最终完成批准。

2026-09-10 续进证据：`docs/data/live-contracts-progress.md` 记录 68 项 live 离线测试、依赖隔离与完整被测文件 hash。Task 1.3 与 2.2 按各自输入/采集解析接缝验收完成；不代表 Task 5.2/5.3 真实读取或 LLM 研究通过。其余 PIT、profile、输入、工具与 Risk helper 尚待完整运行链路接入，不提前勾选。历史阶段记录按时间保留，以此记录说明已补齐的局部缺口。

- [x] 3.1 更新既有 live profile、prepare/invocation/discovery/Trace 和底层重验，锁定目录、路由策略、实际所选 provider/client/adapter、Schema、Agent、Skill、MCP、模型和 Risk Policy；验证缺失选择、错标来源、试拉包、锁漂移拒绝，历史包保留原锁不联网；双状态/批准记录 hash 随快照和 Trace 锁定并底层重验，采集/请求边界/Gate 不允许各自放宽准入。
- [x] 3.2 复用 Gate-scoped MCP 核心实现 live 只读查询/计算及实际工具绑定，必要时调整现有产品 Skill/Agent 指令，保持 Analyst/Skeptic 独立并行、CIO 只收验证报告；用跨 run/invocation、未知/排除 ID、原文注入样例测试权限边界，并证明专业查询不会再次访问 Provider。
- [x] 3.3 在既有输入与 Risk 快照接缝使用 Gate 合格 close_price 构造完整组合估值；用一股/三股、缺价、手填旧价、成本价、未来价测试，核对组合总值、仓位和 Evidence hash，确认不使用被排除价格或对剩余持仓重新归一化，不更改 Risk 硬约束。
- [x] 3.4 将研究目标从 positions[0] 改为显式 focus_security_id，并实现共享快照的 1→3 单证券子运行/批次清单；用持仓重排、重复 run_id、子任务失败与汇总测试确认目标不串股、组合上下文一致、逐股 Risk 完整，汇总不引入新投资判断或联合交易计划。
- [x] 3.5 扩展现有 `scripts/run-product-smoke.sh` 的明确 live profile/外置 portfolio 参数，复用当前 launcher 和代理适配；确定性接缝测试覆盖旧 normal/--prepared-run 兼容、自检零隐式启动、外置路径、live 部分失败/终态非零传播。禁止新增 sandbox、probe、代理逻辑或独立 LLM 后端。

## 4. 中文报告与实际 Eval

2026-09-10 阶段二：`docs/data/live-offline-runtime-progress.md` 记录 83 项 live 离线测试、91 项受影响旧接缝测试及严格校验，附 61 个增量文件完整 hash。Task 3.3 的估值→输入→Risk 接缝已接入并验证；其余部分实现不提前勾选，真实单股/三股与更新资源加载、实际语义评分仍无替代证据。Yahoo 按用户最新明确答复保持暂停。

- [x] 4.1 在已有专业/CIO 结构及报告渲染中补齐 live 事实、推理、反证、持仓理由与可观察条件，live 允许动作限定既有 HOLD/TRIM/EXIT/NO_TRADE；用结构/渲染一致性测试验证每项事实能回溯 source_id/as_of/published_at 语义/retrieved_at，未知引用失败、NO_TRADE 两字段必须 null，不在模板内生成判断。
- [x] 4.2 扩展现有 native/runtime Eval 的 live profile 检查与 rubric 配置，区分运行安全与研究质量；用有具体研究的 NO_TRADE、空泛 NO_TRADE、有据 HOLD/TRIM、悬空引用、Risk 缺失等样例测试评分输入绑定和 fail-closed。语义质量由既有评分作业基于真实产物判定，不以字数、固定 action/confidence 或 Python 投资规则取代。
- [x] 4.3 更新产品运行、来源与合成输入说明为 NASDAQ 股票池＋yfinance 主行情＋AKShare/东方财富受控备用＋SEC；明确回退条件、目录完成度、非实时/权限/隐私和宿主用法，旧唯一行情方案标历史，验证新版样例 Schema。本项因双状态调整重新打开：说明个人批准不等于上游许可，中文报告展示 UNVERIFIED 与限制，新版样例不伪造授权。

2026-09-10 连续推进：新版数据契约、独立有界传输/缓存、价格规范化、冻结→PIT→估值已补离线接缝，59 项受影响测试通过；当前源码与范围记录见 `docs/data/eastmoney-adapter-progress.md` 第二阶段。Task 4.3 文档及合成输入验证完成。身份映射和完整 collection/profile/Trace 接通仍缺同源身份依据，不以局部通过勾选 1.3/2.1/2.4/2.5/3.1/5.1。已提出追加有界身份技术验证的范围申请，尚未执行；正式准入门禁不变。

## 5. 限定集成验收与完成批准

2026-09-10 阶段三：`docs/data/live-integration-progress.md` 及 `live-sdk-contract.md` 记录集合采集→冻结→批次准备/宿主调用、来源版本锁、身份原文重验及中文估值报告接缝；101 项 live、131 项共享/旧入口测试通过。对应实施任务按表关闭，来源准入与真实加载/研究没有由合成测试替代；Task 4.2、5.1–5.5 仍未完成，Yahoo 继续暂停。

2026-09-10 离线收尾：`reviews/development/us-equity-live-advisory-slice-offline-verification.md` 及对应实际测试结果 JSON 归集 Task 4.2/5.1。新增 4 项 Eval 接缝测试，105 项 live 测试通过；73 文件旧 hash 全部一致，复用相同源码/依赖下的 131 项兼容测试。评分替身只证明绑定/失败传播，不是真实语义验收；Task 1.1、5.2–5.5 保持未完成，不启动 Yahoo 或模型。

- [x] 5.1 按 Design 1.2、7 归集源码/配置/输入/输出 hash 与旧证据适用表，执行目录/主备策略及至 MCP、Gate/估值/Risk、宿主、批次、报告/Eval 的受影响确定性接缝和 OpenSpec strict validate；复用未变证据，不重跑全量 Gate/Regression/Calibration/Ablation/Promotion。记录 NASDAQ 默认 20 行仅技术观察，不是全池验收；未测试身份修改不继承旧 PASS。本轮只补双状态准入、实际请求/Gate 接缝、锁及报告的受影响测试；有效批准不得改变 401/403/429/预算/身份/PIT/Risk 拒绝行为。
- [ ] 5.2 满足 Design 1.3 双状态准入且受影响接缝通过后，经现有宿主入口运行一次真实单股采集＋Council，使用合成持仓或用户明确选择的外置真实持仓；保存采集/缓存/PIT、加载/独立 Agent/CIO/Risk 事件、decision/report/trace/native Eval，并通过既有 Runtime Eval 作业完成有输入输出 hash 的语义评分，按 Design 7 验证研究质量。网络或质量失败只报告具体原因，不自动重复付费运行。
- [ ] 5.3 单股通过后，在最终候选锁下经同一宿主入口运行一次三股批次并对三个子运行分别执行实际 Eval 与语义评分；核对唯一 IDs、共同 cutoff/完整组合、目标/来源/价格、风险血缘、逐股研究质量与批次状态。保存非敏感命令/标识/hash；数据缓存可复用但不得把旧研究冒充本次执行，三股全部合格才勾选。
- [ ] 5.4 完成一次独立只读差异复核，读取本次规格、实现及上述实际事件/底层 hash，验证 1→3 链路与非空泛研究、证据复用边界和隐私；输出明确 PASS/FAIL 与不足项。缺口只提出针对性补证，不自行重跑正常样本或全套 Gate；不把本次完成写成 Promotion PASS。
- [ ] 5.5 向用户提交限定完成摘要与证据标识，取得明确人工完成批准后保存批准记录并勾选；未获批准不归档、不提交、不推送，不改生产指针，ISOLATION 继续 UNVERIFIED。

### 2026-09-10 真实运行修复记录（不改变完成状态）

2026-09-10 已批准的上下文交付修订已实施：SubagentStart 注入完整冻结包，回执及底层绑定在 MCP/CIO/执行证明/完成检查重验，不声称能阻止启动；PIT/Risk/引用校验不放宽。120项受影响确定性测试（含13项新增接缝）、strict validate与插件校验通过；见 `reviews/development/live-start-context-fix.md` / `live-start-context-tests.json`。获批一次真实单股 `live-ea56970a-e572-4c6d-8708-86d372bd3546` 已失败：真实数据冻结成功，短票据被 PreToolUse 逐字比较拒绝，未到 SubagentStart/CIO/Risk/Eval；见 `live-start-context-smoke-result.json`。不追加付费运行，2.6、5.2–5.5保持未完成。下列历史“待批准/未实施”是当时状态，由本记录限定更新而不改写历史证据。

2026-09-10 恢复 apply：修复 SEC 拆分标题/正文引用截断、重复同值披露的比较误判，以及 prepare-cio 缺依赖/上下文错误的失败终态。最终 90 项受影响确定性测试通过，原真实 SEC 文档 hash 验证与离线重解析通过；见 `reviews/development/live-research-materials-fix.md` / `.json`。未修改历史包或插件缓存，未调用模型；真实派发前 Hook 覆盖仍无证明，SubagentStart 冻结输入注入替代方案待用户批准、未实施。2.6、5.2–5.5 保持未完成，不以本轮离线材料证明替代研究验收。

最新：本轮 Hook matcher/Schema 提示/错误传播 61 项确定性测试通过；一次真实单股 `live-1e90843c-71d3-4fb8-9747-afd6c0420f4e` 中双 Agent 成功查询且原始报告通过只读 Validator，但主线程 prepare-cio 使用系统 Python，缺少 exchange-calendars，未到 CIO/Risk/Eval。PreToolUse 实际只记录非派发工具，spawn 路径缺口仍未关闭。随后仅修复生成命令绑定宿主解释器，33 项确定性接缝和 strict validate 通过，不追加真实运行。证据见 `reviews/development/live-dispatch-routing-fix.md` 及其三个 JSON；区分真实运行快照与运行后修复，当前安装缓存尚不含后者。2.6、5.2–5.5 保持未完成，无归档/提交/推送。

见 `reviews/development/live-sec-and-plugin-fixes.md` 及配套 JSON。HTTPS、SEC 目录与普通股身份解析、安装包批准资源及插件缓存已修复；受影响确定性测试和真实安装包 query 通过。获授权的补跑中双专业 Agent 均成功取得 live Evidence，但 Analyst 格式修复改动原有陈述，被 `FORMAT_REPAIR_ADDED_FACT_CONTENT` 拒绝，未进入 CIO/Risk。Task 5.2、5.3 保持未完成；不以数据成功或安全拒绝替代研究验收，不自动重复付费运行。

2026-09-10 后续定点修复：明确按本次 Schema 输出、一次格式修复只改指定结构并保留所有其他文本/数值，Validator 未放宽。29 项接缝测试、插件校验与 OpenSpec strict validate 通过，见 `reviews/development/live-format-repair-fix.md` 及两个配套 JSON。用户批准的一次真实重试 `live-4b6a421c-d4d0-4b24-af8a-eaf34513a1cd` 在 Specialist 阶段因 `INVOCATION_ID_MISMATCH` 停止：Analyst 身份错误且未成功查询，Skeptic 成功取得真实证据。本次未触发格式修复，不能称为该路径的真实成功证明；没有 CIO/Risk/decision/report/Eval。2.6、5.2–5.5 保持未完成，未追加模型运行。

2026-09-10 派发接缝修复：从现有冻结 Invocation/Input/Prompt/Schema 确定性生成完整消息，现有 PreToolUse 在派发前核对消息、角色任务及隔离参数，错误或缺失明确拒绝并只记 hash，不静默改写。57 项受影响确定性测试及 strict validate 通过；只读核对历史 live 输入中两个角色各 96 个允许 ID 原样保留，旧运行包未改写。见 `reviews/development/live-specialist-dispatch-fix.md` 与 tests JSON。尚未刷新插件缓存或真实重跑，不关闭 2.6、5.2–5.5，不以单元测试替代实际 Codex 加载与研究质量证明。

2026-09-10 获批的一次新派发版本 Smoke：插件更新为 `0.3.0+codex.20260910123014`，运行 `live-60dfbf24-2090-4058-b29b-6e49ba6afcb5`。两份输出 Invocation ID 一致，但 confidence 均为字符串 LOW，实际以 `INVALID_CONFIDENCE` 失败；没有 CIO/Risk/decision/report/Eval。新生命周期 Hook 1.4.0 有事件，PreToolUse 派发记录缺失，不能认定新检查真实生效。见 `reviews/development/live-specialist-dispatch-smoke.md` 与 result JSON；已保存完整源码快照与底层 hash，未追加运行，2.6、5.2–5.5 保持未完成。
