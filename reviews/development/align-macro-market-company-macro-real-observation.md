# Macro 官方来源真实观测

- 观测时间：2026-09-19T15:44:41Z 至 2026-09-19T15:44:53Z。
- 执行边界：临时隔离 Python 环境，仅安装项目锁定的 `certifi==2026.7.22`；运行输出位于 `/tmp`，未把缓存或正文提交到仓库。
- 快照：`official-macro-snapshot/1.1.0`，状态 `FROZEN`，文件 SHA-256 `12fee3019056626f0c7f867332e09cd759df27dc3f854f675bf686cbac0abc2a`，snapshot hash `87ee2b9bda2c745a44cfb62595925a5a98b1276fb8f229dee64aa42fd45aec5e`。
- 来源请求：BLS timeseries 1 次、Treasury CSV 1 次、BLS iCalendar 1 次、Federal Reserve RSS 1 次加官方政策正文 1 次；全部 HTTP 200，本次 gaps 为空。
- 冻结字段：`us_cpi_all_items`、`us_unemployment_rate`、`us_total_nonfarm_payrolls`、`us_treasury_10y_yield`、`federal_reserve_monetary_policy_text`、`bls_announced_release_calendar`。
- 时间与修订：BLS/Treasury 值分开观察日与保守获取时间；Fed 正文使用官方 RSS pubDate 作为 `published_at/as_of`；日历只冻结 BLS 已公布 VEVENT；后续修订以新 raw hash 保留，不覆盖已冻结版本。

本观测证明免费官方端点在该时点可用，不把一次成功固化为永久 AVAILABLE；每次运行仍应以 events、gaps 和 PIT 过滤表达实际状态。
