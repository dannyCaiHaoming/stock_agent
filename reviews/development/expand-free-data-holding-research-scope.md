# 免费多维持仓研究：实施范围基线

记录日期：2026-09-15
Change：`expand-free-data-holding-research`

## 已完成且复用的能力

- `PortfolioHandoff v3` 已能保留普通股、ETF、期权与账户资金，并向 Council 交接。
- `COMMON_STOCK_RESEARCH` 已能从确认持仓派生逐股请求，以三槽有界并行调用 `runtime_company_analyst`，验证并保存 `EquityResearchReport` 和中文报告。
- 现有 live 资料代码已包含 Yahoo/AkShare 行情路由、SEC 公司披露、缓存、PIT Gate 与来源元数据。
- 既有 `company-research`、`valuation`、`catalyst-analysis` 和 `evidence-grounding` 继续负责公司研究；本 Change 不复制这些能力。
- `runtime_market_catalyst.toml` 文件已存在，但实施前尚未在产品配置注册，且旧契约只覆盖 CatalystMap；不能把文件存在视为新维度已经可运行。

## 本 Change 修改范围

- 新增 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 显式阶段，保留旧阶段行为。
- 新增 `ResearchDimensionReport`、`HoldingResearchBundle`、新维度 Skill、必要的只读资料/计算接缝、中文渲染和聚焦测试。
- 扩充现有 Company Analyst 与 Market Catalyst 的能力模式；不新增投资 Agent。
- 只研究确认持仓中的普通股。ETF 与期权仍留在组合覆盖表中，并明确为本次未覆盖。
- 不启动 Skeptic、CIO 或 Risk，不生成 BUY/HOLD/REDUCE 等组合动作。

## 与暂停 Change 的边界

`us-equity-live-advisory-slice` 继续暂停，其任务状态、历史证据和版本锁不在本次修改范围。当前工作树中的 `product/mcp/live/`、live schemas 与测试属于其未提交实现基线；本 Change 只复用其已经存在且实际需要的只读资料接缝，并在最终差异中逐项标明新增部分。不得借本 Change 勾选、归档或修改暂停 Change 的任务。

## 禁止范围

- 不接券商、账户写入、真实下单或自动组合决策。
- 不建设新沙箱、代理、Replay、Regression、Calibration、Ablation 或 Promotion 平台。
- 不开发 ETF/期权持仓专项研究，不做全市场选股。
- 不把指标阈值或确定性评分改造成投资判断规则。

## 首阶段依赖判断

P1 价格成交量研究只依赖确认普通股身份、日线 OHLCV/公司行动、广泛市场基准、PIT Gate、确定性计算与技术结构 Skill。它不依赖研报、所有权披露或期权数据可用，因此这些后续来源失败不得阻塞 P1。
