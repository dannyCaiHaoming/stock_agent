---
name: stock-research
description: 单只美股或 ETF 的端到端研究入口：用户说“研究/分析 TICKER”“该不该买/卖 TICKER”时使用。并行启动独立的正向（advocate）与反向（skeptic）子 Agent，按共享方法卡分析，反向读正向论点后补充一轮核验，由 CIO 权衡证据、结合行情与持仓后给出 BUY/ADD/HOLD/REDUCE/EXIT/NO_TRADE 建议并保存决策记录。
---

# 个股研究流程

依赖 stock-data MCP 工具、`advocate` 与 `skeptic` 子 Agent，以及以下 Skills：`research-standards`、`company-fundamentals`、`valuation`、`peer-comparison`、`macro-market-context`、`technical-structure`、`investment-decision`。

## 0. 确认输入（不要过度提问）

- 代码；用户是否持有、成本、关注的问题（有就用，没有就按“未持有”处理，不必追问）。
- `as_of`：默认现在。用户要求“以某日为准”时，对所有支持 `as_of` 的工具都传入同一个日期。`get_analyst_snapshot` 只有当前快照，不能用于过去的日期。
- **历史回放模式**（任务写明“历史回放模式：数据截至 {日期}”时）：
  - 把该日期当作今天。所有工具都在这个日期截止（服务端已强制），子 Agent 的任务里写“数据截至：{日期}（历史回放，把它当作今天）”。
  - 不调用 moomoo Skills 与 Bash；`get_analyst_snapshot`、`get_peer_candidates`、`get_peer_snapshot` 会返回 `NOT_POINT_IN_TIME`，不要调用。这些都记为数据缺口（`SOURCE_UNSUPPORTED`：回放无当时数据），不算流程失败。
  - 决策价格用 `get_price_history` 在该日期或之前最后一个收盘价；股数用财报。没有分析师共识时，情景收入用公司历史增速与最近指引（8-K EX-99.1）推算，并写明。同业用你确知的代码，以 `get_financial_statements` 和 `technical_stats` 比较。
  - **不得使用你对该日期之后事件的记忆**（股价走势、财报、并购、管理层变动等）。所有事实必须来自本次工具结果；报告与审查里都不能提到该日期之后的事。
  - `save_decision` 的 `price` 用上面的收盘价，`data_as_of` 用回放日期。
  - 不要读取仓库的 `evals/`、`.local/` 目录（其中有回放样本的分组与事后结果）。
- ETF 没有 SEC 财报：跳过基本面那一步，改为说明 ETF 的跟踪对象、费率和持仓特征（资料不足时如实说明），然后做技术面与估值背景。

## 1. 启动独立的正向与反向研究（第一步就做，两个并行）

同时调用两个子 Agent（Claude Code：Agent/Task 工具，`subagent_type` 分别为 `advocate` 和 `skeptic`，在后台运行；Codex：用 `spawn_agent` 分别派生 `advocate` 与 `skeptic`，**`fork_turns` 必须设为 `"none"`**，否则子 Agent 会继承本对话，破坏独立性）。**只能**传入下面的话，不要附带你的任何发现或结论：

> advocate：正向评估投资 {TICKER}。数据截至：{as_of 或“当前”}。按 bull-case Skill 与共享 references 输出正向初稿。
> skeptic：独立评估投资 {TICKER}。数据截至：{as_of 或“当前”}。按 skeptic-review Skill 第一步与共享 references 输出反向初稿。

两个子 Agent 自行取数，与主研究互不可见。**在第 4 步写下初步判断之前，不要读取它们的结果**（Codex 不要提前 wait）。任何一个失败或超时，都要在“数据缺口”写明，并由你自己补做该方向的分析（标注“非独立”）。

## 2. 资料收集（建议顺序，可以并行调用）

1. `get_analyst_snapshot`：公司概况、价格、市值、共识、预估、下次财报日。
2. `get_financial_statements`：年度 5 期，再取季度 6 期（看 `ttm`、推导出的 Q4、重述）。
3. `technical_stats`：相对 SPY。
4. `pe_history`：只适用于盈利公司。
5. `list_filings`：近期 10-K、10-Q、8-K。最近一次财报的 8-K 要读新闻稿：先 `list_filing_documents(accession)` 找到 `EX-99.1`，再用 `get_filing_text(accession=..., document=<文件名>, query="Outlook")` 直接定位业绩指引段（找不到再试 `guidance`、`expects`）；需要正文时不带 `query` 读第一页即可，后面多是财务表格。读到的指引数字要写进报告并标注来源为该 8-K，不要再写成“未取得”。
6. `get_filing_text`：最新 10-Q 的 `management_discussion`；不熟悉的公司加读 10-K 的 `business`；与核心问题相关时读 `risk_factors`。只读需要的部分，用 `next_offset` 分页。若某章节只返回目录或交叉引用（银行等发行人常见），改用 `section="full_text"` 并传 `query`（例如“net interest income”“Results of Operations”）直接定位内容；不要把“这次没读到正文”写成资料不存在。
   查条款类内容（可转换证券、优先股、债务契约、租赁承诺、诉讼）一律在 10-K/10-Q 的 `section="full_text"` 用 `query` 搜索；`query` 先精确匹配短语，找不到会按“所有关键词同段出现”再找，结果带 `total_matches`，用 `match_offset` 翻页。0 命中时换同义词再试一次，仍无结果才记为缺口，并写明搜过的词和文件。

7. **消息面与持仓变动**（都支持历史时点）：
   - `get_news_history`（默认 30 天财经相关标题；必要时用 `query` 查诉讼、调查、监管等专题）。标题只是线索：同名地点、人物和机构增减持的自动稿很多，先判断相关性；涉及公司事实的，回到 8-K 等原始披露核实后再引用。
   - `get_insider_transactions`（默认 180 天）：看公开市场买入（尤其多位高管同时买入）和卖出；10b5-1 计划内的卖出、授予、行权、代扣税信息量低。
   - `get_fund_holdings`：约 18 家知名基金最近两期 13F 的持仓与变化（季度末之后最多 45 天才公布，只有多头）。
   - `get_congress_trades`（默认 365 天）：众议院议员的交易申报（金额为区间，最多延迟 45 天，不含参议院）。
   这些写进报告“消息面与持仓变动”一节，并在论点表中说明是否使用、如何使用；单笔小额交易、计划内卖出不应当作论点。

8. **moomoo 第三方 Skills（必做，不可跳过）**（按 `research-standards` 的“第三方软件内容”规则处理）。下面四项每次研究都要执行；某项失败或 OpenD 未运行时，在“数据缺口”写明原因，不能不调用就略过：
   - `moomoo-news-search`：近期新闻（news_type=1）与公告（news_type=2），必要时研报（news_type=3）。用于事件地图与催化剂线索。
   - `moomoo-comment-sentiment`：社区情绪快照，**必须**按该 Skill 说明调用 `https://ai-news-search.moomoo.com/stock_feed` 接口（不能用新闻搜索结果代替），只放入“第三方观点”。
   - 异动类（需本机 OpenD，三个都要跑）：`moomoo-capital-anomaly`、`moomoo-derivatives-anomaly`、`moomoo-technical-anomaly`。代码用 `US.<TICKER>` 形式。**在仓库根目录逐个运行**（不要用系统 `python3`，依赖装在 `.venv`）：
     - `.venv/bin/python -I product/skills/moomoo-capital-anomaly/scripts/handle_capital_anomaly.py US.<TICKER> --time-range 7 --json`
     - `.venv/bin/python -I product/skills/moomoo-derivatives-anomaly/scripts/handle_derivatives_anomaly.py US.<TICKER> --time-range 7 --json`
     - `.venv/bin/python -I product/skills/moomoo-technical-anomaly/scripts/handle_technical_anomaly.py US.<TICKER> --time-range 7 --json`OpenD 未连接时记为数据缺口（`SOURCE_UNSUPPORTED`：OpenD 未运行），不重试。
   - moomoo 接口按 Skill 原样的 `curl -sG 'https://ai-news-search.moomoo.com/...'` 形式调用，结果直接输出，不加 `-o` 或重定向，不写任何临时文件。
   - Bash 只用于上面两类命令，每次一条，不用 `for`、`ls`、`grep`、`cat` 等浏览文件（查看 Skill 说明用 Read 或 Skill 工具）。某条命令被权限拒绝时，只说明那条命令的格式不符合要求：按上面的格式改正后重试一次，其余 moomoo 步骤照常执行。
   - 不使用 `moomoo-stock-digest` 替代自己的事件分析；如调用，其结论同样只作参考展示。

9. `get_macro_snapshot` 与 `get_market_context`（各一次）；`get_peer_candidates` 与 `get_peer_snapshot`。

工具报错时，看错误代码后用正确参数重试一次；仍失败就记为数据缺口，不要反复重试。

## 3. 分析

按 `product/references/methods/` 的方法卡分析（适用才用），并参考 `company-fundamentals`、`valuation`、`peer-comparison`、`macro-market-context`、`technical-structure` 的取数细节。三方（你、advocate、skeptic）用同样的工具与 `as_of`，读到的是同一份数据（工具结果有缓存）。需要的数字计算全部调用计算工具完成。

## 4. 初步判断

按 `investment-decision` 第 2 步，写下初步动作和 3 条核心理由。完成后才读取两个子 Agent 的初稿。

## 5. 反向核验（只补一轮）

收到 advocate 的正向初稿后，把它发给第 1 步的 `skeptic`（Codex 用 `followup_task`；Claude Code 新开一次 `skeptic` 调用；任何新派生同样用 `fork_turns="none"`），任务以“核验”开头，只附正向初稿，不附你的判断：

> 核验：{TICKER}，数据截至 {as_of}。以下是正向论点。按 skeptic-review 第二步检验其关键前提、补充遗漏风险，结论可以是“未发现足以改变结论的反证”。
> {正向初稿全文}

核验失败或超时，就在“数据缺口”写明，并自己按第二步的问题清单检查。

## 6. CIO 判断

应用 `investment-decision`：对齐时间尺度、判断方法适用性、权衡正向初稿、反向初稿与核验的证据，结合统计、案例、行情与持仓，得出动作、仓位、方向预测与改判条件，按模板写出完整报告。不再做事后论证审查。

## 7. 交付

1. 在对话中给出完整报告。
2. 报告定稿后只调用一次 `save_decision` 保存（不要先存草稿再存终稿），并告诉用户保存位置。

## 预算

目标在 25 分钟内完成（含 advocate 初稿、skeptic 初稿与核验三次子 Agent 调用），主研究工具调用大约 25–40 次。资料够用就停止，不为求全而无限追加调用。时间或预算不够时，优先保证核心问题、估值和多空权衡，其余写入“数据缺口与限制”。
