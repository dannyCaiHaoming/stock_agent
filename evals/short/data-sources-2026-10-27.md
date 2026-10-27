# Short interest 数据源探查（2026-10-27）

范围：仅数据可得性与点时表，不含任何收益统计。脚本 `scripts/build-short-interest.py`，产物 `.local/cache/derived/short/si.jsonl`（21,210 行，106 只，2017-12-29 ~ 2026-10-15），FINRA 原始响应 `.local/runs/short-probe/finra-raw.json`。

## 1. FINRA Short Interest（持仓口径）

- 来源：FINRA Query API，`POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest`（数据集名带 otcMarket，但实测包含 NNM/NYSE 等交易所上市股票，AAPL 等均有）。
- 鉴权：官方文档称需免费 Public credential（OAuth2）；**实测 2026-10-27 无凭据匿名 POST 可用**。这点不应依赖，未来可能被收紧；届时申请免费 Public credential 即可。
- 限额：同步请求 1,200 次/分钟/IP；单次最多 5,000 条（`limit`，`offset` 上限 500,000）；Public credential 每月 10 GB 下载。全宇宙一次拉取约 5 页，远低于上限。`domainFilters` 可一次传多只 symbol；排序要求 settlementDate 为 EQUAL 过滤，故脚本不排序、本地排序。
- 许可：Specific Terms for Equity Data，仅限非商业个人/职业用途，再分发受限。本项目为研究用途，派生表留在 `.local/`（已 gitignore），不要提交或再分发原始数据。
- 字段：settlementDate、symbolCode、issueName、marketClassCode、currentShortPositionQuantity、previousShortPositionQuantity、changePreviousNumber、changePercent、averageDailyVolumeQuantity、daysToCoverQuantity、revisionFlag（R=上一期被修订）、stockSplitFlag（S=当期有拆股）。无 float、无公布日期字段。
- 历史深度：元数据称“滚动一年”，**实测已过时**：可取到 2017-12-29 起共 212 个结算日（AAPL/MSFT 各 212 条），约 8.8 年，无需自行积累。
- 与 daily short sale volume 的区别：本表是半月度**持仓存量**（结算日未平仓空头数量）；FINRA 另有日度 short sale volume（RegSHO 日文件）只是当日**成交活动**中标记为卖空的量，不是持仓，不能互换，本探查不使用。

## 2. 时点规则

- 结算日：每月 15 日与月末（遇非交易日顺延/提前）。
- 公布日 = 结算日之后第 **7 个交易日**（报告截止为结算后第 2 个交易日 18:00 ET，公布再 5 个交易日）。官方 2025-11 ~ 2026-10 共 23 个结算日的公布日历逐一核对，脚本内 NYSE 交易日历推算 23/23 一致（脚本启动自检，不一致即中止）。2018-2025 的公布日用同一规则推算，未逐期对照官方历史表。
- FINRA 页面未给出公布的钟点。建议“已知时点” = publication_date 当日收盘后，即最早在 publication_date 的**下一个交易日**才可用于信号（保守）。
- 结算日到公布日之间约 10 个日历日，信号窗口必须从公布日起算，不得从结算日起算。

## 3. 修订（重要局限）

- API 只返回当前版本，不保留首次发布值，**无法还原当时看到的数据**。可见痕迹：725 行 `revision_flag=R`；724 行“前一行 current ≠ 本行 previous”（`chain_mismatch`，与 R 基本对应，说明上一期曾被修订）。
- 影响：历史 SI 水平多为修订后终值，与当时公布值可能小幅不同；`change`/`prior` 来自本行当期记录。修订占比约 3.4%，幅度未量化。若要真正点时，只能从现在起每期归档快照（forward collection，建议加到 `snapshot-daily` 同类流程：每个公布日抓一次并存只追加文件）。
- 拆股：FINRA 数值不做拆股调整（17 行 `split_flag=S`）。SI 与当期已知 shares_outstanding 均为拆股前口径，比例本身一致；但跨拆股比较绝对 SI 水平（如 NVDA 2021-07、2024-06，TSLA 2020-08/2022-08）需谨慎，变动量字段在拆股期不可信。

## 4. 分母：shares outstanding

- 来源：SEC companyfacts `dei:EntityCommonStockSharesOutstanding`，取 `filed <= publication_date` 的最新一条（按 filed 点时）；记录 end（封面日期）、filed、accession。封面日期早于 filed，通常滞后结算日 1-3 个月。
- 局限：
  - 双/多类股公司 companyfacts 往往只保留单一类别或缺失。完全无该 tag：GOOGL、META、PL（KeyError）。另有 ALAB、AVGO、BLK、CRDO、DIS、GEV、MRVL、RDW、RKLB、XOM 在早期无数据（BLK 到 2024-10、XOM 到 2026-07 才有）。共 966 行无分母（4.6%）。
  - 数值陈旧：CMCSA、V、MA、UPS、NKE 等多类股公司，companyfacts 的 dei 序列停在多年前（如 V、CMCSA 距今约 16 年；CMCSA/V/MA/UPS/NKE 几乎全期陈旧），分母不可用。`shares_stale`（公布日距 filed >150 天）共 1,209 行已标记；另有 KO、ABT、C、DUK、NEE、PLD、PYPL、SO 等近期偶发超 150 天，多数是缓存的 companyfacts 未含最新 10-Q，重跑可缓解。
  - 可用分母行（有值且不陈旧）：19,035 / 21,210（89.7%）。si_pct_shares_out 中位约 1.4%（有值且非陈旧行）；极端值如 AAOI 2018 年 56-80%，与其实际高空头比例一致，但需留意流通股 float 远小于总股本的公司，分母口径是总股本不是 float（无免费点时 float 源，已放弃 float）。
- 备选：us-gaap `CommonStockSharesOutstanding`（资产负债表日，滞后更大）、或用 Yahoo 价格缓存的成交量与 FINRA 的 ADV 对照（见下）；本次未实现。

## 5. 成交量与 days-to-cover

- 直接使用 FINRA 的 `averageDailyVolumeQuantity`（FINRA 说明“不含非媒体成交”，周期口径未披露；观察到同一股票相邻期 ADV 波动较大，例如 AAPL 2018-02 为 5830 万、2018-07 为 1673 万，可能与取样窗口有关）。
- days_to_cover = SI / ADV 本地重算；FINRA 自带值有时为整数舍入、有时两位小数。两者差 >0.05 的有 821 行（3.9%），这 821 行 FINRA 值全为整数（舍入），分布在各年而非仅早期。分析用重算值，原值保留在 `days_to_cover_finra`。
- 未用价格缓存重算 ADV：Yahoo 成交量窗口与 FINRA 不一致，且 FINRA 窗口未披露，引入会增加口径歧义。

## 6. 覆盖与数据问题汇总

- 106 只全部有 FINRA 记录。上市较短的：SNDK 40 期、TLN 55、GEV 61、ALAB 62、META 118（FINRA 侧仅 118 期，代码变更前的历史可能挂在旧代码 FB 下，未补）、PL 117、RDW 123、BKSY 123、RKLB 124、CRDO 114；RTX 157（UTX 合并前代码不同）、LIN 192。
- 更名/代码变更会造成历史缺口（META、RTX、可能还有 SNDK/GEV 等分拆新股，不存在历史属正常）。
- 幸存者偏差沿用 universe 的既有说明；热门板块组含“挑赢家”偏差。
- 修订不可还原（见 §3）；float 不可得；多类股分母缺失/陈旧（见 §4）。

## 7. 下一步建议（待预注册）

1. 使用本表时：信号日 t 只能使用 publication_date < t 的最新一期；分母需 `shares_stale=false` 且非空，否则该行只用 days_to_cover / change_pct（不依赖分母）。
2. 对 CMCSA/V/MA/UPS/NKE/GOOGL/META 等多类股另寻分母（10-K/10-Q 封面解析）或剔除，并在预注册中声明。
3. 从现在起每个公布日归档一份 FINRA 快照（只追加），为日后真正的点时验证积累未经修订的首发值。
