# 美股真实数据准备：使用说明

`us-equity-live-advisory-slice` 当前只负责为普通股持仓研究准备冻结、可追溯、符合 point-in-time 的数据包。它不产生 Thesis、买卖动作、置信度或组合决策，也不启动 Skeptic、CIO 或 Risk Engine。

## 输入和输出

用户入口是已确认的 `PortfolioHandoff v3`。数据准备层从完整 Handoff 中提取全部普通股，不设三股产品上限；ETF、期权、现金和账户项仍保留在权威 Handoff 中，不被改写为普通股。

内部采集请求使用 `live-portfolio/2.0.0`，用途固定为 `COMMON_STOCK_DATA_COLLECTION`。典型产物包含：

- `collection-input.json`：从已确认 Handoff 派生的内部采集请求，仅含取数所需证券标识，不携带成本、浮亏或投资判断；
- `source-bundle.json`：整批来源清单、Handoff/版本/hash 绑定及每只证券的成功或失败状态；
- `source-snapshots/<security>/snapshot.json`：每只成功证券各自冻结的原始来源、SourceSelection、标准化事实、访问事件、身份绑定与数据缺口；
- `gate.json`：允许和排除的 Evidence，包括 cutoff、PIT 原因与 Evidence Closure；
- `data-preparation.json`：按 `security_id` 绑定的下游消费清单。

每条事实必须保留 `evidence_id`、`source_id`、`as_of`、`published_at` 和 `retrieved_at`。缺失、过期、未公开或晚于 cutoff 的事实不得进入 Agent 上下文。

## 数据来源与路由

当前数据基础保留：

- NASDAQ screener：有界股票目录和身份线索；
- Yahoo/yfinance：主行情来源；
- AKShare/东方财富：只在允许的暂时性失败或空行情下作受控备用；
- SEC：公司身份、申报元数据、财务事实及已实现的披露材料。

身份、Schema、原文、时间完整性、401/403/429 等失败必须 fail-closed，不得通过换源规避。共享来源配置在任何证券请求前统一验证；随后按证券冻结，单只身份或取数失败进入 `source-bundle.json`，不会删除其他成功证券。每只证券、每个时间窗只能选择一个完整价格来源，不逐字段拼接。缓存为内容寻址且位于仓库外，缓存命中仍重验 hash、版本、cutoff 和来源路由。

当前批准、上游核实状态、请求预算、最小域名和历史技术试拉记录见 [美股真实数据：来源与访问条件](../data/us-equity-sources.md)。历史试拉不是当前运行前置，也不能直接成为 Council Evidence。

## 当前产品入口

宿主 Terminal 使用已确认 Handoff 进入普通股持仓研究；如果没有现成 Gate，入口会先调用现有只读适配器准备数据：

```sh
bash scripts/run-product-smoke.sh \
  --stage common-stock-research \
  --handoff "$confirmed_handoff" \
  --model gpt-5.6-terra \
  "$new_external_bundle"
```

如需采集，宿主环境须设置仓库外 `LIVE_SOURCE_ACCESS_FILE`、`SEC_USER_AGENT` 和可选 `LIVE_CACHE_ROOT`。真实持仓、联系邮箱、cookies、凭据、原始数据及运行包不得提交 Git。Provider 只接收证券、日期等必要取数参数，不接收数量、成本、现金或研究问题。

底层 `collect-live` 的共享采集与校验仍被当前 Handoff 流程复用。`prepare-live` 已改为显式拒绝：它不会读取输入文件、访问网络或启动模型；历史包继续由只读 Replay/校验器读取。以下旧入口已退役：

- `prepare-live`；
- `--profile live-us-equity --portfolio ...`；
- `prepare-live-batch`；
- `launch-live-batch`；
- `summarize-live-batch`。

旧 host profile 会明确返回 `LIVE_COUNCIL_ENTRY_RETIRED`，不会静默回退 fixture，也不会启动模型。

如果显式复用既有数据包，`--gate` 必须和 `--data-preparation`、`--source-bundle` 同时提供。入口会重算校验 Gate、准备清单、批次来源包、逐证券 snapshot、SourceSelection 和 Evidence 绑定；缺件或 hash 漂移会在 Agent 启动前失败，不能只交一份可被重新签名的 Gate。

## 资源边界与失败隔离

持仓数量不设产品上限，但每次采集和后续研究都受请求数、时间、并发数与模型成本预算限制。预算耗尽、单证券失败或能力不覆盖时，未执行项必须按 `security_id` 记录原因，不得静默截断，也不得将剩余证券冒充完整组合。

Company Analyst 可通过既有只读工具请求额外研究资料；任何新返回的材料必须先冻结、记录来源和时间、重新经过 PIT Gate，才能进入后续分析。搜索线索、候选同行或未冻结网页不是 Evidence。

## 验收边界

本能力的验收只证明：Handoff 转换完整、来源路由可校验、PIT 和 Evidence Closure 失败关闭、缓存可重验、单证券失败隔离，以及下游能按 `security_id` 读取冻结资料。它不证明研究深度、完整 Council、投资建议、Risk 结果或候选版本晋升。
