## 1. 三源范围与接缝

- [x] 1.1 盘点已归档 expand-free-data-holding-research 的延期证据、现有 SEC/Yahoo 实现及用户差异，交付文件归属与缺口映射；核对不改归档任务和旧 canonical 包。
- [x] 1.2 核对 SEC、Yahoo、Moomoo SG OpenD 的当前来源说明、未开户登录规则、Quote 权限与自动化限制，记录 URL、日期、OpenD/SDK 版本、数据用途、预算和准入结论；验证文档说明不代替真实连通性或 entitlement。
- [x] 1.3 定义逐数据集三源计划及显式回退，交付来源矩阵；用资金流无替代、OpenD 与 SEC/Yahoo 隔离和单次回退 fixture 验证。
- [x] 1.4 核对基础 provider 枚举及研究补充快照接缝，交付 schema/模块影响清单；证明计划不把 Moomoo SG 直接塞入旧基础契约。

## 2. 契约与安全获取

- [x] 2.1 更新能力矩阵与批次契约，覆盖区域、证券、数据集、字段、OpenD/SDK/API 版本及 OpenD 专用失败状态；以未尝试、部分可用、OpenD 不可达和来源独立失败测试验证。
- [x] 2.2 定义并验证版本化 Moomoo Quote API allowlist，锁定 loopback、方法、参数、证券市场、响应、只读语义和预算；用远程 host、任意方法、Trade Context、账户字段和额外参数负例验证调用前拒绝。
- [x] 2.3 实现 OpenD 认证隔离，项目不接收 Cookie/Token/密码/Keychain/交易解锁信息；以 Quote 未登录、停止 OpenD、认证材料扫描和 SEC/Yahoo 独立运行测试验证。
- [x] 2.4 实现本机 OpenD readiness/version probe，只读取全局状态与 Quote 登录信息；用 App 已登录但 OpenD 不可达、版本不足和 Quote 未登录 fixture 验证不误判。
- [x] 2.5 实现有界 OpenD Quote client/缓存，落实 loopback、分页、请求、频率与时间预算及方法级熔断；以超时、限频、字段漂移和错证券测试验证其他来源不受影响。
- [x] 2.6 实现 OpenD 响应隔离、确定性序列化与可提交内容扫描；用认证/账户秘密、公开 SEC 申报人身份和正常 Quote DataFrame 对照 fixture 验证。

## 3. SEC 原始披露

- [x] 3.1 复用公共 EDGAR submissions/XBRL/Archives 获取与标识限速，形成一只普通股真实基础披露 Evidence；保存请求版本、原文 hash、证券与公开时间并通过契约检查。
- [x] 3.2 实现/补齐 13F 管理人两期信息表、修订、单位、分页、证券映射与覆盖集合；以错 CUSIP、部分管理人、修订和拆股 fixture 验证不可伪装全市场。
- [x] 3.3 实现/补齐 Form 3/4/5 日期、交易代码、直接/间接及衍生品字段；用授予/行权/转让/市场交易测试验证语义保留。
- [x] 3.4 在有限预算内取得真实两期机构与内部人样本或逐项实证限制；核对 raw hash、报告期、公开时间、覆盖和 Evidence 引用，未满足条件不标 RESEARCH_INPUT_VALIDATED。

## 4. Yahoo 行情与期权

- [x] 4.1 复用 Yahoo 行情、OHLCV、公司行动与基准路径，验证一只普通股真实快照的币种、时区、复权及来源延迟；保存基线 Evidence 和原始 hash。
- [x] 4.2 独立验证 Yahoo 期权正常读取能力，记录静态/动态、到期日及字段覆盖和失败原因；不因基础行情成功标记期权成功。
- [x] 4.3 补齐期权标准化，区分报价/OI/last trade 的时间与缺失 Greeks；以过期、倒挂价差、乘数、缺字段和跨源不同步 fixture 验证限定用途。
- [x] 4.4 在已批准预算内采集一个标的多个到期日/行权价，或记录实际受限证据；若回退 Moomoo SG，验证显式来源选择与快照分离，不静默拼接。

## 5. Moomoo Singapore 可行性与数据

- [x] 5.1 核实 Moomoo SG 官方 OpenD/SDK 入口、服务区域、证券市场、未开户登录和 Quote 权限；记录官方版本与方法清单，交付不含秘密的 `OPEND_QUOTE_FEASIBLE` 或准确限制证据。
- [x] 5.2 连接用户已登录的本机 OpenD，以 `get_global_state` 和一个批准的 `US.AAPL` 研究方法证明 Quote readiness；记录 OpenD/SDK 版本、行情登录、entitlement 和响应 hash，不读取任何登录秘密。
- [x] 5.3 从 Runtime 与文档移除 Cookie/Charles/私有 HTTP 主路线，保留兼容期代码仅在确认无调用后删除；以代码搜索、依赖图和负例证明 Moomoo 只经官方 loopback OpenD。
- [x] 5.4 OpenD 路线通过后将官方 `get_capital_flow` 响应绑定供应商资金流标准化，保存分类、币种、单位、期间、定义和时点；用缺时点、缺单位与错误方向推断负例验证。
- [x] 5.5 对一个真实普通股取得资金流 Evidence；受限则记录原因，并在已验证能力内选择期权/机构/研报数据集完成至少一项 Moomoo SG 真实纵向链路，不能以证券身份查询替代研究数据。
- [x] 5.6 实现 Moomoo 官方股东/机构/内部人及可得期权 Quote API 适配，验证原始来源声明、单期/两期、分页、时点及二级语义；与 SEC/Yahoo 冲突并列保存。
- [x] 5.7 实现 Moomoo 官方分析师一致预期、评级与 Morningstar 研究资料适配及 Yahoo 候选补充，真实取得至多一个合法研究内容样本或准确 entitlement/字段限制；以评级摘要/观点/转载/正文 fixture 验证分级，单篇不标对比完成。

## 6. 冻结证据与研究接入

本组在下述 6B 背景切片与第 3–5 组各自数据就绪后接入；6B 可与 SEC/Yahoo 数据准备顺序推进，不等待 Moomoo SG 会话成功。

- [x] 6.1 将组合补充快照接入现有 Evidence Gate，验证 source_id/as_of/retrieved_at、公开版本、证券、raw hash 与批次闭合；用晚披露 13F、未来快照和缺时间负例验证。
- [x] 6.2 暴露按证券/数据集/cutoff/batch 查询的冻结 MCP，验证拒绝任意网络、秘密、Bootstrap 和隔离区访问；现有来源查询回归通过。
- [x] 6.3 映射既有 ownership-disclosure、options-market-structure、research-report-analysis 及适用研究 Skill，交付 Input/Tool/Skill/Output/Eval 对照；验证采集层不生成投资判断。
- [x] 6.4 用同一标的与明确 cutoff 形成三源研究包，核对跨源冲突、时间差及字段覆盖；历史 canonical 包保持不变，新包建立明确责任映射。

## 6B. 个股背景资料补齐

- [x] 6B.1 按 Design 对照矩阵核实当前采集/Schema 与参考项目固定 commit，交付十组资料的已有、部分和新增清单；验证不将方法存在当数据可用，不引入参考项目的评分或猜测默认值。
- [x] 6B.2 定义 CompanyBackgroundSnapshot 及同源中文展示，绑定证券、cutoff、批次、十组覆盖/Evidence/缺口；用缺身份、全未知、错证券、缺时间和悬空引用验证基础验收不能误过。
- [x] 6B.3 扩展三源公司档案映射，保留法定名/CIK、行业体系、主营业务、总部、官网定位和员工时点；用分类冲突和当前资料冒充历史负例验证来源保留。
- [x] 6B.4 有界扩展 SEC 分部表格/iXBRL/XBRL context 获取与解析，保留 axis/member、抵销、期间和重分类；用合计不能代分部、跨期重分类与原文截断 fixture 验证，并取得至少一个真实分部样本或实证限制。
- [x] 6B.5 增加 SEC 必需治理表单/章节的精确白名单和解析契约，提取公开管理层、控制权、关联交易及资本配置；以任免生效日、回购授权未执行、公开人名与私人账号区别测试验证。
- [x] 6B.6 扩展财务白名单与选择窗口，目标 3 财年/8 独立季度，补齐资产负债权益、营运资本、R&D、利息和分红回购可得字段；用重复申报、累计拆季、重述、短历史及不支持 taxonomy 测试验证实际覆盖。
- [x] 6B.7 为冻结披露上的业务/KPI/关系/指引候选提取配置既有 Company Analyst 接缝，所有候选带原文 Evidence 与定位，确定性核对身份/时间/引用；用匿名客户、同行非供应商、截断文档和无引文主张负例验证，不新增 Agent 或 RAG 平台。
- [x] 6B.8 实现 Yahoo/Moomoo SG 的业绩日历、预测/修订与评级可得字段契约，SEC 实际/指引独立建模；用错财政期、forward EPS、GAAP 差异、未知 vintage、零/负基数验证不能生成虚假预期差。
- [x] 6B.9 加入三源内事件/新闻/可得电话会定位和空头股本背景；以转载重复、估计日期、仅标题、第四方链接、short volume 与 interest 混淆验证受限与语义，无借券费率不得推算。
- [x] 6B.10 将十组背景资料通过 sidecar/Gate/MCP 接入 company-research 与现有相关 Skill；确定性验证 JSON/中文同源、字段级限制与历史隔离，真实专业消费并入 7.3 的既定检查而不额外启动模型批次。

## 7. 有限验收与收尾

- [x] 7.1 交付真实三源能力矩阵与执行记录，分别证明 SEC/Yahoo 接入和至少一个 Moomoo SG 研究数据集 Capture → Normalize → PIT → MCP；任一来源缺失则整体保持未完成。
- [x] 7.2 证明至少一个延期核心增量：动态期权、供应商资金流或可比两期机构持仓；核对每组其余目标有成功/部分/实际限制证据，不用基本行情或候选摘要抵扣。
- [x] 7.2B 交付同一真实标的的基础背景闭环与十组覆盖矩阵，至少一个新增背景类别有真实 Evidence；核对能回答主营业务/收入构成/财务基线/重要依赖和未知项，未补齐类别明确受限，不能只新增 Schema 或包装旧数据。
- [x] 7.3 在显式实施与宿主授权下执行至多一次 GPT-5.6 Terra 专项消费检查，输入同时包含新背景包与原核心增量，生成中文/JSON 研究输出；验证背景引用、事实/预测/观点分离、覆盖缺口及三源语义，不启动 Skeptic/CIO/Risk 或完整 Council；检查失败保留真实结果，不自动追加批次。
- 首次授权运行因输入包纳入检索时刻之后的 Moomoo 分钟桶而判定无效；原输出和失败原因保留。用户再次明确授权后的 v2 replacement 已通过，记录见 `reviews/development/capture-futu-client-research-data-terra-consumption.json`。
- [x] 7.4 运行受影响契约、OpenD Quote-only 边界、认证隔离、来源路由、标准化、PIT、MCP 聚焦测试和 OpenSpec strict validate，保存实际结果；未运行不标 PASS，不隐式触发 Replay/Eval/Regression/Promotion。
- 实际命令、输出 hash、真实三源包 hash、敏感信息扫描及被中止的过宽 Promotion/Eval 测试记录见 `reviews/development/capture-futu-client-research-data-validation.json`。
- [x] 7.5 独立 Reviewer 只读核对差异、三源真实证据、核心增量及敏感信息扫描，给出逐项结论；缺证据提出最小补跑需求，不自行启动产品。
- 首轮 Reviewer 为 `CHANGE_REVIEW: FAIL`；修复 PIT、契约、来源路由、分部解析、Gate scope、原子 readiness 与验证持久化后，同一 Reviewer 对最新差异和 v2 冻结包给出 `CHANGE_REVIEW: PASS`。完整结论见 `reviews/development/capture-futu-client-research-data-independent-review.md`。
- [x] 7.6 更新中文操作与收尾说明，列出 OpenD 安装/登录由用户管理、loopback 与 Quote-only 范围、真实支持方法、权限限制、停止 OpenD、回滚和归档 Change 映射；取得人工完成批准前不归档/提交/推送，全部受限不得申请完成。

## 8. 截图持仓系统流程收尾

2026-09-17 收口：v3/v8 及 ALB v7–v9 的失败/中止证据均保留，不再作为成功依据。新 v5 冻结数据已在官方宿主入口先通过 ALB 单股验证，随后通过 ALB/MRVL/WOLF 三股完整并发批次；3/3 中文/JSON 报告通过 Schema、PIT、Evidence Closure 与持久化校验，并均实际引用 SEC、Yahoo 与 Moomoo SG 证据。当前只剩最新差异的独立只读复核及人工完成批准。

- [x] 8.1 在普通股父线程增加 run-scoped `Stop` Hook 终态屏障和最小化审计，按冻结任务、允许派发、同一父会话及 invocation binding 重算缺失终态；测试验证启动事件、非终态消息、自报计数、跨会话和错误 invocation 均不能放行。
- [x] 8.2 将 Stop Hook 接入普通股 launcher 命令与 environment manifest，保持批次超时和既有 finalizer 权威；测试验证缺失终态阻止父线程结束、终态齐全允许归集且 Hook 不生成或修补报告。
- [x] 8.3 更新父调度 Prompt 与中文运行说明，明确 `wait` 可因非终态活动返回、必须持续等待真实终态；验证不以固定 wait 次数或父线程完成计数作为成功条件。
- [x] 8.4 补齐可复现的受影响验证记录，区分已通过的 93 项、macOS 路径错误和扩展检查错误；在正确锁定环境核实相关失败，未证明与本次修改无关前不一概称旧错误。验证通过不代替真实消费。
  - 在锁定 venv 与真实 `/private/tmp` 下通过 234 项受影响测试；`compileall`、`git diff --check`、OpenSpec strict validate 均通过。旧 93/231 项口径已由当前记录取代，详见验证 JSON。
- [x] 8.5 盘点三只截图持仓的三源补充包、十组背景、核心增量、证券和 cutoff，先确定可复用输入及必须采集项；无补充包的 v3 仅用于旧故障诊断，不能充当三源验收输入。
  - 旧 v3/v8 均无持仓补充包；新 v5 在同一 cutoff 下冻结 ALB/MRVL/WOLF 三份独立包，覆盖八组背景并明确保留治理、关系缺口，每只均含 5 条 Moomoo `vendor_money_flow`。
- [x] 8.6 从 v3/v4/v8 已有证据定位子任务最早失败步骤，核对上下文、MCP、模型错误及报告捕获。证据不足时明确最早未证实边界、具体假设和所需信号，优先确定性检查，必要时在现有宿主入口补最小诊断并声明运行预算/停止条件；形成有证据支持的最小修复或明确外部阻塞，不无限等待、重复批次或扩建监控平台。
  - v3/v4 是父线程提前结束；v8 的 Stop Hook 已阻止提前完成，但在 900 秒单项预算前被人工中止。后续实证还暴露大包上下文、运行中 dispatch 版本漂移、短 wait 和 FACT 期间字符串血缘等具体接缝。最小修复包括排除后续技术日线并压缩 catalog、锁定长等待与运行中控制、保留 ISO 期间字符串，以及将拒收报告正确归类为报告集不完整。ALB v10 与三股批次已证明该消费阻塞解除。
- [x] 8.7 在既有正式宿主持仓入口接通有界采集、逐股补充包、冻结和研究，不要求用户手工拼包；一起闭合多包保存、preparation 索引、source bundle 重建校验、逐股请求/MCP 查询和报告引用，兼容旧单股包读取。验证多包不覆盖、不串证券、同 cutoff、缺包拒绝；Moomoo 受限继续合格 SEC/Yahoo 研究并记录缺口，但三源验收未通过。复用现有模块，不硬编码验收证券。
  - 官方宿主入口已对同一 Handoff 自动准备 v5 三源包并生成 3 份逐股请求；完整批次 3/3 报告持久化成功。每份报告均引用 SEC、Yahoo 与 Moomoo SG `vendor_money_flow`，没有串证券或手工拼包。
- [x] 8.8 按 8.5 的缺口在三源和既有预算内准备实际持仓资料；当前新采集建立新 cutoff/run_id，不回填 v3。先完成确定性来源、证券、PIT、包重建和 MCP 可查询检查，再启动模型。
  - `capture-futu-client-research-data-20260917-v5` 已通过来源、证券、PIT、多包索引、source bundle 重建与补充/通用 MCP 查询；后续在用户明确授权下完成 ALB 单股与三股正式模型消费。
- [x] 8.9 按 8.6 的已证实原因完成最小消费修复与聚焦检查；经正式宿主持仓入口先验证一只实际持仓，再完成 ALB/MRVL/WOLF 报告集合。验收包含从确认 Handoff 自动准备补充数据的真实证据、逐股基础背景/缺口、三份合法中文/JSON 报告，以及至少一只持仓对新增背景、核心增量和 Moomoo 研究数据的真实查询/引用；保留 ETF/期权缺口，不以手工拼包或 Hook 数量替代。
  - ALB v10 单股先行通过；随后三股批次 `completed=3/expected=3`、`parallel_overlap=true`、`all_reports_valid=true`。ALB/MRVL/WOLF 均引用 Yahoo 价格、SEC 披露与 Moomoo SG 资金流；MRVL 额外引用 `identity_profile`/`earnings_guidance`，WOLF 引用 `business_segments`。ETF 与 SOXL 期权仍保留 `CAPABILITY_GAP`。
- [x] 8.10 更新当前验收矩阵与独立只读复核，限定旧 AAPL PASS 的适用范围，保留失败/中止记录；正式入口、三份报告、新增数据消费及受影响检查全部满足后申请人工完成批准，进入既有归档流程。不追加十组增强数据全覆盖、完整 Council、新 Agent、通用平台或发布级评测门槛，不归档未完成需求。
  - 最新验收矩阵已持久化；独立 Reviewer 对紧凑上下文、等待/终态门禁、三股正式产物、PIT/引用闭合、安全与文档一致性给出 `CHANGE_REVIEW: PASS`，无 blocker。该 PASS 不替代用户的人工完成批准，未归档、未提交、未推送。
