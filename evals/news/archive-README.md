# 新闻前向存档（moomoo news_search）

背景见 `source-probe-2026-10-27.md`：moomoo 新闻没有历史接口（每次最多 50 条、无日期与分页参数），热门票只覆盖最近 2–3 周，所以只能从今天起每日存档，前向积累样本。

## 存什么

入口：`scripts/snapshot-news.sh`（调用 `scripts/snapshot-news.py`），日志 `.local/data/history/news-run.log`，退出码 1 表示有失败。

- 股票池：`evals/replay/universe.txt` + 可选 `.local/data/watchlist.txt`，去重（当前 113 只）。
- 每只股票各查 `news_type=1`（新闻聚合）和 `news_type=3`（研报聚合，标题多为 TipRanks 汇总，不含评级与目标价，只是“有分析师动作”的存在信号）。`size=50, sort_type=2, lang=en`，串行、间隔 1–2 秒，失败重试一次。不抓 type 2（公告流基本是杠杆 ETF 备案）。
- `.local/data/history/news/<YYYY-MM-DD>.jsonl`（日期为纽约时间）：每个 (ticker, news_type) 一行，含 `retrieved_at, source_id, query, items[]`；item 含 `rank, news_id, news_type, title_raw, title_clean`（去 `<em>` 等标签）`, publish_time{raw, utc}, url, domain`。不存正文和图片。
- `.local/data/history/news/first-seen.jsonl`（只追加）：每个 `news_id` 首次被我们观察到的 `first_seen_at`，以及首次查到它的 ticker、`publish_time`。

同日已完成的 (ticker, news_type) 会跳过，失败后直接重跑即可补缺；`--rerun` 同日追加新一行；`--tickers`、`--out-dir` 用于调试。

## 时间语义

- `publish_time`：moomoo 给出的发布时间（秒级 Unix），来源方自报，可能早于我们看到它很久（聚合了第三方内容）。
- `first_seen_at`：我们第一次在查询结果里看到该 `news_id` 的时间，是点时（point-in-time）证据。
- 回测或前向评估里一条新闻的“已知时间”取 `max(publish_time, first_seen_at)`。存档启动当天（2026-10-27）的 `first_seen_at` 对此前已发布的内容只是上界，不代表当时已知；正式统计应只使用存档启动之后 `first_seen_at` 与 `publish_time` 相差不大的条目，或把启动日之前的条目整体排除。
- 一条新闻若在下一次抓取前就已滚出 50 条窗口则会漏；热门票 50 条约覆盖 2–3 周，每日一次不会漏。
- `rank` 是该次返回的序位，同一新闻可被多个 ticker 查到，`first-seen.jsonl` 只记第一次；ticker 归属以查询词为准，响应本身无实体标注，使用时需相关性过滤。

## 条款与使用边界

内容是 TipRanks、Seeking Alpha、moomoo 用户帖等第三方标题。只存标题、时间、URL 供内部研究，不转载、不存正文；引用时保留来源与链接。按 `product/vendor/moomoo-skills.md`，moomoo 内容只作参考，不参与研究判断；本存档只能当“事件存在信号”，不当情绪或方向判断。

## 建议调度

每日一次，美股收盘后（纽约 17:00 之后，约北京次日 05:00 后）。113 只 × 2 类约 226 次调用，单次响应偏慢，整轮估计 30–40 分钟。
