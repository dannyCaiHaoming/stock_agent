# Tiger Brokers Hong Kong 严格只读接入

本能力只用于用户明确启动的本地账户数据同步，不是研究数据源、Agent Tool、MCP 或交易系统。第一版锁定官方 Python SDK `tigeropen==3.8.0`，发行 wheel SHA-256 为 `8f87fe69997d9c25463b04b2646dcd7b2e395209058195514675ab675cd3563a`。

官方依据：

- `https://pypi.org/project/tigeropen/3.8.0/`
- `https://github.com/tigerfintech/openapi-python-sdk`
- `https://quant.itigerup.com/openapi/en/python/operation/trade/tradeList.html`
- `https://quant.itigerup.com/openapi/en/python/operation/trade/accountInfo.html`
- `https://quant.itigerup.com/openapi/en/python/permission/requestLimit.html`

## 第一版能力矩阵

| 数据 | 官方方法 | 分页/窗口 | 第一版状态 |
|---|---|---|---|
| 账户发现 | `get_managed_accounts` | 当前值 | 合成契约完成，真实 TBHK 字段待验收 |
| 当前资产 | `get_prime_assets` | 当前值 | 官方已记录字段，真实分段范围待验收 |
| 当前持仓 | `get_positions` | 按 STK/OPT 分次读取 | 官方已记录字段，期权调整合约待验收 |
| 历史资产 | `get_analytics_asset` | 有界日期窗口 | 官方已记录字段，最早可追溯日期待验收 |
| 全状态订单 | `get_orders` | 时间窗 + `page_token` | SDK 3.8.0 已核对 |
| 逐笔成交 | `get_transactions` | 时间窗/订单 + `page_token` | Prime 账户限定，TBHK 返回待验收 |
| 订单费用 | `get_order(show_charges=True)` | 按订单 | SDK 3.8.0 已核对 |
| 资金明细 | `get_fund_details` | `start/limit` + 日期 | 字段和终止条件待真实 TBHK 验收 |
| 出入金 | `get_funding_history` | Provider 可见历史 | 官方已记录，无分页能力证明 |

适配器只暴露上表读取方法。下单、预览、改单、撤单、换汇、转账、交易解锁、Push 和任意字符串方法调用均没有入口，并在发出网络请求前拒绝。

## 管理台与本地文件

用户需要在 Tiger 开放平台启用 OpenAPI，并把官方生成的 `tiger_openapi_config.properties` 和 TBHK `tiger_openapi_token.properties` 放入仓库外、仅当前用户可读的目录。配置至少需要 `tiger_id`、`account`、`license=TBHK`，以及官方 SDK 3.8.0 支持的 `private_key`、`private_key_pk1` 或 `private_key_pk8` 之一；Token 文件需要 `token`。Tiger 公钥仅用于验证服务端响应，不能替代用户私钥。聊天、命令参数、Git、网页和普通产物不得包含这些值。

首次同步还需要用户在本地指定 `history_start` 和 `history_start_accuracy=EXACT|APPROXIMATE`。第一版最多证明 `API_COMPLETE_WITHIN_DECLARED_WINDOW`，不会声称已取得开户以来的完整生命周期，也不解析券商结单。

建议在 Tiger 开放平台完成以下准备：

1. 确认账号属于 Tiger Brokers Hong Kong，并在官方管理台开通只读 OpenAPI 所需权限；不为本项目开通或提供交易授权。
2. 下载官方配置文件并完成 TBHK 问卷/协议；确认配置中的 `license` 是 `TBHK`。
3. 在官方流程中生成 Token 文件。Token 到期或认证失败时，只在官方管理台/SDK 流程中续期，不把值粘贴到聊天、环境变量或仓库文件。
4. 选择一个仓库外私人目录保存配置，另选一个仓库外私人目录保存账本。目录权限设为 `0700`，两个配置文件权限设为 `0600`；目录和数据库都不得是符号链接。

## 显式运行流程

所有真实账户请求只能由宿主入口启动。下面的路径是占位符，不应替换成仓库内目录，也不要把凭据值放入命令参数。

```bash
bash scripts/run-product-smoke.sh --tiger-readonly preflight \
  --config-dir /path/outside/repository/tiger-config

bash scripts/run-product-smoke.sh --tiger-readonly snapshot \
  --config-dir /path/outside/repository/tiger-config \
  --ledger-root /path/outside/repository/private-ledger

bash scripts/run-product-smoke.sh --tiger-readonly sync \
  --config-dir /path/outside/repository/tiger-config \
  --ledger-root /path/outside/repository/private-ledger \
  --history-start 2024-01-01 \
  --history-start-accuracy APPROXIMATE \
  --window-end 2026-09-23
```

`history_start=EXACT` 只适用于用户能证明该日就是需要覆盖的真实起点；不确定时必须使用 `APPROXIMATE`。同步是一次性的显式命令，没有 daemon、自动计划任务或网页同步按钮。相同窗口重跑用于验证去重，增量同步应带重叠窗口以接收订单状态和费用修订；任何失败窗口都会保留 gap，水位不会跨过它。

同步后，使用同一宿主入口生成冻结分析：

```bash
bash scripts/run-product-smoke.sh --tiger-readonly analyze \
  --ledger-root /path/outside/repository/private-ledger \
  --account-ref 'snapshot 输出的脱敏 account_ref' \
  --cutoff 2026-09-23T23:59:59Z
```

浏览器只读接入使用已有入口的可选参数：

```bash
python3 -m product.web.cli \
  --memory-root /path/outside/repository/research-memory \
  --trade-ledger /path/outside/repository/private-ledger \
  --port 8765
```

`/trades` 刷新、筛选和版本切换只读取已保存 SQLite，不连接 Tiger、不刷新 Token、不调用模型，也不提供原始对象下载。未配置 `--trade-ledger` 时页面明确显示未配置，并且不会扫描默认路径。

## Intake 与复盘边界

- 当前快照中的 US/USD 普通股、ETF 和上市期权可转换为现有 `PortfolioDraft v3`，但仍必须由用户明确确认一次才能生成 Handoff。
- 混合账户只把已完整声明的 US/USD 子组合标为 `USER_DEFINED_PORTFOLIO`。港股、HKD 和其他当前不支持资产保留在账户覆盖清单并显示“投研接入待定”，不会被静默丢弃、换汇或写入会阻断子组合确认的 `unsupported_assets`。
- 全账户净资产、现金和保证金不会冒充 US/USD 子组合字段；只有 Tiger 明确返回 USD 分段值时才进入混合账户 Draft。
- 交易复盘只聚合 US/USD 受支持资产；非 USD、未知身份和 coverage gap 都显示排除计数或限制。FIFO episode 仅供复盘，不是税务 lot；结果不是券商结单、税务报告或策略回测。
- 页面内六组图形数据来自同一个冻结 `TradeHistoryAnalysis`：资产/净入金/收益、回撤、月度收益率、证券盈亏/费用、持有期与净盈亏、活动时间线。月度收益率和月度美元净盈亏不得混用。

## 故障处理

| 状态 | 含义与处理 |
|---|---|
| `TIGER_CONFIG_*` | 配置目录、文件、权限或 TBHK 牌照不满足要求；只修复对应本地条件，不输出文件正文。 |
| `TIGER_SDK_NOT_INSTALLED` / `TIGER_SDK_VERSION_MISMATCH` | 在隔离环境安装锁定的 `tigeropen==3.8.0`，不要自动升级。 |
| `TIGER_HOST_LAUNCHER_REQUIRED` | `snapshot`/`sync` 被从底层 CLI 直接启动；改用宿主入口。 |
| `TIGER_SYNC_RATE_LIMITED` / `TIGER_SYNC_TIMEOUT` | 当前窗口保留 gap；稍后显式重跑相同或带重叠窗口，不手工推进水位。 |
| `BROKER_LEDGER_BUSY` | 同步事务或其他进程正在占用账本；等待后重试。浏览器不会写入或迁移账本。 |
| `BROKER_LEDGER_VERSION_UNSUPPORTED` | 当前代码不认识该账本版本；停止读取，不降级改写，保留原文件。 |
| Token 失效 | 通过 Tiger 官方流程续期仓库外 Token 文件，再从 `preflight` 开始；网页与分析不会代替续期。 |

真实验收记录只允许保存脱敏状态、类别计数、时间窗、gap 和 hash。私人账本、配置、日志、持仓、交易和分析始终留在仓库外，不进入 Git 或 Research Memory。
