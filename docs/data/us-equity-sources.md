# 美股真实数据：来源与访问条件

所属 Change：`us-equity-live-advisory-slice`，Task 1.1。
首次核对日期：2026-09-09；当前说明日期：2026-09-16。本文是工程准入记录，不是法律意见或上游授权证明。

## 2026-09-16 当前：用于 Handoff 数据准备，上游核实保持 UNVERIFIED

用户已批准 Design 2 的当前范围，规范化记录见 [personal-research-approval.json](personal-research-approval.json)。本次只从原准入范围中移除误放的“三股产品上限”，不把产品持仓数量解释成 Provider 授权；canonical JSON hash 为 `84f7f933a5107a2948315ad66ff424b44f6db8773d691668a86a5eb4850f2960`。该记录不含凭据、真实持仓或联系邮箱。

四个来源沿用下文已核对的条件、限制、角色及最小域名，尚未核实的适用性全部明确保留 UNVERIFIED。本次批准不是上游许可、法律结论、免费无限访问保证或最终完成批准，不改变下文历史条款观察。

当前 source-access/snapshot 实际使用 v4：操作者 APPROVED 与上游 UNVERIFIED 分开存储和验证。它服务于从已确认 `PortfolioHandoff v3` 为全部普通股准备冻结数据，不再以“单股→三股完整 Council”为当前产品范围。持仓数量没有产品上限，但请求、时间和计算资源仍有界，未执行项必须显式记录。缺批准、暂停、篡改、超范围、DENIED 或实际 401/403/429 仍停止；批量商业用途、无限抓取、付费订阅或新增域名不在批准范围。

本次请求预算沿用有界路径：NASDAQ 单次默认最多 200 行、单证券采集事务目录请求预算 5；Yahoo 实际 HTTP 预算 12；东方财富备用预算 6；SEC 预算 30。每项事务有界，整批范围由已确认 Handoff 中的普通股集合确定；这不代表应当用完预算、服务授予额度或故障后可重新尝试。临时故障和回退仍按原策略；真实取数与数据准备通过必须另有产物证明。下文临时目录、单次响应和故障过程均为历史技术记录，不是当前运行前置。

下文 `BLOCKED_PENDING_AUTHORIZATION` 和“未确认即停”是旧项目门禁及历史进度，不再覆盖当前双状态规则；旧试拉仍不可转为 Council Evidence。原始许可依据未新增或伪造。

## 2026-09-10 历史：NASDAQ＋主备行情，正式准入仍未解决

最新批准选型：NASDAQ screener 股票池、Yahoo/yfinance 主行情、东方财富/AKShare 受控备用、SEC 披露。后文单源、暂停与旧进度段落均是历史，不能覆盖此选型，也不能证明当前主备入口已经接通。

最新 apply 已接入 NASDAQ 目录、主备采集、来源选择冻结与 `live-us-equity/3.0.0` 运行锁；见 [新版使用说明](../product/us-equity-live-advisory.md) 和 [拓扑版本接缝记录](../../reviews/development/live-topology-v3-verification.md)。这些是确定性实现与合成测试证明，本轮没有请求真实目录或行情。HTTP 200 与个人开发批准均不能替代当前 Specs 要求的来源准入依据。

| source_id | 本次核对 / 缺口 | as_of / retrieved_at |
| --- | --- | --- |
| nasdaq-legal-live-review | [NASDAQ Legal](https://www.nasdaq.com/legal) 全文可读取；第 2、6、7 节涉及采集、个人非商业许可及 AI/数据分析开发用途的书面许可限制。未核实适用于本项目 screener 自动采集、缓存及模型用途的许可或例外，不标 AUTHORIZED | 页面更新 2026-05-11 / 2026-09-10（日期精度） |
| yahoo-terms-live-review | [Yahoo US Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html) 官方搜索索引仍列自动取数需事先明确许可；本次不声称已完成全文/地区适用性审核 | 生效日期未核实 / 2026-09-10（日期精度） |
| yfinance-live-review | [项目文档](https://ranaroussi.github.io/yfinance/) 说明研究/个人用途与非官方身份，并要求核对 Yahoo 数据条款；它本身不是上游授权 | 生效日期未知 / 2026-09-10（日期精度） |

未保存上述网页原始字节，不编造网页 hash；此表是工程准入风险记录，不是认定具体个人用途违法的法律结论。`www.nasdaq.com/terms-of-use` 初次文档读取失败，随后找到并实际读取 `/legal`；不是数据 API 网络故障。

角色与最小数据域名：NASDAQ 仅 `api.nasdaq.com`，Yahoo 仍限已核对 chart/crumb/bootstrap 的三个主机，东方财富仅 `63.push2his.eastmoney.com`，SEC 仍为 `data.sec.gov`、`www.sec.gov`。没有修改 allowlist。各主机技术可达、用途许可与正式完整链路是三项不同证据。

NASDAQ 请求默认单页、至多 200 行，显式预算内分页；20 秒、2 MiB、串行每秒至多一次、不自动重试/跟随重定向。真实分页参数及完整覆盖尚未验证；默认响应 20 行/totalrecords=7139 的旧观察不能替代。目录仅记录证券线索，不提供投资排序、身份保证或历史成员时间。

当前 Yahoo transport 已按新契约将 429 改为立即失败并锁住该调用链；暂时性 5xx 保留有限重试。主备路由已接入 collection，合成输入验证允许回退与禁止回退分支，尚非真实网络可用性证明。费用/额度仍未知；不安装付费数据产品、不承诺免费无限。SEC 沿用下方已核对说明。

`SOURCE_ACCESS_STATUS: BLOCKED_PENDING_AUTHORIZATION`。Task 1.1 与真实目录、单股/三股验收保持未完成；只继续已授权的离线适配。解除正式采集门禁需要覆盖所选端点及使用方式的可核实依据；用户接受工程风险不能被写成不存在的上游许可。

## 2026-09-10 历史：东方财富选型及准入复核

唯一行情选型为东方财富（client=AKShare 1.18.94），SEC 披露不变。下方 Yahoo 选型、依赖和测试段落均为历史，不作为当前来源或回退依据。当前 live 依赖已经迁移；见 [适配记录](eastmoney-adapter-progress.md)。

本次只读取公开文档，没有新增行情或身份 API 请求。正式状态仍为 `BLOCKED_PENDING_AUTHORIZATION`，不把试拉成功和用户选型批准当作上游许可。以下是工程准入判断，不是个人用途是否合法的法律结论。

| source_id | 原始来源 | 核对与具体缺口 | as_of / retrieved_at |
| --- | --- | --- | --- |
| eastmoney-protocol-recheck | [官方服务协议](https://about.eastmoney.com/home/protocol) | 存在行情复制、向外提供及数据用途限制；未取得覆盖本项目自动采集、缓存、发送模型研究的明确准入依据 | 生效日期未核实 / 2026-09-10，日期精度 |
| eastmoney-disclaimer-recheck | [官方法律声明](https://about.eastmoney.com/home/disclaimer) | 数据准确性/及时性无保证，复制传播另有限制；不能承诺免费无限或全市场 SLA | 生效日期未核实 / 2026-09-10，日期精度 |
| akshare-symbol-contract-recheck | [AKShare 美股文档](https://akshare.akfamily.xyz/data/stock/stock.html)和本地锁定 SDK | stock_us_hist 文档要求从 stock_us_spot_em 的代码字段取得 provider_symbol。单个 MSFT 样例不足以证明其他前缀、股类、标点及币种。本轮未下载全市场表 | SDK 1.18.94，网页生效日期未知 / 2026-09-10，日期精度 |

未保存网页完整原文字节，不编造网页 hash。开源库不是上游授权主体。没有购买订阅、创建账户或修改代理。已核对日线主机仅为 `63.push2his.eastmoney.com`；其他身份端点未经核对不得加入。SEC 保留 `data.sec.gov`、`www.sec.gov` 及本地联系身份要求。

免费范围目前只能确认已获批试拉未使用付费账户/key/订阅；不能据此确认正式免费额度或自动化使用权。日线非实时，具体发布延迟未验证。正式访问仍按每秒至多 1 请求、暂时故障最多 2 次重试、401/403/429 停止、单请求 20 秒/2 MiB 和外置总预算。

尚缺具体使用条件及小范围身份材料，不是代理端口或模型配置。追加身份技术验证需要限定范围批准；原 Task 1.4 额度不自动重复。

## 2026-09-10 历史：Task 1.4 实际技术试拉

以下更新优先于后面的历史核对记录。用户批准的有限技术试拉已实际执行；不再是仅看文档。正式来源准入仍为 `UNRESOLVED` / `BLOCKED_PENDING_AUTHORIZATION`，不据此完成 Task 1.1 或启动 Council。

| 路线 | 真实结果 | 不能据此推导 |
| --- | --- | --- |
| Yahoo，yfinance 1.7.0 | 1 次 GET，匿名初始化 `https://fc.yahoo.com` 返回 404，试验立即终止，退出码 1；未发出 chart 行情请求 | 不是 Yahoo 行情端点已被证明不可用，也不是沙箱/代理失败证明 |
| AKShare 1.18.94 / 东方财富 | 1 次 GET，HTTP 200，827 字节；返回 MSFT 7 条日线，日期 2026-08-31 至 2026-09-09，退出码 0；响应代码、日期范围、正且有限 close 另经只读核验 | 不代表正式授权、实时性/复权/身份全部通过或产品已集成 AKShare |

两次执行各自获得宿主命令权限，未修改权限配置或代理。均只使用公开测试 ticker，没有持仓、邮箱、登录凭证或模型调用。Yahoo 使用 SDK 支持的 requests Session（没有 TLS 浏览器模拟），并在试验进程内禁用持久 cookie 缓存；因此也不能把其结果包装成产品 curl_cffi 路径的真实验收。现有产品边界允许匿名初始化的特定 404，而本轮获批试验规则是任何 HTTP 错误即停；本轮没有改规则后重跑，也没有放宽产品 Validator。

AKShare 调用了实际安装的 `stock_us_hist`，在外置试验的请求边界将服务器端参数收窄为 `beg=20260831, end=20260910, lmt=10`，保留 `secid=105.MSFT, klt=101, fqt=0`。原 SDK 参数 `end=20500000, lmt=1000000` 未原样发送。仅修改本次请求，不修改安装库文件；应称为“带有界请求适配的 SDK 试拉成功”，不称原版无约束调用成功。原始响应由现有库解析，没有手工拼造行情。

### 可审计标识与实际命令

外置目录：`/private/tmp/stock-agent-source-trial.JhvGbZ`。每条路线保存 `manifest.json`、`result.json`；AKShare 原始响应另存 `akshare/response-1.bin`。所有产物均为 `purpose=TECHNICAL_TRIAL`、`eligible_for_council=false`、`source_access_status=UNRESOLVED`。公开仓库仅保存本摘要，不提交外置依赖、原始行情或 SDK 状态。

```sh
/private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B /private/tmp/stock-agent-source-trial.JhvGbZ/trial.py yahoo
/private/tmp/stock-agent-source-trial.JhvGbZ/ak-env/bin/python -B /private/tmp/stock-agent-source-trial.JhvGbZ/trial.py akshare
```

| 文件 / 标识 | SHA-256 |
| --- | --- |
| 外置 `trial.py` | `82e8b8c1071a345dd70da4fbf78a6acd2a7e0a3a4f57a8986060c00287a553db` |
| `yahoo/result.json`；trial_id=`yahoo-stock-agent-source-trial.JhvGbZ` | `09a5a5f016cd2ebec22e8a16c0653a4863483acf084a4bc0e65eb39b3e4f90dd` |
| `akshare/result.json`；trial_id=`akshare-stock-agent-source-trial.JhvGbZ` | `75110a1e71539dc2dcb62784a08718b116ec02ee5b6e577037d42b9259fae04c` |
| AKShare 原始响应 | `a51aca8f4df9f09240f1ae7455cc127c9b05b76a09e26ad64add92b87f0f2d8a` |
| 实际 yfinance data.py | `5f41a4cec99d50be3a13c8ae5f2674e1b5e1582be1a861fcdbb57bba783629da` |
| 实际 AKShare stock_hist_em.py | `d2a4c09d55d9362c8c7e58ec82f78d198cf6d2c2daf004033eef42ded915050d` |

Yahoo 执行时间为 `2026-09-10T03:23:28.126861+00:00` 至 `2026-09-10T03:23:30.545362+00:00`；AKShare 为 `2026-09-10T03:23:58.245249+00:00` 至 `2026-09-10T03:24:00.929140+00:00`，行情 `retrieved_at=2026-09-10T03:24:00.918675+00:00`。数据日期仅为供应方日线日期，未冒充完整 LiveFact 的公开时点或交易日历验证。

请求预算、每次实际参数、HTTP 状态、依赖版本清单和失败码均在原始 result 中；每路线零重试、单响应 2 MiB、20 秒请求超时及 90 秒墙钟限制实际由外置脚本执行。AKShare 使用新建外置 venv 安装，产品依赖锁未改。`live-offline-phase-3.sha256` 的 73 个文件逐项重验全部一致，旧离线证据范围不变；未重跑全量测试/Regression/Gate。试拉数据没有进入产品缓存、Evidence 或报告。

Task 1.4 的“有界尝试及真实结果记录”完成。下一步仍需正式单行情源选型和来源准入；如选用 AKShare，必须先更新当前 Change 的产品来源设计，不自动启用双源或将本次外置数据导入产品。

## 2026-09-10 恢复核对：Yahoo 与 AKShare

用户已明确允许恢复尝试 Yahoo，并评估 AKShare。此前“用户暂停 Yahoo”的状态已解除；但来源许可未确认的工程门禁仍未解除。下文 2026-09-09 的未安装依赖、0/21 等陈述仅代表当时状态；当前实现进度为 16/21，SDK 安装和版本见 `live-sdk-contract.md`，离线验收见 `../../reviews/development/us-equity-live-advisory-slice-offline-verification.md`。

本轮实际执行公开文档和开源代码读取，没有调用行情 API、安装 AKShare、发送邮箱、修改来源授权状态、运行 Council 或变更代理。不能称为下载失败或 SDK 接入成功。

| 项目 | 核对结果 | 当前判定 |
| --- | --- | --- |
| Yahoo/yfinance | 官方 US/通用地区条款直接读取均返回浏览工具 999；官方通用地区搜索索引仍有自动化访问需事先明确许可的条款。直接读取失败不能推导行情网络故障，也不能据索引声称完整法律审查 | `ACCESS_REVIEW_UNRESOLVED`；行情请求 `NOT_RUN` |
| AKShare 东方财富路线 | `stock_us_hist` 读取东方财富，不是 AKShare 自有行情；有 daily 与复权选项。实际读取 main 源码发现发送 `end=20500000`、`lmt=1000000`，再在本地按 start/end 切片，不能把调用的短日期范围当成小响应预算 | `CANDIDATE_ONLY`；行情请求 `NOT_RUN`；不直接接进现有采集器 |
| AKShare 新浪路线 | 官方文档提供 `stock_us_daily` 美股日线；是另一上游来源，不能和东方财富共享授权结论 | 仅候选记录，未验证访问条件或数据 |
| 数据用途 | AKShare 项目概览说明学术研究用途；东方财富法律声明含复制/传播与运行负载限制。未取得本项目个人持仓自动采集、缓存用途的明确准入依据，不能用库可开源下载替代数据使用权 | 不作“违法”法律结论，也不标为 `AUTHORIZED` |

### 本轮来源定位

以下 `retrieved_at=2026-09-10` 为工具核对日期精度；页面未给出明确生效日期时 `as_of=未核实`。未保存网页原始字节，未编造原文 hash。GitHub main 是当次查看的可变源码，不作为已安装版本锁。

- `yahoo-terms-recheck`：[Yahoo 通用地区条款](https://legal.yahoo.com/xw/en/yahoo/terms/otos/index.html)；仅搜索索引支持条款观察，全文读取失败。
- `akshare-us-documentation`：[AKShare 股票接口文档](https://akshare.akfamily.xyz/data/stock/stock.html)；接口说明及复权注意事项。
- `akshare-em-source-review`：[stock_hist_em.py](https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_hist_em.py) 中 `stock_us_hist`；当次源码使用 `63.push2his.eastmoney.com`，请求 timeout=15，日期范围在响应解析后切片。未据此开放域名或复制实现。
- `akshare-purpose-review`：[项目概览](https://akshare.akfamily.xyz/introduction.html)；页面标注文档更新时间 2026-08-21，非上游授权日期。
- `eastmoney-terms-review`：[东方财富法律声明](https://about.eastmoney.com/home/disclaimer) 第四、八、十部分；未确认对本次美股端点、缓存和用途的完整适用范围。

### 尚需决策

现有 Spec 要求来源权限不能确认时不采集，覆盖首次尝试。若要将“少量个人技术试拉”和“正式产品来源准入”分开，必须先透明调整当前 Change 的契约并明确试验预算、数据用途和停止条件；不能只在代码中绕过 `SOURCE_NOT_AUTHORIZED`。该流程调整本身不构成任何上游授权。本轮未擅自修改此门禁、启用第二数据源或增加任务。

## 当前结论

`SOURCE_ACCESS_STATUS: BLOCKED_PENDING_AUTHORIZATION`

规划的来源仍为 Yahoo/yfinance 行情＋SEC 披露，尚未启用或更换。Task 1.1 未完成，不能以本文存在作为通过证据。

Yahoo 官方条款的 Acceptable Use 自动访问条款要求事先明确许可；本次没有取得适用于 yfinance 所用行情端点和本项目用途的许可依据。yfinance 的个人用途提示不等同于 Yahoo 授予自动化取数许可。因此按本 Change 的准入要求停止，不以低频、免费、无需 key 或接口可访问替代授权核实。[Yahoo 官方条款](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?bt_ts=1741912561771)

## 核对依据

以下来源于公开文档查询，而非实际数据 API 调用。`retrieved_at` 仅记录本次核对日期，未保存网页完整原始字节，不提供虚构的秒级时间或原文 hash；网页生效日期未完整核实时标为未知。

| source_id | 来源定位 | 本次观察 | 时间说明 |
| --- | --- | --- | --- |
| yahoo-terms-us | [Yahoo US Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html?bt_ts=1741912561771) 的 Acceptable Use 第 9 项 | 官方页面搜索索引返回自动化访问事先许可条款；直接网页读取失败，不能声称阅读全文或完成所有地区适用性核对 | retrieved_at=2026-09-09（日期精度）；as_of=未核实 |
| yahoo-terms-xw | [Yahoo 通用地区 Terms](https://legal.yahoo.com/xw/en/yahoo/terms/otos/index.html) 的 Acceptable Use 第 9 项 | 官方索引也返回同类限制；不据此猜测用户所在地或合同主体 | retrieved_at=2026-09-09（日期精度）；as_of=未核实 |
| yfinance-project-docs | [yfinance 项目文档](https://ranaroussi.github.io/yfinance/) 的免责声明 | 项目自述非 Yahoo 官方背书，提示研究/教育和个人用途，并要求用户核对 Yahoo 条款 | retrieved_at=2026-09-09（日期精度）；as_of=文档未给出条款生效日期 |
| sec-api-docs | [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | submissions/companyfacts 公共读取无需 API key，可取得披露元数据和 XBRL；存在 bulk 路径 | retrieved_at=2026-09-09（日期精度）；as_of=页面标注更新 2025-04-08 |
| sec-fair-access | [SEC Developer Resources](https://www.sec.gov/about/developer-resources) 的 Fair Access | 每用户合计不得超过 10 请求/秒，要求有身份的自动化访问并可封禁过量请求 | retrieved_at=2026-09-09（日期精度）；as_of=页面标注更新 2025-03-10 |

这些文档核对记录不是产品 LiveFact，不会进入投资研究 Evidence。搜索索引条款足以提示未解决的准入风险，但不构成对某一具体用途是否合法的最终判断。

## 费用、时效和请求边界

- 目标为不购买行情订阅的个人非实时研究；当前未安装 live 依赖、未创建账户、未付费。Yahoo 免费客户端不等于数据访问获批，不承诺无限请求、全市场吞吐或服务可用性。
- 行情按已完成常规交易日取日线，不能宣称实时；具体发布延迟和最新交易日完整性需后续用获准来源验证。
- SEC 公共 API 不要求付费 key；本项目拟采用串行、最多 2 请求/秒的保守预算。该数值是项目政策，不是 SEC 额度。遵守同一用户全部客户端的合计限制。
- 真实模型运行有独立 Codex 消耗，免费数据不代表 LLM 运行免费。
- Yahoo 拟用客户端版本、确切端点、域名、SDK 内部请求次数尚未核实/锁定，属于 Task 1.2，不填占位版本作为已完成结果。
- SEC 已确认的拟用主机为 `data.sec.gov`（JSON）和 `www.sec.gov`（披露原文）。本次不修改任何域名 allowlist、用户代理或权限配置，不以域名存在声称网络可用。

## 本地身份与隐私

SEC 访问应配置标识应用及真实联系渠道的 User-Agent。具体本地设置方式将在适配实现后给出；当前没有可执行设置命令，不请求用户把联系信息或凭证贴进聊天。Yahoo cookies、认证状态、完整环境、真实持仓和原始采集/运行包均不得提交 Git。

后续数据请求仅带 ticker/CIK/日期等必要查询字段，不向来源服务发送持仓数量、成本、现金或研究问题。Council 模型会接收研究所需组合上下文，不能将此产品描述为全部数据留在本机。

## 解阻条件与停止范围

以下任一方向需要明确处理后再继续，不自动执行：

1. 获得并核实适用于所选 Yahoo 数据端点及用途的许可依据；用户批准开发或接受风险本身不能代替上游许可。
2. 用户授权在当前 Change 内重新核对并选择访问条件明确、免费优先的单一行情源，再用 OpenSpec update 同步对应选型，不新增 Change 或暗中双源兜底。
3. 用户批准先继续与行情授权无关的离线契约/合成测试工作，同时保持 Yahoo 真实采集和 live 验收阻断。这不代表来源准入通过。

本次只保存 Task 1.1 核对与阻断记录；未修改产品实现、依赖、代理、沙箱或生产版本指针，未运行测试、行情采集或 Council。任务仍为 0/21 完成。
