# Market 免费来源真实观测

- 观测截止：2026-09-19T15:53:41Z。
- 快照：`market-context-snapshot/1.0.0`，状态 `FROZEN`，文件 SHA-256 `37fde66ea8af01e392780de3fc6a9816109d0f350e1445768e8acc26398cd0a3`，snapshot hash `619cd6235e4461fd74d9197604ab3da5c9ef26e29b7bdd2a1ee2779d2072d792`。
- 实际请求：Yahoo 公开 chart 18 次加 news search 1 次；无失败 event，共冻结 1,135 条序列 Evidence。
- 覆盖：SPY 大盘、11 个 Select Sector 板块代理、TLT 长久期美债、UUP 美元、GLD 黄金、USO 原油、HYG 高收益信用代理和 VIX 波动指数。ETF 均显式标为 proxy，不冒充现货、指数原值或资金流。
- 24 小时新闻：请求成功，窗口内归一化去重后为 0 条，以 `MARKET_NEWS_WINDOW_EMPTY` 保留；这是有效的空窗口观测，不用旧新闻或模型记忆补齐。
- 正式消费：全量序列进入 Gate，`MARKET_STATE` invocation 按序列有界选取最新两个观察，防止数百日线直接放大模型上下文；大盘趋势仍使用现有确定性市场统计产物。

该观测只证明当时可达；日后超时、限流或字段漂移必须降级对应数据集，不得沿用本次成功状态。
