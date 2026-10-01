# 普通股持仓多维研究

本文说明 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 产品阶段。它承接用户已经确认的 `PortfolioHandoff v3`，自动准备免费公开资料，并为每只普通股生成可供后续 Independent Skeptic 直接读取的结构化研究包。它不是组合决策阶段，不输出买卖动作，也不启动 CIO、Risk Engine 或真实交易。

## 运行链路

```text
PortfolioHandoff v3
→ 只读行情、SEC、NASDAQ、宏观、披露及期权资料采集
→ point-in-time Evidence Gate
→ 资料准备：公开研报发现 / 同行候选选择
→ 正文取得与同行有限采集、冻结、再次 Gate
→ 多维专业研究（有界并行）
→ HoldingResearchBundle + 中文报告
```

用户只提供已确认持仓，不需要制作 Evidence。系统仍保留完整组合，但本阶段只研究普通股；ETF、上市期权及账户级项目在覆盖表中保留为当前能力缺口，不能被静默删除。

## Agent、Skill 与工具边界

- `runtime_company_analyst`：公司基本面深化、公司事件和公司研报分析；复用已有公司研究报告，不重复生成同一份基础报告。
- `runtime_market_catalyst`：技术结构、行业同行、宏观环境、市场状态、所有权披露及期权市场结构。`MACRO_CONTEXT` 与 `MARKET_STATE` 是两个独立 capability、两个独立 invocation；前者解释利率、通胀、经济活动和政策传导，后者解释基准、板块、跨资产、波动/信用代理与短期市场事件。每个 invocation 只执行一个 capability。
- Skills：定义各维度应回答的问题、证据分层、反向条件和表达边界。
- 只读工具：获取与标准化公开资料、计算指标、冻结正文、核实同行身份；不得形成投资评级。
- Python：执行 PIT、Schema、引用闭合、依赖调度、哈希、渲染和存储；不得代替 LLM 选择 Thesis、同行赢家或交易动作。

## 资料准备与正式研究分离

公开研报和同行比较采用两步流程：

1. 资料准备 invocation 允许 Company Analyst 调用 `research_search`、`research_fetch`，允许 Market Catalyst 从冻结的 NASDAQ 候选池选择有理由的同行候选。
2. 工具核实并冻结正文或同行资料，再执行 PIT Gate。正式研究 invocation 只读取 Gate 合格资料，不继承搜索权限。

搜索标题和摘要始终是 `LEAD_ONLY`，不能写成已读研报。独立正文以 `BODY_VERIFIED` 和真实 documents 引用进入报告；另外，已过 Gate 的 `LICENSED_API_CONTENT` 许可文本章节可按 Evidence ID、章节和原始响应 hash 读取、引用，不能冒充完整独立研报或伪造 documents。缺少正文 API key 等配置问题标记为 `BLOCKED_CONFIGURATION`；实际搜索/正文路径受限标记为 `SOURCE_LIMITED`。两者都必须引用本 invocation 的真实尝试产物，不能由模型自行宣称。独立正文路径的阻断不自动否定其他已核实的许可章节，但报告必须保留来源限制。来源分层已有零模型及真实 Agent 读取证明；最新第八批研报金额和引用相关性内容复核通过，但其它维度缺陷仍阻断整批验收，不能借研报单维PASS宣布Change完成。

同行目录只用于限制候选范围与请求预算。`candidate_status=UNVERIFIED` 不是同行事实；只有 `materialization_status=FROZEN` 且对应 Evidence 已进入正式 Gate，Agent 才能进行实质比较。

## 并发和依赖

默认最多三个活跃 Subagent。技术、基本面、宏观和市场等独立任务可并行；正式研报分析等待正文准备与公司基础报告，正式同行比较等待候选选择、有限采集、Gate 与公司基础报告。某一资料路径失败只阻塞真实依赖项，不能阻止其他维度运行。共享 `MACRO_CONTEXT` 与 `MARKET_STATE` 各自每批只执行一次，不能再用一份历史 `MACRO_MARKET` 报告冒充两个维度均已覆盖。

## 输出

新运行的每个维度输出 `ResearchDimensionReport/2.0.0`，至少包含：

- 研究身份、Agent/Skill/模型及输入绑定；
- 具体问题、Claim、原始 Evidence、计算、假设和反向观察条件；
- 研报正文元数据及其对已有主张的支持、挑战、修订或无新增信息；
- 可比性、时效、来源和资料缺口；
- `COMPLETE`、`LOW_CONFIDENCE`、`INSUFFICIENT_EVIDENCE`、`SOURCE_LIMITED`、`FAILED` 或 `TIMEOUT` 状态。

最终 `HoldingResearchBundle/2.0.0` 同时引用已有 `EquityResearchReport`、新增维度报告、原始 Evidence 与产物哈希，按每只普通股列出每个维度的覆盖状态。它分别报告 `STRUCTURALLY_CONSUMABLE` 与 `DOWNSTREAM_READY`：前者只证明结构、绑定和引用可解析，后者还要求每只普通股的公司报告已经重新验证并纳入、补证来源处理完整、待反证问题或空值原因明确。

历史 `ResearchDimensionReport/1.1.0` 与 `HoldingResearchBundle/1.1.0` 仍可只读和确定性重组，其中 `MACRO_MARKET` 明确标记为 `LEGACY_COMBINED_COVERAGE`。兼容读取不自动升级历史结论，也不把一份合并报告判为 `MACRO_CONTEXT`、`MARKET_STATE` 两项通过。

历史阶段产物可通过确定性 `assemble-canonical-holding-research` 入口重组。该入口选择一个基础 run 和统一 decision cutoff，重新验证公司报告并复制到新的外置交接目录；它不会修改原运行包或调用模型。不同 run、cutoff、CouncilRequest 或 Evidence 集合的补证保留在 `package_provenance.excluded_supplements`，不能静默拼成同一次用户研究。

`unresolved_cross_dimension_questions` 只归集报告已经写明的观察或失效条件，并引用原报告和 Claim；Python 不判断哪项 Thesis 正确，也不补写投资意见。中文摘要只归集已验证报告，不消解跨维冲突、不生成统一分数。

## 首版最低研究问题

- 技术：多窗口趋势、相对基准、波动/回撤、量价关系和推翻当前解释的信号。
- 基本面与事件：业务与增长驱动、盈利质量、现金流/资本配置、适用估值假设、关键事件和未知项。
- 研报：作者依据、预测/估值假设、与其他资料的分歧、对已有研究判断的具体作用及利益披露限制。
- 行业：同行相对位置、行业与公司因素、需求/价格/周期传导和可比性限制。
- 宏观：相关利率、通胀、经济活动、央行政策与发布日历，对不同持仓的传导、敏感性和反向情景。
- 市场：大盘与相关板块、跨资产序列、波动/信用指标或明确代理，以及 24 小时市场事件；所有代理、时点和不能推断的方向必须显式说明。
- 所有权与期权：只解释实际取得的披露或快照、滞后和覆盖，不从单期数据推断资金方向。

## 当前来源与限制

### 最新消费核对（2026-10-01）

`complete-eight-dimension-source-consumption`已完成技术及八维内容验收并取得最终人工完成批准，四份主规格已同步，限定发布及归档收尾沿批准执行。第十三批`eight-dimension-readable-results-20261001.wN788G/run`同原资料与截止点、原shell入口实际8子/1父，八份报告保存且独立内容8/8 PASS。技术计算与有据推翻条件、基本面财季/单季累计/重组语义、同行比较、宏观原观测/传导、市场广度/波动/代理、所有权两期/内部人、期权报价/Greeks/规模/时点及许可研报正反/当批上游关系均达原最低问题；没有拼旧报告、降低门禁或增加Agent。旧计算引用方式和其他模式保持兼容。LOW_CONFIDENCE/SOURCE_LIMITED等真实限制保留，不把八份SAVED标为研究充分COMPLETE。版本/hash、实际查询/计算与成本限制见[验收记录](../../reviews/development/complete-eight-dimension-source-consumption-acceptance.md)。

### 第十二批诊断（历史，已由上述最终验收承接）

`complete-eight-dimension-source-consumption`尚未内容验收完成。最新已结束第十二批`eight-dimension-content-consistency-20261001.aRH63I/run`实际8次子启动、八项可信终态、7份报告保存，父正常收尾且源码未变；独立同行/宏观/所有权/期权/研报五维PASS。累计现金流、EPS一次性解释、市场摘要方向和研报金额/逐上游关系已修；仍有基本面财季标签错误、市场波动率计算错选及技术零依据主张。现沿原计算选择提供新任务可读结果引用、原一次修订并列明确零关联诊断，并由基本面核对原文财季，不改变同批8/8标准或自动改稿、不拼历史报告。版本、原hash、成本和接缝见[验收记录](../../reviews/development/complete-eight-dimension-source-consumption-acceptance.md)。

当前研究仍限普通股八维输入与解释；完整独立全文、SEC 13F全覆盖、历史vintage和主动期权方向等受限边界不变。这不是CIO操作建议、历史回测或候选晋升。

### 消费核对（2026-09-29，历史批次）

`host-v2/run` 在同一冻结 cutoff 保存八份报告：技术、行业、宏观、市场、所有权、期权六维有可定位的实质研究；研报等内容缺口尚未清除。之后 `table-unit-ready` 与最新 `monetary-guard-ready-v2` 各只定点运行基本面→研报两项。最新轮虽通过执行与依赖证明，且保留 FY2026 年度 EPS、受限历史比值和一次性收益限制，基本面却漏掉上一轮正确呈现的 SEC 完整财年收入结构；研报在多来源主张中又将中文金额无同主张收据改写为英文 billion USD。独立只读内容复核判 FAIL。两项定点仅为 `DEPENDENCY_CHAIN_EVIDENCE`、2/8，不是新完整八维包；旧六维仅是相同冻结输入下的历史证据。当前累计 **103子/25父**，Change 最终内容验收和人工完成批准均未完成；无新 Skeptic/CIO/Eval 或交易建议。

以下旧批次按各自当时状态保留，不作为上段两包的替代或合并证明：

`complete-eight-dimension-source-consumption` 尚未完成整体验收，以下按原始运行包分别说明，不跨包拼装：

- `eight-dimension-reference-readiness-fi29yasd/ready-final-v2` 经原失败任务补跑已有八份合法报告。技术20/60/252窗口、基本面期间与计算、MRVL/ALAB业务及季度营收比较、宏观条件传导、市场广度与板块/波动代理、机构Q1/Q2变化、期权报价/Greeks均已有真实消费证据；研报虽合法保存，仍有来源归属及上游缺口扩大问题，不能据此宣称八维内容全部通过。
- `eight-dimension-structured-readiness.hV9ie4/run` 的基本面→研报定点验证已通过，研报实际消费Morningstar章节，并正确保留来源、预测与上游估值限制。显式开启的结构化提交由程序序列化和绑定可信身份，仍经过原Schema/引用/PIT门禁；首稿附件路径错误由原Agent在一次纠正后修复。该包只有两维，不能替代完整八维包，也不自动迁移其他七维或旧包。
- 独立公开全文、完整 SEC 13F、历史 vintage、逐合约历史及资金方向仍受限。旧批次调用额度已用尽；没有因此自动启动新一轮研究、Skeptic/CIO 或归档。

输入包装已测得参考token减少，但子Agent完整usage不可观测，严格质量A/B未测试；不宣称全流程成本降低或预测精度提高。完整证据与剩余验收项见[验收记录](../../reviews/development/complete-eight-dimension-source-consumption-acceptance.md)。下述早期批次结果保留为历史，不作为当前是否已经消费的结论。

当前三域及 provider 平面的权威映射见 [`holding-research-inputs.json`](../../product/profiles/holding-research-inputs.json)，来源、预算和实测状态见 [免费公开资料能力表](../data/free-source-capability-matrix.md)。新运行会在 manifest 中锁定该拓扑、引用版本与 hash；历史 `live-us-equity/4.0.0` 仅作 `RETIRED/COMPATIBILITY_ONLY` 读取，不再代表当前创建入口。

基础披露层以 SEC 与 Yahoo 为主：SEC 承担公司身份、申报、财务事实与公开事件，Yahoo 承担冻结行情、基准及可确定性派生的市场/估值输入。研究补充层可以接入本机 `127.0.0.1` Moomoo OpenD，但其当前契约只允许新加坡区域、只读 quote capability；OpenD 不可达、未授权或字段不足时，只降低对应 supplement 数据集状态，SEC/Yahoo 合格资料仍继续，不得回退到客户端 Cookie、私有接口或登录绕过。

Moomoo 补充按资料语义进入既有能力，不新增数据源 Agent：分章节 Morningstar、评级与目标价进入 Company 的 `RESEARCH_REPORT`；营收分部与管理层进入 Company 的既有事实输入；供应商宏观历史、Calendar 与 Dot Plot 进入 `MACRO_CONTEXT`；涨跌分布、全市场期权统计和 FedWatch 进入 `MARKET_STATE`；逐股动态期权及供应商资金流进入 Market Catalyst 的 `OPTIONS_FLOW`；机构、内部人与空头补充进入 `OWNERSHIP_DISCLOSURE`。官方宏观、SEC 和 Yahoo 的主源职责不被覆盖。

公开 `moomoo-news-search` 与 OpenD 是两条独立来源：前者无账户认证、只返回新闻/公告/Research 的标题、类别、时间和链接。身份与时点合格的逐股结果进入 Company `research_discovery`，始终为 `LEAD_ONLY`，不是已读研报或发行人原文；仅当 Yahoo 24 小时市场新闻无合格项时，相关公开标题才作为 Market `TITLE_ONLY` 后备。Macro 仍以 BLS、Treasury、Federal Reserve 等官方数值与正文为主，新闻标题不能补成宏观观察值。每批的采集、Gate 准入与 Agent 有效引用是三个独立状态，不能互相代替。

同一冻结 Gate 可供各专项复用，但 Company Analyst 的旧通用启动目录不再重复展开上述已有专门消费者的数据集；该边界用于避免上下文膨胀和跨能力误用，Evidence 仍保留在 Gate，并由对应专项的 `allowed_evidence_ids` 交付。

动态期权先复用 Yahoo 正式 Collector；Yahoo 失败时沿用 Moomoo 的到期日、静态链、确定性近价选约和批量动态快照回退。若 Yahoo 已选合约合格但缺 Greeks、乘数或 IV，仅按标的/到期日/行权价/类型及标准合约身份映射这些已选合约，最多三个到期日、48 个合约；两源字段并列、冲突显式保留，不启动第二套择约。只有静态合约目录时必须标为受限，不能用全市场 Put/Call、资金流或 Short Interest 替代合约级 bid/ask、volume、OI 和 IV。

2026-09-21 的 MRVL 真实持仓验收已按该策略把 19 个可用到期日、388 个候选收敛为三个到期日的 48 个合约，并在 Capture、PIT Gate 和 `OPTIONS_FLOW` 交付保持同一数量；报告因缺 Greeks、multiplier、完整链与主动买卖方向而保持 `SOURCE_LIMITED/PARTIAL`，该受限状态是正确完成而非数据可用性的夸大。

2026-09-27 的新 MRVL 来源批次已从 OpenD 为 Yahoo 已选的 48 个合约补得动态 Greeks/乘数，并取得市场广度、供应商两期已结束机构汇总、分节 Morningstar 和 378 点 MRVL/SPY 日线；这些首先是来源与 Gate 事实，不自动改写 2026-09-21 历史报告的状态，也不能单独证明八维 Agent 已查询或引用。

同日后续的精简输入八维宿主运行已保存八份合法报告：技术为 `COMPLETE/SUFFICIENT`；基本面、行业、宏观、市场、所有权与期权均为 `LOW_CONFIDENCE/PARTIAL`；研报为 `FAILED/INSUFFICIENT`。行业实际比较 ALAB/MPWR，市场引用广度，期权引用部分 Greeks/标的波动；但研报未读取已入 Gate 的 Morningstar 分节，所有权未使用两期机构汇总。阶段 `PASSED` 只表示八份报告可保存和装配，不意味着所有维度研究充分、也不形成投资操作建议。分项查询、引用、剩余限制与版本见本 Change 验收记录；研报分层规则与机构任务实际补跑尚未完成。

2026-09-28 的新一轮 MRVL 八维运行没有通过内容验收：仅市场、所有权、期权 3 份报告保存；技术、基本面、行业、宏观被引用校验拒绝，研报因基本面依赖失败未派发。市场报告仍未解释实际广度数值，所有权仍未形成 Q1/Q2 机构比较；期权报告对具体报价、Greeks 和单位限制已有实质解释。宿主进程 `PASSED` 不改变这些失败状态。后续已在本 Change 范围内用零模型验证计算收据引用、同会话一次纠错和研报许可章节与独立正文分层校验；这些修补尚无新的真实 Agent 八维报告证明，不应提升 coverage。历史运行包不改写。

公开研报正文、13F 两期机构持仓、历史期权结构和可验证资金行为等仍按能力矩阵逐项记录 `AVAILABLE`、`PARTIAL`、`SOURCE_LIMITED` 或准确失败状态。它们不是因为某个已归档 Change 而自动完成；只有真实采集、PIT Gate、冻结引用和对应 Agent 实际消费闭合后，才可提升本批次 coverage。

完成本阶段只证明 canonical 研究包可以供下一 Agent 消费，不代表 Skeptic、CIO、Risk 或候选版本晋升已经通过。

正向研究与独立反证均完成后，只有用户另行明确请求，才能按 [正反研究之后的 CIO 综合](predecision-cio-research.md) 在独立外置运行中重验来源包并进入主线程 CIO；当前后续阶段只交付非动作研究综合，尚不提供完整组合建议，也不会由本阶段自行启动。
