# 心法自检小对照（事先登记，2026-11-16）

## 问题
`investment-decision` 第 9 步“心法自检”（读 `trader-playbooks-synthesis` 卡“针对四个毛病的对治”一节逐组自问）加上之后，CIO 的**行为**有没有变化：动作、仓位、置信度、方向预测、改判条件的具体程度。

只衡量行为是否改变，不衡量对错。n=6，只做描述，不做显著性结论。

## 样本

### 选择规则（跑之前固定）
- 方向取交易者卡里 2026 年 6–8 月实际讨论的六个方向，每个方向一只；必须在 `evals/replay/universe.txt` 里。
- 日期取自关键时刻事件表 `.local/cache/derived/signals/key-moments.jsonl`（2026-11-11 建，覆盖股票池全部股票；时刻定义见 `product/deterministic/key_moments.py`），窗口 2026-06-01 至 2026-08-31。
- 下跌类：`platform_breakdown`、`platform_breakdown_new_low`、`uptrend_break`、`sharp_reversal_down`、`failed_breakout`（突破失败，收回平台中点之下）。
- 反弹类：`sharp_reversal_up`、`failed_breakdown`、`downtrend_break`。
- 第 1、3、5 只：窗口内第一个下跌类时刻。第 2、4、6 只：窗口内第一个反弹类时刻，且同一股票在窗口内、该时刻之前出现过下跌类时刻。
- 没有符合的时刻就取另一类（按“窗口内第一个”），仍没有就按股票池同组顺序换同方向的股票。
- 只用事件的日期和类型，选择时不看 `outcome` 字段。

### 结果

| # | 方向 | 原定 | 实际 | 日期 | 时刻 | 说明 |
|---|---|---|---|---|---|---|
| 1 | CPU／晶圆代工 | INTC | INTC | 2026-07-16 | uptrend_break | 窗口内第一个下跌类 |
| 2 | 功率半导体 | WOLF | TXN | 2026-06-26 | failed_breakout | WOLF 不在股票池；池内无功率半导体专营股，取模拟／电源管理占比高的 TXN。TXN 窗口内没有反弹类时刻，改取下跌类 |
| 3 | 存储 | MU | MU | 2026-07-28 | platform_breakdown（同日 uptrend_break） | 窗口内第一个下跌类 |
| 4 | AI 芯片龙头 | NVDA | NVDA | 2026-08-04 | failed_breakdown | 之前 2026-07-29 platform_breakdown |
| 5 | 算力租赁 | CRWV | ORCL | 2026-06-11 | sharp_reversal_down | CRWV 不在股票池；池内无纯算力租赁股，取以 AI 算力出租和举债扩建为主要叙事的 ORCL，代表性有限 |
| 6 | 软件／大型科技 | NOW（或 MSFT） | CRM | 2026-08-04 | downtrend_break（同日 platform_breakout） | NOW、MSFT 窗口内两类时刻都没有符合的（只有无前置下跌的 downtrend_break）；按池内顺序 ORCL 已用，取 CRM，之前 2026-06-09 failed_breakout |

说明：分类细则（`failed_breakout` 算下跌类、`downtrend_break` 与 `failed_breakdown` 算反弹类、“之前的下跌类”限在窗口内）是在列出这几只股票的时刻类型与日期之后写定的，没有看任何结果字段。替代股的选择有主观成分。

## 两组
同一命令，模型 `gpt-6.1-terra`，宿主 Codex：

```
scripts/dev-research.sh codex <TICKER> --as-of <DATE> --model gpt-6.1-terra --tag <tag> --prompt "<说明>"
```

- 对照组 `--tag abctl`：`我目前按标准仓位持有。`（回放按 Skill 默认跳过第 9 步）
- 心法组 `--tag abpb`：`我目前按标准仓位持有。本次回放例外，要做 investment-decision 第 9 步心法自检（引用交易者心法）：只读 trader-playbooks-synthesis 卡“针对四个毛病的对治”一节，不读该卡其他小节，不读各交易者卡与案例卡（它们含截止日之后的信息）。`

共 12 次；最多 2 路并行；单次失败重试一次；遇到 Codex 额度上限即停，不绕过。先单跑 1 次确认流程（有报告、有 `decisions.jsonl`）。

## 比较指标（逐只并排）
- 动作（ADD／HOLD／REDUCE 等）、仓位、置信度。
- 方向预测，含 `relative_return_60d` 的方向与概率。
- 改判条件：条数；是否含可观察的具体条件（价格位或经营事实）；失效条件是否写了。
- 心法组：是否写了“心法自检”一行；四组各答了什么；是否有某组导致结论改变及依据。
- 心法组是否违规读了其他卡（查 `transcript.log`）。
- 每次耗时。
- 参考：截止日后 60 个交易日个股与板块 ETF 收益（取自事件表 `outcome`），只附表，不据此下结论。

## 已知局限
- n=6，每组每只只跑一次。
- 同一模型同一提示词两次运行本身就有随机差异；本次没有“同提示词跑两次”的噪声对照，所以小差异（仓位档、置信度几个百分点、改判条件多一两条）不能归因于心法。
- 综合卡写于 2026-11，自检问题本身不含结果，但措辞受之后的经历（6–8 月的讨论与结果）影响；心法组提示词也让模型知道“存在截止日之后的信息”。
- 模型训练记忆无法排除（2026 年 6–8 月的走势可能已在训练数据中），两组同样受影响，但可能与自检提示交互。
- 心法组只多了一步，同时也多了一段提示词，变化可能来自提示词长度或“被提醒”本身，而非心法内容。
- 两只替代股（TXN、ORCL）对原方向代表性有限；样本按价格行为选，偏向下跌后时刻。
