# Company / Macro / Market 最低数据集覆盖清单

记录日期：2026-09-19
对应 Change：`align-macro-market-company-research-inputs`
用途：在增加采集器前冻结本次交付范围、已有能力和真实验证缺口；本表不是 provider 永久可用性承诺，也不把历史成功等同于当前批次可用。

## 状态口径

- `IMPLEMENTED_HISTORICALLY_VERIFIED`：确定性链路存在，且仓库已有真实采集或真实消费证据；本 Change 仍须在同一 Handoff/cutoff 下重新验证核心项。
- `IMPLEMENTED_PENDING_CURRENT_VALIDATION`：已有适配器、契约和测试，但没有本 Change 的真实返回与对应研究消费闭环。
- `IMPLEMENTED_CURRENTLY_VERIFIED`：本 Change 已保留真实返回 hash、实际请求与冻结 Evidence；仍不等于供应方永久可用或 Runtime Smoke PASS。
- `IMPLEMENTED_CURRENTLY_SOURCE_LIMITED`：链路和有界尝试已完成，但真实返回受配置、授权或正文范围限制。
- `PARTIAL`：已有部分字段或资料形态，但尚未满足本表的核心字段、覆盖或消费要求。
- `NOT_IMPLEMENTED`：当前没有可从正式入口自动装配的确定性适配器。
- `ENHANCEMENT`：不阻止核心三域闭环；只能准确记录为可用或受限，不能替代核心项。

所有事实仍须具有 `source_id`、`as_of`、`retrieved_at`；有公开时间的资料还须保留 `published_at`，并经同一 `decision_cutoff` 的 PIT Gate、冻结 MCP 和对应报告引用闭合。

## Macro

| 数据集 | 层级 | 当前状态 | 必需字段与时间语义 | 范围 | 主/备来源与预算 | 正式消费位置 | 本 Change 验证条件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CPI 与就业 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | series、观察期、值/单位、`as_of`、保守 `published_at`、`retrieved_at`；公开 v1 无 historical vintage 必须明示 | US shared market | BLS Public API v1；三序列合并 1 个正常请求 | `MACRO_CONTEXT` / `runtime_market_catalyst` | 本 Change 真实 HTTP 200、冻结 Evidence 与 cutoff 过滤 |
| 美国国债收益率 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | tenor、交易日、收益率、观察/获取时间；无精确发布时间时采用保守获取时点 | US shared market | U.S. Treasury Daily Rates；1 个年度 CSV | `MACRO_CONTEXT` / `MARKET_STATE` | 本 Change 真实 HTTP 200，失败与其他官方源隔离 |
| 经济活动 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | 非农就业总量作为当前免费活动指标；period、value/unit、保守发布/获取时间与无 historical vintage 限制；GDP/PCE 不列为本次核心 | US shared market | 与 BLS 其他序列合并 1 次请求 | `MACRO_CONTEXT` | 真实返回、冻结与修订限制均已记录 |
| 央行政策原文 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | 文档身份、标题、正文、官方 RSS pubDate、获取时间与 raw hash | Federal Reserve, US | RSS 1 + 最新适用正文 1 | `MACRO_CONTEXT` | 本 Change 真实 HTTP 200，原文 locator/hash 已记录 |
| 已公布发布日历 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | VEVENT、官方时区、状态、获取时间；不预测 | BLS, US | BLS iCalendar 1 次 | `MACRO_CONTEXT` | 本 Change 真实 HTTP 200 并冻结 180 天有界日程 |
| historical vintage、全球央行与地缘材料 | ENHANCEMENT | `ENHANCEMENT` | 明确 vintage、修订和报道/原文属性 | 按取得范围 | ALFRED/FRED 或官方来源；不因缺失轮换无界来源 | `MACRO_CONTEXT` | 可准确 `SOURCE_LIMITED`，不阻断核心 US 闭环 |

## Market

| 数据集 | 层级 | 当前状态 | 必需字段与时间语义 | 范围 | 主/备来源与预算 | 正式消费位置 | 本 Change 验证条件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 大盘与相关板块基准 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | 90 天日收盘、ticker/role、获取时间；ETF 代理显式标识 | SPY + 11 个 Select Sector ETF | Yahoo chart；每 ticker 1 次 | `MARKET_STATE`；单股相对结构仍属 `TECHNICAL_STRUCTURE` | 本 Change 12/12 序列真实返回并冻结 |
| 跨资产代表序列 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | TLT/UUP/GLD/USO 日收盘、观察/获取时间和 ETF 代理限制 | 债券、美元、黄金、原油 | Yahoo chart；每 ticker 1 次 | `MARKET_STATE` | 本 Change 4/4 真实返回，不冒充现货/原值/资金流 |
| 波动 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | 大盘确定性历史波动 + VIX 独立序列 | US broad market | Yahoo + `market-state-calculation` | `MARKET_STATE` | 本 Change 真实 VIX 序列及已有确定性计算闭合 |
| 信用指标或明确代理 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | HYG 日线作高收益信用 ETF 代理，明示非 spread/债券现货/资金流 | US credit proxy | Yahoo chart 1 次 | `MARKET_STATE` | 本 Change 真实返回并冻结 |
| 过去 24 小时市场新闻 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | canonical URL、publisher、title、`TITLE_ONLY`、published/retrieved；不冒充正文 | shared market | Yahoo search 1 次/40 候选 | `MARKET_STATE` | 真实请求成功，24h 去重后 0 条并保留 `MARKET_NEWS_WINDOW_EMPTY` |
| 专有仓位、实时全市场宽度、商业指数/付费新闻全文 | ENHANCEMENT | `ENHANCEMENT` | 仅按真实授权和时间语义登记 | 未承诺 | 无默认来源 | `MARKET_STATE` | 缺失不阻断核心项，不得由 Moomoo money-flow 或新闻摘要冒充 |

## Company

| 数据集 | 层级 | 当前状态 | 必需字段与时间语义 | 范围 | 主/备来源与预算 | 正式消费位置 | 本 Change 验证条件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 身份、申报与财务事实 | CORE | `IMPLEMENTED_HISTORICALLY_VERIFIED` | CIK/ticker/security、form/accession、accepted/period、XBRL value/unit、获取时间、原文 locator | 全部确认普通股 | SEC submissions/companyfacts/filing；身份、submissions、companyfacts 各 1 次，必要正文最多 2 次，暂时故障各最多 1 次 | `FUNDAMENTAL_EVENT` / Company Analyst | 当前全部确认普通股同一 cutoff 的 Gate 与报告引用 |
| 冻结行情、当前估值与预期补充 | CORE | `IMPLEMENTED_HISTORICALLY_VERIFIED` | completed-session price、provider/derived 口径、财务期间、预测目标期、获取时间 | 全部确认普通股 | Yahoo；每证券 1 次正常采集，最多 1 次暂时故障重试 | `FUNDAMENTAL_EVENT`，必要时 `RESEARCH_REPORT` 只作背景 | 当前逐股 coverage；与 SEC 冲突并列而非覆盖 |
| 公司公告/IR 正文自动发现 | CORE | `IMPLEMENTED_CURRENTLY_VERIFIED` | SEC earnings exhibit / management discussion 原文定位、实际可查询正文范围 hash、published/retrieved；过滤目录型抽取并按 filing/语义段去重后投影为 `ISSUER_MATERIAL/BODY_VERIFIED` | 全部确认普通股 | 复用 SEC 8-K/附件选择，不额外轮换网站 | `RESEARCH_REPORT` / Company Analyst | v20 定点依赖链、v21 同批三域与 v22 当前版本均实际引用两份去重正文、正文 hash、SEC URL 与 Gate 定位；独立正文仍单列增强缺口 |
| 指引与事件上下文 | CORE | `PARTIAL` | 原文片段/定位、period、metric、management guidance / estimate / fact 分类、published/retrieved | 全部确认普通股 | SEC 为事实锚点；Yahoo、Moomoo SG 按 source plan 补充；每证券/数据集各 1 次 | `FUNDAMENTAL_EVENT` | 当前逐股分类正确、不能把候选文本或共识提升为公司事实 |
| 公司/行业独立研究自动发现 | ENHANCEMENT | `IMPLEMENTED_CURRENTLY_SOURCE_LIMITED` | query、候选身份、作者/机构、published、lead/body 状态和获取时间 | ALB/MRVL/WOLF | OpenAlex；每股实际 1 次查询/10 候选 | `RESEARCH_REPORT` / Company Analyst | 三股均 HTTP 200，正文尝试因 key 准确受限；用户已明确接受本增强项保持 `SOURCE_LIMITED` |
| 独立研究正文 | ENHANCEMENT | `IMPLEMENTED_CURRENTLY_SOURCE_LIMITED` | body hash/章节定位契约已有；搜索线索不进正文 | ALB/MRVL/WOLF 均已尝试 | OpenAlex Content API；需外置 key | `RESEARCH_REPORT` | 三股均为 `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED`，未冒充已读正文；不替代 Company 核心 issuer/IR 正文 |
| Moomoo SG 逐数据集补充 | ENHANCEMENT | `IMPLEMENTED_HISTORICALLY_VERIFIED` | capability/dataset、区域、权限、as_of/retrieved、endpoint version、失败码；不含账户/交易 | 已确认普通股，取决于 SG OpenD 美股 quote 权限 | 本机 `127.0.0.1` OpenD quote-only；每证券/数据集 1 次，不循环登录 | 对应 Company 报告；不承担 Macro/Market 核心来源 | 不可达只降低相应 supplement；不得回退 Cookie、私有接口或阻断 SEC/Yahoo |
| 两期 13F、历史期权结构、可验证资金方向 | ENHANCEMENT | `ENHANCEMENT` | 申报主体发现/两期可比或历史快照与方向语义 | 未承诺完整覆盖 | SEC/Yahoo/Moomoo 能力边界内有界尝试 | `OWNERSHIP_DISCLOSURE` / `OPTIONS_MARKET_STRUCTURE` | 可准确 `SOURCE_LIMITED`；单期或单快照不能声称资金方向 |

## 进入实现的硬边界

1. 核心缺口是：Macro 的经济活动、政策正文和日历；Market 的板块、至少两类跨资产、信用及 24 小时新闻；Company 的逐股 issuer/IR 公告发现、去重正文和真实消费闭环。独立公开研报发现/正文是增强项，不冒充 issuer/IR 核心材料。
2. 现有 BLS/Treasury、SEC/Yahoo/Moomoo、OpenAlex 和计算链优先复用；新增 provider 只服务表中具体缺口，不新增 provider-specific Agent、第二套编排器或通用新闻平台。
3. 第三方 Skill/CLI 只有完成静态审计、固定依赖和有界真实返回后，才可能由确定性 adapter 间接采用；Agent 永不直接执行第三方 Skill/CLI。
4. 本表中的 `PARTIAL` 或历史验证不构成本 Change 的真实三域消费 PASS；v21 已由宿主 launcher 证明同一 Handoff/cutoff 的 8/8 引用闭环，v22 以当前版本再次证明三域核心但准确保留非核心 Options 终止事件失败；两者均不构成来源永久可用或长期稳定承诺。
