# SEC + Yahoo + Moomoo SG 研究补充层

本文记录 `capture-futu-client-research-data` 的实现边界、来源准入、OpenD 操作方式与真实验证结果。它是开发和运维说明，不代表 Change 已完成全部三源验收。

## 当前结论

- SEC 和 Yahoo 沿用既有只读 transport、缓存、证券绑定与 Evidence 体系；新增资料进入独立 `research supplement` sidecar，不修改 `live-snapshot/4.0.0` 的基础四源枚举。
- Moomoo Singapore 使用官方 `Moomoo OpenAPI + OpenD`。账号登录、首次 API 问卷与协议由用户在 OpenD 内完成；项目只连接 `127.0.0.1`/loopback Quote API，不读取 Cookie、Token、密码、Keychain、客户端数据库或交易解锁信息。
- Runtime 只实例化 `OpenQuoteContext`，不创建 Trade Context，不调用账户、持仓、资金、订单或交易接口，不提供任意 SDK 方法透传。
- Cookie 重放、Charles 抓包、网页私有端点和客户端协议模拟已退出主方案。官方 API 缺少或无权限的数据记录真实限制，不自动回退到私有接口。
- 2026-09-16 已以未开户 Moomoo SG 平台账号验证本机 OpenD：状态 `READY`、Quote 登录为真、server version `1010`、SDK `moomoo-api 10.10.7008`。

## 来源与准入

| 来源 | 官方说明 | 用途 | 自动化边界 | 当前结论 |
|---|---|---|---|---|
| SEC | [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)、[Form 13F Data Sets](https://www.sec.gov/files/form_13f.pdf) | submissions、Companyfacts、Archives、13F、Forms 3/4/5、原始申报 | 只读 GET、标识 User-Agent、有界请求与缓存；不使用申报提交 API | `AVAILABLE`；AAPL 基础披露、最新 10-K、Form 4 与 Berkshire 两期 13F 已真实验收，分部样本保留实际解析限制 |
| Yahoo | [Exchanges and data providers](https://help.yahoo.com/kb/SLN2310.html)、[Download historical data](https://help.yahoo.com/kb/sln2311.html) | OHLCV、公司行动、期权、公司档案、日历、预期和空头快照 | 仅允许既有固定域名/path/modules，关闭重定向，受 source access 预算约束；匿名 crumb 只驻留同一内存会话 | `AVAILABLE`；AAPL/SPY 日线、AAPL QuoteSummary 和两个到期日动态期权已真实验收 |
| Moomoo SG OpenD | [OpenD Overview](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-intro.html)、[Authorities and Quota](https://openapi.moomoo.com/moomoo-api-doc/en/intro/authority.html)、[Quote API Overview](https://openapi.moomoo.com/moomoo-api-doc/en/quote/overview.html) | 公司档案、资金流、分析师共识/评级、Morningstar、机构/内部人、空头资料和期权静态链 | 官方 SDK、loopback、Quote-only、版本化方法 allowlist；每方法当前最多 1 次正式纵向验证，无远程 OpenD | `OPEND_QUOTE_FEASIBLE`；11 个 AAPL 研究/元数据方法真实成功，动态期权字段明确不可由静态链替代 |

Moomoo API 权限与 App 权限不完全一致。方法在官方文档中存在不等于当前账号有 entitlement；每项必须保留真实成功、部分字段或准确失败状态。

## 架构与安全边界

```text
stock_agent research request
  → DatasetSourcePlan
  → MoomooOpenDQuoteClient
      → loopback check (127.0.0.1:11111)
      → exact SDK/OpenD version check
      → MoomooQuoteCapabilityManifest allowlist
      → OpenQuoteContext only
      → response schema / row / byte / security checks
  → deterministic JSON + raw SHA-256
  → Moomoo normalizer
  → supplement Evidence / PIT Gate / frozen MCP
  → existing research Skill
```

关键实现：

- `product/mcp/live/moomoo_opend.py`：loopback、Quote-only allowlist、版本、预算、序列化、敏感字段扫描、缓存与方法级熔断。
- `product/mcp/live/moomoo-opend-quote-manifest.json`：已批准的官方方法、参数、响应字段和预算；当前只含已经真实验证的方法。
- `product/mcp/live/moomoo_normalize.py`：将官方 DataFrame/dict 响应转换为供应商语义 Evidence。
- `product/mcp/live/research_supplement.py` 与 runtime schemas：能力矩阵、批次、背景包、PIT 与冻结查询。

Manifest 当前批准：

- `get_global_state`
- `get_company_profile`
- `get_capital_flow`
- `get_research_analyst_consensus`
- `get_research_morningstar_report`
- `get_shareholders_institutional`
- `get_insider_holder_list`
- `get_insider_trade_list`
- `get_option_expiration_date`
- `get_option_chain`
- `get_research_rating_summary`
- `get_short_interest`

未知方法、额外参数、非 `US.*` 证券、远程 host、SDK 版本漂移、Trade Context 或账户/交易语义均在调用前拒绝。

## 本机使用方式

1. 用户自行安装并启动 Moomoo OpenD。
2. 用户在 OpenD 内使用 Moomoo SG 平台账号登录并完成 API 问卷与协议。
3. 保持 Quote service 状态为已登录；默认监听 `127.0.0.1:11111`。
4. 项目使用 `moomoo-api==10.10.7008`；依赖已加入 `pyproject.toml` 的 `live` extra 和 macOS/Python 3.13 锁文件。
5. 首次运行先读取 `get_global_state`，核对 `READY`、`qot_logined=true`、server/SDK 版本，再调用批准的数据集。

项目不需要 Moomoo Key、Cookie 或配置文件。用户退出 OpenD 后，新请求自然返回 `OPEND_UNREACHABLE`；既有冻结 Evidence 与 SEC/Yahoo 不受影响。

官方 Python SDK 默认在用户 Moomoo 日志目录写运行日志。该日志由 SDK/OpenD 管理，不进入仓库、Evidence 或模型上下文；受限环境必须显式允许该官方目录，不能通过读取其中内容获取认证信息。

## 2026-09-16 真实 OpenD 验证

测试证券为 `US.AAPL`，研究身份为 `US:COMMON_STOCK:AAPL`。原始响应只存于本机 `/private/tmp` 隔离缓存；仓库记录 hash、结构和限制，不提交 Morningstar 正文。

| 方法 | 结果 | 结构 | 本轮示例 raw SHA-256 | 已确认限制 |
|---|---|---|---|---|
| `get_global_state` | 成功 | dict | `5e98379147cc2e2240e8b11f1b60752899c867faa96b020d792a44b8d437db62` | 只证明当前 OpenD/Quote readiness，不外推其他方法权限 |
| `get_company_profile` | 成功 | 18 行长表 | `5276b55dbf604088e37309cda519aacd9a6e1c4c98b00937a9892cf3803795c5` | 当前供应商档案、界面语言相关；法定名仍以 SEC 为主，员工/高管缺历史生效区间 |
| `get_capital_flow` | 成功 | 391 行分钟序列 | `495dc48601b516c56940106bd906ad269ea0e51122ad92b8854e1422f7ecfc10` | 形成 overall/特大/大/中/小五类唯一 Evidence；intraday 的 block order 为 `N/A`；供应商时钟约领先本机 10 秒，原值保留并记录 gap |
| `get_research_analyst_consensus` | 成功 | dict | `bef0becc352ab9e2d14f1a8ce8e7a8190d148d9879640729f877462d85b545d5` | 当前评级/目标价观点；无财政期、会计口径和历史 vintage，不能生成历史预期差 |
| `get_research_morningstar_report` | 成功 | dict | `de0cf7f79c0d33d831977bffe7d9bfe119e68f1d3f043984fb96f5abd406798a` | 供应商研究观点；仅限内部研究，不声明再分发许可；单份内容不构成研报对比 |

资金流真实修复验证：5 个可用分类生成 5 个唯一 Evidence ID；`main_in_flow` 不可用和供应商时钟偏差均显式保留，未补零、未推断机构买卖方向。

扩展 Quote-only manifest hash 为 `1c8259cb75f1edda2475a0658dd47c12e1a3147bf7dc1fc4b52be3439c03be17`。同日正式适配器完成以下 Capture → Normalize 检查：

| 方法 | 返回规模 | 扩展 manifest 下 raw SHA-256 | 标准化结果与限制 |
|---|---:|---|---|
| `get_shareholders_institutional` | 20 期 | `39b4a019cfbddb630b647e466e67c446ff77825cb54e8f5f90bb8ea75d4e528d` | 20 个唯一 Evidence；是供应商期间聚合，不是逐管理人 13F，当前季度标签不推定为已结束季度 |
| `get_insider_holder_list` | 18 人 | `6f8e448f0c83b8ca5ed122e998bd87da361772a9f6f60ba0e44d4cabf2e47ce5` | 18 个唯一 Evidence；公开披露人名保留，但持股数缺独立 `as_of`，以当前快照并记录 gap |
| `get_insider_trade_list` | 20/199 条 | `e40ff37616787c25b4a5ff920fcf3955205457fc18ed596ae3478a2d3f6a4b4f` | 20 个唯一 Evidence；保留 `next_key` 和总数，交易区间/供应商分类不替代 SEC Form 3/4/5 字段 |
| `get_option_expiration_date` | 25 个到期日 | `f0d8967264d346eb658685f1cc031721268a5dc9d4b48bc6cf501f8c8a9ac0f2` | 证明到期日可发现；不等于动态行情权限 |
| `get_option_chain` | 最近到期 94 个合约 | `19fdb47aca90ad389b4c80367647c71b04802e68ce377ecb1f65b5e09c2cb1a8` | 94 个唯一静态合约 Evidence；无 bid/ask/last/volume/OI/IV/Greeks，明确记为 `STATIC_CONTRACT_CHAIN` |
| `get_research_rating_summary` | 20 个机构、291 条评级项 | `5ae9bcb9b9530d1d63eaf0ec140e174bfd1c4372a3eda163fe1d0b7250e5c4e4` | 291 个唯一 `RATING_SUMMARY` Evidence；仍有后续页，评级摘要不冒充研报正文 |
| `get_short_interest` | 20 期 | `58bcdf98b9c2acd6602581520dd7f643f8b55f67d3b903cdeb7ce8dcad06a428` | 20 个唯一 Evidence；与 short volume 分离，不推算借券费率或挤空评分 |

DataFrame 分页元数据会进入确定性序列化的 `attrs`；机构、内部人、评级和空头资料的 `next_key` 均保留。SDK 的 `get_short_interest` 返回美股和港股两个 DataFrame，US manifest 只接收美股结果，不混入港股分支。

Moomoo 端到端冻结验收另以当前 manifest 重新读取公司档案、资金流与分析师共识，并完成 Capture → Normalize → PIT package → `research_supplement.query`。资金流只接纳 `capital_flow_item_time <= retrieved_at` 的最后完整分钟桶；尚未完成或位于检索时刻之后的桶被排除并记录 gap，Evidence `as_of` 精确等于已完成区间的 `period_end`。若供应商 `last_valid_time` 领先本机检索时刻，原值仅保留在 gap，事实内 `provider_valid_time` 置空，绝不把未来时间钳制后伪装成已知事实。

## 2026-09-16 真实 Yahoo 验证

测试证券为 AAPL，基准为 SPY；`yfinance==1.7.0`、`exchange-calendars==4.13.2/XNYS`。首次直接 QuoteSummary/期权请求得到真实 `YAHOO_HTTP_401`，随后通过既有固定 `fc.yahoo.com` 与 `/v1/test/getcrumb` 白名单建立匿名会话。crumb 仅在内存传给同一有界 session，传输层在事件与缓存 key 中移除 crumb；不读取登录 Cookie、不自动同意条款。

| 数据集 | 结果 | 真实规模与 hash | 语义与限制 |
|---|---|---|---|
| AAPL 日线基线 | 成功 | 2026-08-03 至 2026-09-15 共 31 个已完成交易日；canonical raw hash `804ad2cd67f10ffd789ec2ae2ccbcfad5a1784779aa1b5a0b3ca111c99beb91c` | USD、`America/New_York`、provider close；不是实时价 |
| AAPL 研究序列 | 成功 | 2026-07-01 至 2026-09-15 共 53 日、319 个字段 Evidence；raw hash `8766adb87f52de96a56adbc7fdd98e39b7cbcc883e1b13af5eb2b1ff989869d6` | 每日 open/high/low/close/adjusted close/volume；53 个 adjusted-close 可用于历史回报，识别 1 个现金分红事实 |
| SPY 基准序列 | 成功 | 53 日、318 个字段 Evidence；raw hash `80c1090fd9ffd0ef216b3140baa63305338729d381a5122d4cd26ef1c95a43f3` | 与 AAPL 使用同一 XNYS 日历、时区和 cutoff |
| AAPL QuoteSummary | 成功 | 6 个 Evidence；wire raw hash `eaa1896ac3c0699122492bb51ec13b7ac6da96ad08ade3fa908c3c0b0f93c220` | 覆盖档案、财报日历、预期/修订、评级分布、空头快照和分红；均为当前供应商快照，无历史 vintage 不生成历史预期差 |
| AAPL 动态期权 | 成功 | 到期日 2026-09-16、2026-09-18，共 274 个唯一合约；wire hashes `f7542fd340852bee0d64ded2bfd24f7bce98bbf96feec422babcce8b062da6ae`、`ec362739c57ae106bb6b18f9ab539eac5ec3bc1c4d5724b5316039cd9a0fa5d5` | last/IV/OI 274，bid 273，ask 274，volume 270；Greeks 与 multiplier 缺失逐合约记 gap，不推断方向 |

Yahoo 与 Moomoo 的期权响应保持为两份独立快照：Yahoo 提供动态字段，Moomoo 当前已验证方法只提供静态合约属性，二者不按行静默拼接。

## 2026-09-16 真实 SEC 验证

SEC 联系信息只在运行时进入 EDGAR `User-Agent`，未写入仓库、缓存键、Evidence 或验收记录。AAPL 基础披露在 10 次有界请求内完成：submissions raw hash `cb90ffafc5b6f997b60aa109e07008223ad35abe896ec7918fd43652b4057329`，Company Facts raw hash `73a86c6aedc31f77cac2ea4df5f80f0b3bd7e6eb58bb4e01444fbedf3afb9c43`。共读取 1,000 个当前 submissions filing 与 15,068 条原始财务事实，标准字段/期间选择形成 744 条 live financial/derived Evidence；未支持 taxonomy、累计季度、重述歧义和覆盖窗口均以 gap 保留。

最新 AAPL 10-K 为 accession `0000320193-25-000079`，公开时间 `2025-10-31T10:01:26Z`，原文 hash `548ae59778cf08ee0f2ee088e7ece20d947076c3c01f74d2d65db4c2777e436a`，六个白名单章节均取得。真实 iXBRL 同时包含维度化文本节点、无效数值节点及隐藏层/展示层重复事实；解析器现跳过无 `unitRef` 文本、把坏数值记录为 gap，并按解析后 Evidence ID 去重。最终有界输出 200 条带 axis/member、期间、单位及抵销语义的分部事实；没有用 Company Facts 合计值复制或推断分部收入。

所有权样本同时取得：最新 AAPL Form 4 accession `0001140361-26-036226` 形成 1 条内部人 Evidence，raw hash `dc11428ca10523d8c53a10ffa631dd0ac62f659a025b9bff24967d08d029e7b1`。Berkshire Hathaway（CIK `0001067983`）2026-06-30 与 2026-03-31 两期 13F 信息表各保留 12 条 AAPL 相关行，raw hashes 分别为 `6a2798aa0fa9731c33b0f0b748229eaf7cdf118f9c46fd5a4a9a3de6979d4d95`、`47b2bdae43512763cbd6459b6980827fc0a4fdc05515b4609950a7ab52b55316`，比较 hash `5b833089cd5bef058677aee2b4d331d5d77183610735b150657baeceeb6993fb`。多行同 CUSIP 按同一 `shares_or_principal_type/put_call` 汇总；混合持仓类型拒绝直接比较。该结果只代表指定管理人和已映射证券，不代表全市场机构趋势，且未自动拆股回溯调整。

## 同标的三源冻结包

同日对 `US:COMMON_STOCK:AAPL` 重新执行修复后的 SEC + Yahoo + Moomoo SG 联合冻结，截止时间为 `2026-09-16T15:08:54.394877Z`。SEC 使用四次请求取得当前身份、Company Facts、最新 10-K 与章节；Yahoo QuoteSummary 使用三次匿名请求；Moomoo OpenD 在同一 client 先通过 readiness，再读取公司档案、盘中资金流与分析师共识。联系信息和原始响应均未进入仓库。

联合批次 hash 为 `0265cdeb8b3b203918c152f98850eb6c16cbdee00a4381be4acd394fb4c3132e`，背景 snapshot hash 为 `e57286357d95db140152efba356fe8826c4db9a5a2b87893430ed9aad846cd25`，package hash 为 `4f264957f9212e6f78fe0aca1665815187c8359b40c14d88fcd6eff485ed6a0e`。包内共有 228 条 Evidence；一次 `research_supplement.query` 返回 27 条，result hash `935439e1745071b2ea05b2557c0b7d45122f5b475c3d2023c4f40feaa3eee742`，来源集合精确为 `sec/yahoo/moomoo_sg`。15 条 capability 与 10 条来源选择覆盖全部实际尝试，并绑定 Evidence ID、raw hash、请求预算和同一 batch；全部事实的 `as_of/published_at/retrieved_at` 均未超过 cutoff。

十组背景真实覆盖如下：

| 背景组 | 状态 | Evidence | 实际边界 |
|---|---|---:|---|
| 身份与公司档案 | `PARTIAL` | 3 | SEC 法定身份与 Yahoo/Moomoo 当前业务简介并列；供应商分类与员工数不回填历史 |
| 业务与分部 | `PARTIAL` | 200 | Apple 最新 10-K 的明确维度事实；保留 axis/member、期间、单位、抵销与重复去除 gap，不以合计数伪造收入构成 |
| 管理层与治理 | `SOURCE_LIMITED` | 0 | 冻结章节已取得，但本轮未形成人工引用核实后的治理 claim |
| 重要关系 | `SOURCE_LIMITED` | 0 | 不从同行或匿名披露猜测客户/供应商身份 |
| 财务历史 | `PARTIAL` | 14 | SEC 核心收入、利润、资产负债、现金流、Capex/R&D 等最新适用事实；重述和累计季度限制保留 |
| 资本配置 | `PARTIAL` | 1 | Yahoo 当前分红快照；实际分红/回购仍以 SEC 原文为主 |
| 业绩与指引 | `NOT_ATTEMPTED` | 0 | 没有把 Yahoo 财报日历或市场预期误标为发行人指引 |
| 分析师预期 | `PARTIAL` | 3 | Yahoo 趋势/评级与 Moomoo 共识并列；历史 vintage 与财政期口径不完整 |
| 事件背景 | `PARTIAL` | 1 | Yahoo 财报日历经 SEC 主来源显式受限后单次回退；估计日期不是公司指引 |
| 股本与空头背景 | `PARTIAL` | 1 | Yahoo short-interest 快照；不推算借券费率或挤空评分 |

该包可以回答公司主营业务、已披露收入分部和当前财务基线；重要客户/供应商依赖仍以明确未知项返回。额外数据集包含 5 条 Moomoo `VENDOR_CALCULATED_FLOW` Evidence，全部来自截至 `2026-09-16T15:08:00Z` 的最后完整分钟桶，证明核心延期增量，而不把正负号解释为真实机构买卖方向。

## 数据集来源计划

权威计划位于 `product/mcp/live/research-supplement-source-plan.json`。每个数据集只有一个 primary 和至多一个 fallback；补充来源只提供并列证据。

- `vendor_money_flow` 只能来自 Moomoo SG OpenD，SEC 13F 或 Yahoo volume 不得替代。
- `options_snapshot` 先 Yahoo；只有 Yahoo 明确失败且 Moomoo 对应 Quote API 已逐项验证时才单次回退。
- `institutional_ownership` 以 SEC 原始 13F 为主，Moomoo 只能保留为二级供应商资料。
- `insider_transactions` 以 SEC Forms 3/4/5 为主，Moomoo 仅作为并列的二级供应商补充，不参与失败回退。
- 档案、财务、分部和治理以 SEC 为主；Moomoo 当前摘要不能冒充历史原始披露。

## Background 与 Skill 接入

| Input | Tool/Data | Skill/Reasoning | Structured Output | Eval |
|---|---|---|---|---|
| `CompanyBackgroundSnapshot` 十组资料 | `research_supplement.query` | `company-research`：解释商业质量和依赖，不补猜缺口 | 既有 company research 报告引用 Evidence ID | 身份、PIT、引用闭合、未知项保持未知 |
| SEC 13F/Forms 3/4/5 与 Moomoo 二级资料 | 冻结 ownership Evidence | `ownership-disclosure` | 所有权披露结论 | 不把单一管理人或供应商汇总当全市场 |
| Yahoo/Moomoo 期权快照 | 冻结 options Evidence | `options-market-structure` | 期权市场结构结论 | 不推断买卖方向，不拼接不同时点 |
| Moomoo Morningstar/评级与 Yahoo 候选 | 冻结 research Evidence | `research-report-analysis` | 研报观点分层 | 单篇不标比较完成、许可限制保留 |
| 事件与财报日历 | 冻结 event Evidence | `catalyst-analysis` | 事件场景 | 估计日期与公司确认分开 |

采集层只形成事实、供应商观点、来源限制和结构化缺口，不输出护城河评分、管理层质量评分、交易动作或组合决策。

## 回滚与剩余验收

回滚 Moomoo 新能力时，禁用 `MoomooOpenDQuoteClient` 或将 manifest 移出批准版本；用户也可直接停止 OpenD。旧 live snapshot、SEC/Yahoo 和已冻结合格 Evidence 保持可读。

### 截图持仓 v5 自动接入

正式 `collect-common-stock-data` 入口现会在基础数据 cutoff 冻结前有界采集 Yahoo 与 loopback OpenD，随后用同一确认 Handoff 的 SEC Gate 事实为每只普通股构建补充包。多证券包写入 `research-supplements/<security>/`，`data-preparation.json` 和 `source-bundle.json` 保存逐股引用及 hash；旧根目录单股 sidecar 仍可读取。缺文件、证券串包、重复证券、路径越界、cutoff 或 hash 漂移均使重建失败。

`capture-futu-client-research-data-20260917-v5` 已为 ALB、MRVL、WOLF 生成 265/265/217 条补充 Evidence。三只均有 SEC、Yahoo、Moomoo SG、公司档案、业务原文候选、财务历史、资本配置、指引候选、分析师预期、事件、空头背景和 5 条供应商资金流；治理与重要关系保持 `SOURCE_LIMITED`。source bundle 重建、逐股 preparation/Gate 闭合、补充 MCP 和通用 Gate 查询均通过。ALB 单股正式运行包也已准备完成，dispatch catalog 可见 265 条补充事实及 `moomoo_sg/vendor_money_flow`。

当前验收结论：

- 首次经用户授权的 GPT-5.6 Terra 专项消费检查暴露了资金流未来分钟桶缺陷，该结果按真实失败保留且不计为有效验收。
- 用户再次明确授权后，修复后的替代运行只消费 v2 冻结输入，输出中文与 JSON，结果为 `PASS`。确定性复核确认 23 个引用全部闭合、三源语义与 PIT cutoff 保持、事实/预测/观点分离、覆盖缺口保留，且未启动 Skeptic、CIO、Risk 或完整 Council。记录见 `reviews/development/capture-futu-client-research-data-terra-consumption.json`。
- 独立 Reviewer 首轮结论为 `CHANGE_REVIEW: FAIL`；修复完成后，同一 Reviewer 对最新差异和 v2 冻结包给出 `CHANGE_REVIEW: PASS`。
- 截图持仓旧 v3/v4/v8 仅用于故障证据：v3/v4 提前退出，v8 的 Stop Hook 已阻止提前结束，但在单项 900 秒预算前被人工中止，不能据此判定模型或 MCP 失败。
- 普通股父线程现禁止对仍运行且未请求协助的子任务反复 follow-up/list，并使用覆盖冻结单项预算的长等待；Stop Hook、批次超时和 finalizer 继续 fail closed。
- 正式 ALB 模型运行尚未启动。该步骤会把持仓与冻结研究数据发送给外部模型，当前安全审批要求用户在知情后明确授权；没有授权时只保留本地 PREPARED 包，不绕过、不生成替代报告。
- Change 当前仍在实施中；取得外发授权后须先完成 ALB，再完成三只合法报告、新数据实际查询/引用和当前差异独立复核，最后申请人工完成批准。此前不得归档、提交或推送。

未运行的 Replay、Eval、Regression、Promotion 和完整 Council 不标 PASS；取得人工完成批准前不归档、提交或推送。
