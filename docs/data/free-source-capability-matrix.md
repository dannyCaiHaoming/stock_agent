# 免费公开资料能力表

本表用于记录当前 Company / Macro / Market 三域的真实来源语义与有界请求预算。它不是供应商长期可用性承诺；每个来源在对应阶段实测后更新状态。所有进入研究上下文的事实都必须带 `source_id`、`as_of`、`retrieved_at`，并在 Agent 读取前通过 PIT Gate。当前拓扑由 `product/profiles/holding-research-inputs.json` 定义；旧 `live-us-equity/4.0.0` 仅作历史兼容读取。

## 请求预算约定

- “正常请求”包括必要的身份查询、单次列表/分页、明细和正文获取，不计作失败重试。
- 每个请求至多进行一次有原因的暂时故障重试；权限拒绝、登录/付费限制不重试。
- 主源/回退选择默认最多两个供应方；明确标为 `supplemental` 的线索可独立有界采集，但不能成为第三个隐式回退或填平正文缺口。
- 缓存命中保留原始 `retrieved_at`，不得伪装为新采集。
- OpenD 仅使用批准的本机只读 Quote 清单；不得回退客户端 Cookie、私有接口或登录绕过。
- 研报每证券至多 3 次查询、检查 10 个候选、尝试 5 份正文；取得足够材料后提前停止。

## 渐进来源矩阵

### 2026-10-01 当前消费核对

最终收尾：本Change已同步且归档，限定实现提交`05905dc`已推送origin/main，五类义务5/5完成。下面保留批准/归档准备时的事实截面，其收尾现已执行完毕；来源覆盖不因归档升级。

最终第十三批`eight-dimension-readable-results-20261001.wN788G/run`使用同8835事实/2026-09-28截止点，正常8子/1父、8SAVED，八维最低内容独立8/8 PASS：技术/市场多窗口计算正确消费，基本面财季/累计利润现金流及一次性处置解释正确，同行业务与经营比较、Moomoo宏观代表观测、广度/代理、机构两期/内部人、同合约期权报价/五Greeks/IV/OI/规模及许可Morningstar正反章节与当批上游关系均已消费。没有借旧PASS、改来源或将受限状态升级COMPLETE。最终人工完成批准已取得，四份主规格已同步，限定实现发布及归档收尾沿批准执行；具体原文/工具/三类hash和真实限制见[验收记录](../../reviews/development/complete-eight-dimension-source-consumption-acceptance.md)。后续来源表中的日期行仍是各次原采集/研究截面，不覆盖本次消费结果。

### 2026-10-01 历史过程截面（由上方最终核对承接）

最新第十二批aRH63I/run同8835事实/2026-09-28截止点，正常8子/1父、7SAVED，独立内容Industry/Macro/Ownership/Options/Research Report五维PASS。宏观代表补源、期权同合约报价/五Greeks/IV/OI/规模、基本面累计现金流和EPS一次性解释、研报许可章节与逐上游关系已实际消费；仍有基本面财季写错、市场所述波动率误选成交量比率引用、技术零依据主张执行失败。不是缺源或超时；当前只修选择表达/并列诊断/原文财季自核，不借旧PASS或改来源，未达到同批8/8。具体账及hash见验收记录。

第十批pZ6cqi/run当时正常8子/1父、8SAVED，独立内容6PASS/2FAIL；宏观已读Moomoo却未用及期权漏乘数/规模，已由第十一批对应真实消费承接，不改原历史报告。

第九批历史`eight-dimension-marker-consumption-20261001.X22ArC/run`使用同8835条冻结事实与2026-09-28截止点，实际7次子启动、5SAVED、八项可信终态。当时独立内容同行/宏观/所有权PASS；市场漏选择60/252日波动率，期权未查询已有同代表合约OpenD补源，内容FAIL；技术/基本面执行失败，研报依赖阻断未启动。机构两期与内部人、宏观同条观测已真实消费；先前许可Morningstar读取仅对应历史批次，该批不能借用为研报PASS。失败原件保留，已由上方新同批八维内容核对承接；不将其当时状态误称当前状态。精确调用账及原hash见验收记录。

公开独立全文、完整SEC 13F、历史vintage、逐合约历史及主动方向仍真实受限；上述消费不提高这些来源覆盖。未开启回测、账户建议、Skeptic/CIO/Eval或新增来源采集。

### 2026-09-29 消费状态更新（历史批次）

`host-v2/run` 已在同一冻结截止点保存八份报告：技术、行业、宏观、市场、所有权和期权六维有可定位的实际研究；基本面与研报也已运行，但旧研报仍有内容缺口。后续 `table-unit-ready` 与最新 `monetary-guard-ready-v2` 各只定点执行基本面→研报 2/8。最新轮的执行/依赖证明通过、FY2026 EPS 与受限历史比值保留，但基本面遗漏了上一轮正确呈现的完整财年收入结构；研报仍把许可章节中文金额无同主张收据改写为英文 billion USD。独立内容复核判 FAIL，不能把来源可读、任务已运行或窄门禁未报错写成 Change 内容通过，也不能把定点报告拼入旧八维。累计真实调用 **103 子/25 父**，未启动 Skeptic/CIO/Eval；具体 proof、版本和限制见验收记录。

下表是当前可核实的**分批证据**，更新后文早期“未消费/待验证”的历史状态；来源预算、原批次事实及外部限制不变。它不是一次新八维完整内容验收通过的声明。

| 能力 | 当前真实证据 | 尚未证明或仍受限 |
|---|---|---|
| 技术窗口 | `host-v2` 解释 MRVL/SPY 20/60/252 窗口收益、相对表现、波动、回撤与量比 | 不代表历史交易回测或预测准确率；本次定点未重跑技术维 |
| 同行业务/财务 | `host-v2` 实际比较 MRVL 与 ADI/MPWR 的业务重叠、差异及同一营收指标，注明财季起止错位 | 不构成严格排名或同口径分部收入比较；本次定点未重跑行业维 |
| Macro/Market | `host-v2` 分别解释官方政策/利率/通胀/活动与 SPY、板块、波动、跨资产代理及广度观测 | 历史 vintage、信用/流动性和市场研究正文仍有限；两维不是同一报告 |
| 机构汇总 | `host-v2` 实际计算并引用 2026/Q1→Q2 机构数、持股数与比例变化 | 供应商汇总不等于逐管理人 SEC 13F 或主动净买卖 |
| 期权 | `host-v2` 解释代表合约 bid/ask、OpenD OI/IV/Greeks、跨来源与时点限制 | 非同步快照，不提供主动方向或逐合约历史 |
| Morningstar章节 | `table-unit-ready` 与最新定点研报均已查询并引用许可章节、作者观点与估值，公开标题线索仍为 `LEAD_ONLY` | 许可章节不是独立全文；最新研报多来源主张仍有无收据金额改写，内容复核 FAIL |

上述 `host-v2` 与两轮定点使用相同冻结 Gate，但执行、依赖报告及交付版本不同，不可视为同批结果。最新定点已完成独立只读内容复核且判 FAIL；Change 最终复核和人工完成批准仍未取得。路径/hash、成本与查询证据见[验收记录](../../reviews/development/complete-eight-dimension-source-consumption-acceptance.md)。

### 来源契约与历次验证记录

下表逐来源行保留各次采集/研究当时的证据截面，其中 2026-09-27 的“未消费”仅指该次报告；不能覆盖上方 2026-09-29 的当前分批消费核对。后文 2026-09-28 的 3/8 失败段落同样是历史批次，不是最新运行结论。

| 能力/字段 | 首选来源 | 备选来源 | 费用/认证 | 时间语义与延迟 | 历史/缓存 | 本阶段预算 | 来源记录与缺口影响（含历史截面） |
|---|---|---|---|---|---|---|---|
| 美股身份/股票池 | NASDAQ Screener 官方接口 | SEC ticker/CIK 映射 | 免费、通常无密钥 | 响应时点；不是上市状态的完整历史 | 本地冻结响应 | 身份列表 1 次；必要明细 1 次 | 已有代码与离线契约测试；网络可用性须按批次记录 |
| 日线 OHLCV、复权、分红拆股 | Yahoo Finance（现有 yfinance 路由） | AkShare 暴露的美股日线 | 免费、无项目凭证；非正式 SLA | 日线、可能延迟；未完成交易日必须排除 | 约 252 交易日起步；按冻结批次缓存 | 每证券/基准正常采集 1 次；暂时故障重试 1 次；切换 1 次 | `IMPLEMENTED`：已保留 OHLCV、调整收盘、分红和拆股，完成 PIT、断点、固定计算和图表同源测试；真实 LLM 批次待 P1 验收 |
| 当前估值快照 | Yahoo 当前统计（仅并列展示）+ Yahoo 价格与 SEC 财务/股数的确定性派生 | 无默认商业估值源 | 免费、无项目凭证；Yahoo 当前统计无正式发布时间保证 | `PROVIDER_REPORTED` 与 `DERIVED` 分列；价格、财务期间、公开时点和获取时间分别保留 | 冻结 `EquityValuationSnapshot`；不以当前检索值回填历史 | 沿用行情与 SEC 采集预算；不为补齐倍数循环换源 | `RESEARCH_VALIDATED_LIMITED`：支持 trailing PE、P/S、P/B、FCF Yield、EV 及条件 forward PE/EV-EBITDA；缺 EPS、股数、资本结构或非正分母时明确不适用/缺失。MRVL 最终授权批次已查询并解释 DERIVED P/S，冻结 calculation_ref、全部输入 Evidence 与 `FY + current YTD - prior YTD` 期间血缘均通过确定性校验；报告整体仍因其他资料缺口保持 `LOW_CONFIDENCE`。 |
| 历史估值重建 | Yahoo 月末非分红复权价格 + SEC 当时已公开财务版本 | 无默认历史估值供应商 | 免费；依赖原始申报公开时间与历史行情可用性 | 每点只用估值日当时已公开版本；当前检索时间不能冒充历史公开时间 | 默认近 5 年月末；至少 24 个有效点且请求窗口覆盖率 80% 才给分位 | warm-up 单列有界窗口；缺核心输入不自动换源或降标准 | `RESEARCH_VALIDATED_LIMITED`：盈利样本 PLAB 已形成 50/61 个有效月末和 81.97% 覆盖率；MRVL 冻结样本因 PIT TTM diluted EPS 缺失明确为 `CURRENT_VALUE_UNAVAILABLE/PIT_EPS_MISSING`、0 点/0 覆盖，不伪造历史 PE。最终 MRVL Agent 已实际查询、解释并在 HTML/PDF 中保留该限制卡。 |
| SEC 公司披露、财务事实、公司事件 | SEC submissions/companyfacts/filing 文档 | 发行人 IR 公开页面（后续最小接缝） | 免费；SEC 需合规 User-Agent | `accepted`、报告期与获取时间分别保留 | SEC 历史覆盖；冻结原始响应 | 身份、submissions、companyfacts 各 1；必要 filing 文档 2；暂时故障各 1 次 | `IMPLEMENTED`：现金流、资本开支、稀释、债务到期标签及业绩附件可进入 Gate；companyfacts 不含 XBRL 分部 dimension，明确保留分部结构化数值缺口 |
| 公司基本面补充与静态图文 | SEC Company Facts/申报正文 + Yahoo 冻结行情；渲染阶段不联网 | 无默认第二来源 | 同上述免费来源 | 每项保留期间、单位、公开/获取时间、公式与 Evidence；不同口径不强连趋势 | 冻结 `CompanyFundamentalSupplement`、同行附件、chart-data、SVG/HTML | 披露与同行各自使用既定有界预算；缺组显示限制卡 | `RESEARCH_VALIDATED_LIMITED`：最终授权 MRVL 批次实际查询估值、历史估值、基本面和同行四类附件，生成已验证 JSON/Markdown 与同源离线 HTML/SVG。251 个交易日与两期完整财年可视化可用；基准、历史 PE、指引、治理及同行不足均以限制卡呈现。桌面、390px 窄屏和 20 页打印已检查，无脚本、损坏图片或页面横向溢出；不代表 Runtime Eval、完整组合决策或 Promotion PASS。 |
| 自动研报发现与正文 | OpenAlex Works 搜索 + Content API 的公开 GROBID XML 正文 | 暂无默认第二来源 | 搜索可匿名；Content API 需要外置 `OPENALEX_API_KEY`；不绕过登录/付费 | 发布日、获取时间与预测目标期间分开；未来发布日期排除 | 搜索结果为 `LEAD_ONLY`；正文按 body hash 冻结并保留章节定位 | 每证券 3 查询/10 候选/5 正文 | `IMPLEMENTED_CURRENTLY_SOURCE_LIMITED`：ALB/MRVL/WOLF 各有 10 个真实候选；未配置 key 时正文均准确停在 `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED`，未冒充已读正文 |
| 发行人公告/IR 正文 | SEC 8-K 业绩附件与 management discussion | 无默认网页爬取备源 | 免费；SEC 需合规 User-Agent | accepted/published/as_of/retrieved 分开 | 冻结原始响应与正文解析 hash | 复用现有每证券披露预算 | `IMPLEMENTED`：Gate 中已核验正文自动投影为 `ISSUER_MATERIAL/BODY_VERIFIED`；发行人指引、第三方预期与独立观点分类不互换 |
| 行业同行资料 | NASDAQ 完整股票池选择 + SEC/行情有限采集 | 公开行业材料 | 免费公开资料 | 各公司期间、币种、会计口径分别保留 | 候选池、选择、采集快照和 Gate 分层冻结 | 每公司最多 3 个候选；只采集实际选择的去重同行 | `RESEARCH_VALIDATED_PARTIAL`：2026-09-27 MRVL 最终 Gate 已冻结 ALAB/MPWR/ADI，八维行业任务实际查询并比较 ALAB、MPWR 的 SEC 事实，报告为 `LOW_CONFIDENCE/PARTIAL`；这不证明所有同行或跨运行转研究目标已完成。 |
| 官方宏观：利率、通胀、经济活动与政策 | BLS Public Data API v1 + U.S. Treasury Daily Rates + Federal Reserve RSS/正文 + BLS iCalendar | BEA/FRED 仅作后续增强 | 免费、无项目凭据 | 观察期、官方 pubDate、决策 cutoff 与获取时间分开 | 无 historical vintage 时不还原历史认知；修订以 raw hash 分版 | BLS 序列 1、Treasury 1、BLS 日历 1、Fed RSS+正文 2 | `IMPLEMENTED_CURRENTLY_VERIFIED`：本 Change 六个字段全部真实 HTTP 200 并冻结；非农就业作当前活动指标，GDP/PCE 未承诺 |
| 市场上下文与 24h 新闻 | Yahoo 公开 chart/search | Moomoo 公开 `news_search` 仅在 Yahoo 无合格新闻时补标题 | 免费、无账户凭据；非正式 SLA | 日线观察/获取与新闻 published/retrieved 分开；公开搜索亦须过 24h/PIT/相关性检查 | 全量冻结，Agent 每序列有界消费最新观测 | 18 序列 + Yahoo 新闻 1 次；必要时公开搜索 1 次 | `SOURCE_AND_GATE_VERIFIED`：2026-09-26 MRVL 同截止点批次中 Yahoo 新闻为 0，公开搜索 10 个候选中 1 个标题通过过滤并进入 Gate；不代表 Market Agent 已引用，更不证明正文已读 |
| Moomoo OpenD 行情补充 | 本机 `127.0.0.1:11111` Moomoo OpenD | SEC/Yahoo 继续承担各自基础资料，不作为 OpenD 的伪替代 | Singapore 区域 loopback OpenD quote-only；需用户本机完成协议和相应行情权限 | 保留响应市场时点、供应商更新时间、获取时间、区域和权限状态 | 冻结 supplement；不得从当前值回填历史 | 每证券/数据集按 supplement plan 有界查询；游标方法最多三页，已选期权的静态映射至多三个到期日 | `PARTIAL_RESEARCH_CONSUMPTION`：2026-09-27 MRVL 本机 SDK `10.10.7008`/OpenD `1010` 实测：广度 1、宏观历史 192、经济日历 300（页预算后仍 PARTIAL）、机构汇总 50、Morningstar 分节 14、已选期权动态风险事实 48 条进入 Gate。正式八维任务已实际引用广度和期权风险资料，但未读取机构汇总或 Morningstar 分节；供应商数据不替代官方值、SEC 13F 或独立研报全文。SDK/权限失败按数据集单列，不回退 Cookie 或私有接口。 |
| Moomoo 公开标题线索 | 无认证 `news_search` | 无正文后备 | 公开 HTTPS；不使用 OpenD、Cookie 或账户 | 标题、类别、发布时间、获取时间和原始链接分开保存 | 原始响应 hash 与最小元数据冻结；不获取文章正文 | 每证券 ticker/发行人名各至多 1 次、每次 10 项；Market 后备至多 1 次 | `COMPANY_LEAD_CLAIM_VERIFIED`：2026-09-27 MRVL 同截止点批次有 11 条 Company 线索准入并被研报任务查询，1 条在有效 `SOURCE_LIMITED` claim 中原样引用；全部仍为 `LEAD_ONLY`，独立研报正文为 0。Market 标题 2 条进入允许目录但本轮 Agent 未运行、未验证引用 |
| 机构持仓/内部人披露 | SEC Forms 3/4/5；Moomoo 供应商机构汇总 | 完整 SEC 13F 聚合仍未接入 | 免费；SEC 需合规 User-Agent；OpenD 需本机 Quote 权限 | 交易日、accepted 公开时点、供应商更新、获取时间与季度标签分别保留；未结束季标 provisional | SEC 原始披露与供应商汇总分层冻结，不作拆股回溯调整 | SEC 每发行人最新 1 份 Form 3/4/5；OpenD 机构至多三页，内部人各方法至多三页 | `SOURCE_AND_GATE_VERIFIED_PARTIAL`：2026-09-27 MRVL 有 Q1/Q2 已结束及 Q3 provisional 的供应商机构汇总 50 条，内部人 78 条；正式 Ownership 报告只引用内部人/SEC Form 4，机构两期未被 Agent 消费。已定点修补该任务的受限计算权限，真实研究仍待验证；供应商变化不等于完整 13F 或资金方向。 |
| 期权链快照/资金代理 | Yahoo Finance 已选期权链 | 对同一已选标准合约，Moomoo OpenD 只补缺失动态字段；Yahoo 失败时才独立回退 | 免费、Quote 权限受 OpenD 限制；非正式 SLA | 各源快照/last trade/获取时点分别保留，IV 统一小数口径 | 不承诺逐合约历史 OI、成交方向或真实资金流 | 最多三到期日、48 合约；OpenD 静态映射最多三请求、动态快照一次 | `RESEARCH_VALIDATED_PARTIAL`：2026-09-27 MRVL 的 48 个 Yahoo 已选合约映射到 OpenD 动态快照，48 条 Greeks 与乘数事实进入 Gate；正式 Options 报告实际查询/引用部分 Greeks 与标的波动，仍为 `LOW_CONFIDENCE/PARTIAL`。它不等于合约级历史结构或资金方向，单快照不得推断主动买卖。 |

2026-09-28 的同一 MRVL Gate 新八维运行仅保存 3/8 份报告：Options 对报价、Greeks 和单位限制的解释比上轮具体；Market 虽保存报告，却未解释广度实值；Ownership 仍未消费 Q1/Q2 机构比较。技术、基本面、行业、宏观的草稿被引用校验拒绝，研报依赖基本面而未派发。新增计算收据和一次同会话纠错仅通过零模型检查，不能把来源已准入、阶段 `PASSED` 或模拟报告当成真实八维研究完成。详情见 [本 Change 验收记录](../../reviews/development/complete-eight-dimension-source-consumption-acceptance.md)。

## 状态定义

- `IMPLEMENTED`：代码和确定性契约存在，不代表外部来源本次可用。
- `RESEARCH_VALIDATED`：真实资料进入 Gate，并由真实 LLM 形成满足最低问题的实质报告。
- `SOURCE_LIMITED`：完成了限定尝试并保存失败、影响、未实现子能力和 TODO；不等于能力通过。
- `NOT_TESTED`：尚未在对应阶段执行，不得写成来源不可用。

## 已知延期子能力

- 结构化分部数值：SEC `companyfacts` 不保留 XBRL axis/member；需读取 filing XBRL instance 后才能建立可靠分部桥接。正文仍可供公司 Agent 定性分析，但不能冒充结构化分部数值。
- 机构持仓：13F 以申报机构为主体，不能只凭被投公司 CIK 直接得到完整机构持仓变化；需增加申报人发现、information table 解析、CUSIP/发行人身份绑定及两期可比链路。
- 研报：OpenAlex 主要覆盖学术与技术研究，不等于卖方股票研报库；正文 Content API 需要外置 API key。若真实批次没有可读正文，保留实际尝试和未验证范围；SEC 业绩附件只能标为发行人材料，不能冒充独立卖方或第三方研报。
- 期权：已新增有界标的 IV/HV 与全市场统计，不提供逐合约历史 open interest、成交方向、净资金流、期权持仓估值或保证金研究。
