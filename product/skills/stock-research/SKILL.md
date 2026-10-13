---
name: stock-research
description: 单只美股或 ETF 的端到端研究入口：用户说“研究/分析 TICKER”“该不该买/卖 TICKER”时使用。依次完成资料收集、基本面、估值、技术面、反方自检，最后给出 BUY/ADD/HOLD/REDUCE/EXIT/NO_TRADE 建议并保存决策记录。
---

# 个股研究流程

依赖 stock-data MCP 工具，以及以下 Skills：`research-standards`、`company-fundamentals`、`valuation`、`technical-structure`、`investment-decision`。

## 0. 确认输入（不要过度提问）

- 代码；用户是否持有、成本、关注的问题（有就用，没有就按“未持有”处理，不必追问）。
- `as_of`：默认现在。用户要求“以某日为准”时，对所有支持 `as_of` 的工具都传入同一个日期。`get_analyst_snapshot` 只有当前快照，不能用于过去的日期。
- ETF 没有 SEC 财报：跳过基本面那一步，改为说明 ETF 的跟踪对象、费率和持仓特征（资料不足时如实说明），然后做技术面与估值背景。

## 1. 资料收集（建议顺序，可以并行调用）

1. `get_analyst_snapshot`：公司概况、价格、市值、共识、预估、下次财报日。
2. `get_financial_statements`：年度 5 期，再取季度 6 期（看 `ttm`、推导出的 Q4、重述）。
3. `technical_stats`：相对 SPY。
4. `pe_history`：只适用于盈利公司。
5. `list_filings`：近期 10-K、10-Q、8-K。
6. `get_filing_text`：最新 10-Q 的 `management_discussion`；不熟悉的公司加读 10-K 的 `business`；与核心问题相关时读 `risk_factors`。只读需要的部分，用 `next_offset` 分页。若某章节只返回目录或交叉引用（银行等发行人常见），改用 `section="full_text"` 并传 `query`（例如“net interest income”“Results of Operations”）直接定位内容；不要把“这次没读到正文”写成资料不存在。

7. **moomoo 第三方 Skills（必做，不可跳过）**（按 `research-standards` 的“第三方软件内容”规则处理）。下面四项每次研究都要执行；某项失败或 OpenD 未运行时，在“数据缺口”写明原因，不能不调用就略过：
   - `moomoo-news-search`：近期新闻（news_type=1）与公告（news_type=2），必要时研报（news_type=3）。用于事件地图与催化剂线索。
   - `moomoo-comment-sentiment`：社区情绪快照（按该 Skill 说明调用 `stock_feed` 接口），只放入“第三方观点”。
   - 异动类（需本机 OpenD，三个都要跑）：`moomoo-capital-anomaly`、`moomoo-derivatives-anomaly`、`moomoo-technical-anomaly`。代码用 `US.<TICKER>` 形式。**在仓库根目录用 `.venv/bin/python -I product/skills/<skill>/scripts/<script>.py US.<TICKER> --time-range 7 --json` 运行**（不要用系统 `python3`，依赖装在 `.venv`）。OpenD 未连接时记为数据缺口（`SOURCE_UNSUPPORTED`：OpenD 未运行），不重试。
   - 不使用 `moomoo-stock-digest` 替代自己的事件分析；如调用，其结论同样只作参考展示。

工具报错时，看错误代码后用正确参数重试一次；仍失败就记为数据缺口，不要反复重试。

## 2. 分析

依次应用 `company-fundamentals`（先选 2–3 个核心问题）→ `valuation` → `technical-structure`。需要的数字计算全部调用计算工具完成。

## 3. 决策与报告

应用 `investment-decision`：完成反方自检，选定动作和信心，按模板写出完整报告。

## 4. 交付

1. 在对话中给出完整报告。
2. 调用 `save_decision` 保存，并告诉用户保存位置。

## 预算

目标在 15 分钟内完成，工具调用大约 15–30 次。资料够用就停止，不为求全而无限追加调用。时间或预算不够时，优先保证核心问题、估值和反方自检，其余写入“数据缺口与限制”。
