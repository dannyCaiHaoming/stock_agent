## Context

参见 `proposal.md`。当前 Moomoo 边界已经具备 loopback-only、Quote-only、版本化 allowlist、请求/响应预算、内容扫描、缓存 hash 和失败隔离，但能力存在三类漂移：

1. 官方网页已展示 v10.11 契约，而当前锁定并实际运行的是 `moomoo-api==10.10.7008` 和 OpenD server `1010`；新文档字段并不一定出现在当前响应。
2. manifest 批准 12 项能力，正式采集只调用其中一部分；`options_snapshot` 在来源计划中存在，但 Yahoo 和 Moomoo 都没有正式动态期权采集路线。
3. 已标准化 Evidence 的 semantic field 与多维 capability 选择规则不一致，导致 Morningstar、评级、所有权、空头、静态期权和资金数据可能在 Gate 后仍无法进入专业任务。

只读 Spike 已在用户当前 Mac/OpenD 上验证：股票及期权 `get_market_snapshot`、`get_capital_distribution`、机构/分析师双维度评级、`get_option_volatility`、美国期权市场 volume/OI 统计、Macro indicator list/history、FedWatch target rate、FedWatch dot plot 和 Economic Calendar 均可成功调用。该证据只证明当前版本可行性，不等于正式系统闭环。

## Goals / Non-Goals

**Goals:**

- 以纵向能力矩阵管理“文档、Spike、批准、标准化、采集、Gate、消费、验收”，消除假完成状态。
- 用最小高价值接口补齐动态期权、供应商研究、二级 Macro/Market 补充和正确专业消费。
- 对复合响应建立字段级 PIT，避免评级、Morningstar、机构汇总、宏观和期权字段发生历史提前可知。
- 保持当前 Company / Macro / Market 三域和现有专业 Agent；扩大数据，不扩大主观决策角色。

**Non-Goals:**

- 不接入 Trade Context、账户、用户持仓、资金、订单、解锁或任何交易能力。
- 不升级为通用 Moomoo SDK 网关，不允许 Agent 自选方法、证券或任意分页。
- 不把 Moomoo Macro 取代官方宏观来源，不把 Morningstar/评级变成 SEC 事实或独立研报共识。
- 不在第一阶段接入 Option Screen、Option Event、0DTE/卖方排行、策略组合分析或供应商技术指标脚本。
- 不重新启用 `live-us-equity/4.0.0`，不改写历史冻结包或历史 Evidence。

## Decisions

### 0. 先完成取舍与已有来源复用

能力矩阵是一份随 Change 验收维护的清单，不建立独立状态服务或数据库。每行记录研究问题、域/专项、已有响应与消费覆盖、候选方法、文档/运行证据、取舍原因和验收引用。文档发现、调用成功、正式交付和实际研究使用分别记录，不能相互代替。

| 层级 | 范围 | 本次完成含义 |
|---|---|---|
| 必须完成 | 当前批准但未接线的高价值数据、动态期权快照、Company/Macro/Market 路由与验收、已有来源复用检查 | 实现与聚焦验证完成；动态期权核心不允许用静态链替代 |
| 必须评估、条件接入 | 下表候选，以及原计划的合约 volatility、全市场期权统计、capital distribution、FedWatch、Dot Plot 等增强项 | 有界核实；有实际增量且权限/字段/现有链路支持则接入，否则记录具体限制或暂缓原因，不因未使用全部 API 阻塞归档 |
| 暂缓 | 全市场榜单、筛选、实时订阅、交易策略、任意深分页和通用抓取 | 保留取舍原因，不扩展运行系统 |

| 研究问题 | 优先复用 | 必须评估的 Moomoo 候选与取舍 |
|---|---|---|
| 公司收入来自哪里、管理层是谁 | SEC 已下载披露、Yahoo/现有 company profile | `get_financials_revenue_breakdown`、`get_company_executives`；有缺口才接入，背景深挖不逐人遍历 |
| 下一次财报与近期事件 | Yahoo 现有日历、SEC 事件文本 | `get_earnings_calendar`、`get_search_news`；新闻只保证线索，正文可读性单独核实 |
| 市场涨跌是否广泛 | Yahoo 基准行情、现有 Market 输入 | `get_rise_fall_distribution`；固定 US 市场一次请求，补指数不能说明的涨跌分布 |
| 选中合约是否代表整体期权环境 | 已有 Yahoo 期权 collector 与确定性统计 | `get_option_underlying_overview`、`get_option_underlying_his_statistic`、`get_option_underlying_his_volatility`；总览优先，历史最多 30 个交易日/一页，不把局部合约求和冒充全标的 |
| 估值、财务、资本配置与行业关系是否仍缺资料 | SEC financial history/披露、Yahoo 数据和既有行业比较 | 核对 `get_financials_statements`、`get_valuation_detail`、公司行动、industry/plate 接口的覆盖与可行性；已有主源足够则不重复接入，复杂关系图与全行业遍历暂缓 |

候选评估固定到确认持仓中的一个代表证券（共享数据固定 US），每方法最多一次初始请求、不追分页；失败或复杂新增依赖如实记录，不以不断重试扩大范围。正式接入只接受本表领域内、可沿用既有 adapter/Normalize/Gate 的增量；需新增服务、通用抓取或资产职责的方案转后续建议。

现有 `relationships`、`management_governance`、`capital_allocation`、`earnings_guidance`、`event_context` 等来源声明逐项核对。已有原始材料但缺结构化/消费的，优先接线；来源无对应方法的，纠正声明并保留资料缺口，不要求此次重建完整 SEC 解析器。Treasury 优先从同一已下载 CSV 输出同日 2Y/10Y/30Y 及确定性 10Y−2Y 期限差；缺期限时不拼接不同日期。

接口依据为 2026-09-20 审视的 [官方 Quote 目录](https://openapi.moomoo.com/moomoo-api-doc/en/quote/overview.html) 与本地 SDK 方法定义；新增候选尚未完成账号权限 Spike。前述已成功 Spike 的旧证据仅在版本、参数、字段和证据引用仍适用时复用。

### 1. 文档契约和运行契约分层

保留两个不同概念：

- `documented_contract_version`：官方文档页面版本及扫描日期，用于发现候选方法和字段。
- `runtime_contract`：确切 SDK、OpenD server、方法签名、实际响应字段、manifest/hash 和验证时间，用于生产放行。

当前生产继续锁定 `10.10.7008`/`1010`。manifest 仍采用 exact SDK version；未来发布新 SDK 时创建新 manifest 版本并重新 Spike，而不是放宽为版本范围。选择 exact pin 是因为 Moomoo 响应嵌套结构、方法参数和字段可见性已经表现出文档/运行差异。

不新增通用状态服务。能力矩阵复用现有 capability/provider coverage 产物，增加各纵向阶段和 evidence refs 即可。

### 2. Adapter 继续逐方法封装，不提供通用反射调用

在现有 wrapper、validator、缓存和失败隔离机制上扩展。每个新增方法必须具有：

- 独立 wrapper 和参数 validator；
- 只接受批准的 US security、市场枚举、indicator ID、日期范围和分页；
- 方法级 max requests、rows、bytes、timeout；
- 明确响应 kind、必需字段和可选字段；
- 权限、限流、schema drift 和分页未完成的稳定错误/gap。

`get_market_snapshot` 的 `code_list` 只能来自确定性期权选择器或固定 Market symbol policy，Agent 不能传入任意列表。Macro indicator history 只接受版本化 indicator allowlist，不能先返回 24 个指标后让模型自由选择网络请求。

正式新增采集默认每证券最多 24 次请求、共享 Macro/Market 最多 16 次请求，全批新增请求不超过 `24 × 证券数 + 16`；新增采集总时长不超过 `120 × 证券数 + 120` 秒，现有更严格限额优先。重试/分页计入预算，剩余不足时增强项标记预算排除，不抢占核心数据。共享 Macro、Calendar、FedWatch 和全市场统计每批各按批准参数采集一次，复用冻结 Evidence，不按持仓重复请求。以上只增加计数和截止时间检查，不新增调度器；预算是调用上限，不限制产品持仓数量。

### 3. 动态期权使用“发现、选择、快照”三段式

初始流程：

```text
underlying snapshot
        |
        v
expiration dates + static chain
        |
        v
deterministic selection policy
        |
        +--> selected contract codes
        |
        v
batched market snapshot
        |
        +--> optional volatility for <= 4 representative contracts
        v
field-level normalized options_snapshot
```

初始选择策略复用版本化来源配置：依次取最近非过期到期日、最接近 30 天且未选中的到期日、最接近 90 天且未选中的到期日；相同距离取较早日期，不足三个则保留实际数量。每到期日每种 option type 取现价上下各最近四档（平价只计一次，不存在的一侧不补造），单标的动态合约上限 48。若已确认组合有同标的期权合约，经身份核实后用其到期日替换最远的非持仓到期日，并优先保留该合约；持仓合约自身超过预算时记录未覆盖项，不扩大限额。现价不可得时不猜近价范围。保存候选范围、入选数、排除理由和策略版本；未读取全链时不声称知道全链总数。

`get_market_snapshot` 是单合约动态字段的主方法；`get_option_quote` 主要面向组合策略 legs，第一阶段不作为普通合约快照主路径。全市场 `get_option_market_statistic` 以两个有界请求分别取得 volume 和 OI；不得从 ratio 反推个股方向。

Yahoo 已有动态期权能力优先复用并接到正式 Collector，不重新实现第二套 Yahoo 客户端；主源成功时不为覆盖率重复抓取 Moomoo 同类全套数据。Moomoo 回退能力以明确测试场景验证。标的总览作为有限合约样本的独立背景，不能替代合约快照；最多四个代表合约的 volatility 仅在总览/既有历史不能回答当前问题时追加，属于增强项。

### 4. Normalize 使用字段时间策略而非响应时间复制

沿用现有 `source_id`、`as_of`、`published_at`、`retrieved_at` 与 metadata；仅在语义需要时补充下列元数据，不要求每条旧 Evidence 新增全部字段，也不建设独立时间框架：

- `as_of_policy`
- `published_at_policy`
- `provider_observed_at`
- `provider_updated_at`
- `time_zone`
- `vintage_status`

具体规则：

- Market snapshot：`update_time` 仅用于 price quote；OI/IV/Greeks 等没有独立 provider time 时，以 `retrieved_at` 作为保守 snapshot `as_of/published_at`，同时标记 `PROVIDER_EFFECTIVE_TIME_UNAVAILABLE`。
- Morningstar：每个正文 section 单独生成 Evidence，使用其 `update_time`；星级、fair value、analyst report metadata 分开；缺 `context` 时生成 gap 而非空正文。
- Rating：`recommendation_date` 是 `as_of`，`update_time` 是最早供应商可知时间；若 update time 不可用，published_at 退回 retrieved_at。
- Institutional aggregate：解析 `period_text` 为报告期；update time 仅作为 published/provider updated time。无法可靠解析时不猜季度末。
- Macro History：`data_time` 为观察期，`release_time` 为候选公开时间；只有时区规则已验证才转换，否则 published_at 使用 retrieved_at 并保留 raw release string。actual、predict、previous 分别建模，predict/previous 标记无历史 vintage。
- Option market statistic：交易日为观察期，published_at 使用 retrieved_at；volume 和 OI 分系列，不要求同日齐全。

百分比、货币和单位转换通过版本化字段映射完成，同时保存原始值。不能仅凭字段名或示例决定乘除 100。

没有原始版本证明的历史 actual 也按当前供应商修订快照处理；旧 release time 不证明当前数值过去已知。未来 Calendar/FedWatch 的事件日期保存为事件目标时间，资料 `as_of/published_at` 表示该日程或预期何时已知，不把未来事件误当未来才可用的证据。只拆分时间/用途不同的字段族，不逐标量扩增 Evidence。

### 5. Macro 与 Market 采用来源层级而不是 winner 覆盖

数据职责：

| 输入 | 主源 | Moomoo 用途 |
|---|---|---|
| CPI、就业、非农 | BLS | current secondary cross-check、共识补充、覆盖冲突 |
| Treasury yields | Treasury | 不替代 |
| Fed 政策正文 | Federal Reserve | 不替代 |
| PPI、核心 CPI、PCE、零售等未覆盖系列 | 后续官方源优先 | 当前二级补充，明确非官方与 vintage 限制 |
| Economic Calendar | 官方日历优先 | 事件发现、供应商 consensus/actual 补充 |
| FedWatch | 无官方政策事实等价物 | Market-implied expectation，只进 MARKET_STATE |
| Dot Plot | Fed SEP | 供应商转引或 fallback，不冒充原始文档 |

首批目标指标固定为 CPI、核心 CPI、非农就业、失业率、PPI、PCE/核心 PCE、零售销售和政策利率；已由官方源满足的问题，Moomoo 仅补 consensus 或缺失口径，最多选择八个 indicator ID。每系列最多最近 24 个观测/一页；Calendar 为 cutoff 前 7 天至后 30 天、一页；FedWatch 最多未来三次会议，Dot Plot 最多最新一版。实现前通过列表响应将目标绑定到真实 ID、单位、同比/环比或水平值口径和时区，不能凭名称猜 ID，也不能把 BLS CPI 指数水平/非农总人数与供应商同比/新增人数直接比较。无精确匹配的指标记录缺口，不扩大列表。官方原始数据无需额外请求即可提供的信息优先复用。

### 6. Research 内容按 section 和观点层级交付

Morningstar 正文继续标记 `LICENSED_API_CONTENT`，只用于用户有权访问的内部研究。`pdf_url` 即使未来可用也只保存为 locator，不自动抓取。评级 Summary 只做一页有界机构维度和一页分析师维度；`num` 按官方 1–20 校验，分页未尽即保留 gap。第一阶段不追逐每个 UID 的全部详情。

`RESEARCH_REPORT` 可以引用：

- 目标价/评级共识；
- 机构/分析师评级 item；
- 有正文的 Morningstar section。

它必须区分供应商观点、预测、估值假设和未独立核实转引。单一 Morningstar 来源不能满足“多份独立研报比较”。

### 7. Capability 路由采用 dataset + semantic field 显式表

替换当前仅靠少量字段集合/前缀的隐式选择，建立可测试映射：

| Capability | Moomoo datasets |
|---|---|
| `FUNDAMENTAL_EVENT` | company profile、revenue breakdown、executives 与已批准事件/资本配置补充 |
| `RESEARCH_REPORT` | analyst expectations、rating summary、Morningstar sections |
| `OWNERSHIP_DISCLOSURE` | institutional aggregate、insider holder/trades、short interest |
| `MACRO_CONTEXT` | approved macro actual/history、economic calendar、Dot Plot fallback |
| `MARKET_STATE` | broad/ETF snapshot fallback、option market statistics、FedWatch |
| `OPTIONS_FLOW` | selected option snapshot、option volatility、per-security capital flow/distribution |

在现有选择器中维护小型 dataset/semantic field 映射；证券、source family、cutoff 和批次可用性仍由既有校验负责，不把动态 ID/时间展开为通用六维规则引擎。Macro/Market 的 provider scope 同步允许合格 Moomoo 补充；新增公司事实/日程按明确来源层级接入既有 Company 输入或事件专项，行业材料按既有 `INDUSTRY_COMPARISON` 输入约束处理，不能将所有资料塞入 `RESEARCH_REPORT`。不改变 SEC 原始事实的定义。

旧 `common-stock-research` 的 Company Analyst 启动目录只展示没有专门能力消费者的公司资料；研报、所有权、Macro、Market 与 Options 数据仍留在冻结 Gate，由上述多维专项消费。此处不建立第二份 Gate 或数据副本，只在现有启动目录做 dataset 过滤，避免动态期权和评级明细挤占公司研究上下文。

准备阶段复用现有 provider coverage，并增加集中式 `capability_routing` 观察，逐 dataset 记录采集、Gate 合格、目标任务交付数量与排除原因。过期、去重、主源覆盖、本次专项未启用和预算裁剪属于合理排除；只有本次启用能力按规则应接收且无合法排除原因的合格 Evidence 未进入任务时，才报告 `CAPABILITY_EVIDENCE_NOT_ROUTED`。选入 `allowed_evidence_ids` 仅证明交付，`actual_research_use_status` 在准备阶段保持 `NOT_EVALUATED_AT_PREPARATION`，实际研究使用另依据有效报告引用与对应解释核验，不要求模型引用每条资料，也不为无引用自动追加模型运行。

### 8. 验收按纵向切片进行

新增或变化部分通过聚焦 fixture/schema/PIT 测试与有界 Quote 验证，复用有效旧证据。使用同一确认 Handoff 验证至少一只普通股的动态 options snapshot 进入 `OPTIONS_FLOW`；Company、Macro、共享 Market 分别至少一项资料通过正式链路交付并被报告正确引用/解释，允许来源为 SEC、Yahoo、官方宏观或 Moomoo。逐域保留完整覆盖/缺口清单，最低样本不等于所有指标覆盖完成。候选与增强项的取舍结果必须齐全；受限项不能掩盖核心消费路由未完成。

若三个域之一因所有适用来源均不可用而无实际使用证据，保留具体阻塞，不用其他域替代。仅 Moomoo 不可用而既有主源可满足该域时，允许该域通过并明确 Moomoo 限制。独立复核和人工完成批准仍按既有流程执行。

直接 AAPL Spike 继续作为可行性证据，不替代持仓闭环。真实 Smoke 只能按仓库运行手册从宿主 launcher 启动；普通开发测试不隐式运行产品、模型、Regression 或 Promotion。

## Risks / Trade-offs

- [官方 v10.11 文档先于可安装运行版本] → 维持 exact runtime pin，分别保存 documented/runtime contract，只批准真实字段。
- [期权链规模大且快照字段时点不同] → 确定性选择最多 48 个合约；价格与衍生字段分开 PIT，不把全链注入模型。
- [免费权限随账号、证券和时段变化] → capability/dataset 级失败隔离，保留 `ENTITLEMENT_REQUIRED` 和实际字段覆盖，SEC/Yahoo/官方宏观继续运行。
- [Macro 数据缺上游来源、时区或历史 vintage] → 仅作 SECONDARY_VENDOR；无法核实时 published_at 保守退回 retrieval，禁止历史回填。
- [Morningstar 内容体积和许可] → section 级有界内容、响应大小限制、内部研究标记，不自动获取 PDF。
- [评级嵌套 item 数量远大于 page size] → 页数和 outer entity 同时设限，保存 inner item 数量与未完成分页。
- [显式消费映射增加维护成本] → 映射集中版本化并由正反测试保护，收益是避免已采集资料静默不可见。
- [Moomoo current snapshot 与 Yahoo 历史系列时间不同] → 不静默拼成同一快照；需要跨源比较时保留各自时间和允许偏差。

## Migration Plan

1. 先完成取舍清单与已有响应复用，再扩展必要 manifest/normalizer 和聚焦测试；仅契约实际变化时升级对应 schema/version/hash，不统一升级无关组件。
2. 逐接口完成当前锁定 SDK/OpenD 的只读 Spike，并记录字段/权限/PIT 差异；失败能力不进入批准 manifest。
3. 接入 Collector、来源选择、逐股冻结包和 provider coverage；默认仍允许 Moomoo 失败而 SEC/Yahoo/官方宏观继续。
4. 更新 capability 路由、Gate/MCP 和聚焦消费测试，再启用正式入口中的新数据集。
5. 按运行手册执行用户批准的持仓纵向 Smoke 和独立复核；未通过不归档。
6. 回滚时停用新增 capability 或恢复前一 manifest/source-plan/topology 指针；旧缓存、旧 Evidence、SEC/Yahoo、官方宏观和历史兼容 profile 保持可读。

## Open Questions

- 官方可安装 SDK/OpenD 的 v10.11 发布版本与发布时间目前尚未出现；它只影响未来 runtime manifest 升级，不影响当前 `10.10.7008` 纵向实现。
- 不同 Moomoo 区域/账号对 Morningstar、Macro 和美股期权字段的长期免费权限可能变化；以每批 capability coverage 和稳定失败码为准，不写死为永久可用。
