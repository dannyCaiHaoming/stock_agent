# 当前实施任务

本任务清单取代旧“单股→三股完整 Council”验收。历史 5.3、5.4、5.5 已作废，新编号不继承旧验收义务。已有实现的证据适用性已由 5.2 核对；独立复核与人工完成批准分别记录在 5.3、5.4，不能扩大为完整 Council 或候选版本晋升证明。

已有证据索引（待核对适用范围，不自动继承 PASS）：1.1 参考 `docs/data/nasdaq-primary-backup-progress.md`、`docs/data/sec-collection-progress.md`；1.2–1.4 参考 `reviews/development/live-data-seams-closeout.md` 和 `reviews/development/live-sec-history-isolation-fix.md`；2.1–2.2 参考 `reviews/development/common-stock-holding-analysis-evidence.json`，并核对 `tests/test_common_stock_research_contracts.py` 的实际覆盖。适用性记录应包含对应命令、输入、代码/配置版本及产物路径；缺失则如实列出，不补造历史证据。

## 1. 保留真实数据基础

- [x] 1.1 已实现并验证 NASDAQ 目录、Yahoo/yfinance 主行情、AKShare/东方财富受控备用和 SEC 披露的有界只读适配，保留既有来源样例与聚焦测试作为实现证据。
- [x] 1.2 已实现证券身份核实、行情与披露标准化、SEC 财务期间处理、原始内容 hash 和完整 `source_id`/`as_of`/`published_at`/`retrieved_at` 血缘，并有相应正负测试。
- [x] 1.3 已实现外置缓存、请求预算、主备 SourceSelection、单来源价格口径、失败原因和 Provider 拒绝即停，并有相应正负测试。
- [x] 1.4 已实现统一 cutoff、候选事实冻结、PIT 排除、Evidence Closure 和结构化数据缺口，并被后续普通股数据准备代码复用。

## 2. 对齐 PortfolioHandoff 与下游研究

- [x] 2.1 已存在从确认 `PortfolioHandoff v3` 派生内部普通股采集请求的接缝，并验证只提取普通股且不丢失权威 Handoff 绑定。
- [x] 2.2 已存在普通股研究阶段对冻结 Gate、data-preparation manifest 和逐证券 source bundle 的消费接缝，可按 `security_id` 读取 Evidence 与缺口而不重新访问 Provider，并在 Agent 前拒绝 hash 或绑定漂移。
- [x] 2.3 保留现行无三股上限的 `live-portfolio/2.0.0`，用超过三只的合成输入确认全部普通股进入采集计划和当前 v4 快照契约；预算耗尽的未执行项须显式记录，不能静默截断。不声称有限测试证明无限吞吐；旧 profile/v1/v3 三股限制仅保留为历史兼容。
- [x] 2.4 将旧 `--profile live-us-equity --portfolio ...` 产品入口改为明确拒绝并提示使用确认 Handoff 的数据准备入口；验证不能静默进入 fixture 或旧 Council。

## 3. 收缩当前契约

- [x] 3.1 列出拟删除文件/函数及现行、动态配置、历史读取消费者；保留当前采集请求 v2、SEC fact v1、来源访问 v4 等实际使用版本。清单明确删除或保留理由，不统一升版或增加兼容框架。
- [x] 3.2 对清单中无保留消费者的旧契约分支做最小删除；当前 v4 准入记录移除误放的三股产品上限，批准、暂停、拒绝、hash 校验、缓存和历史锁语义保持；必要历史 profile/Schema 保留并记录理由。
- [x] 3.3 合并当前来源说明和实现限制，历史技术试拉、临时目录、单次响应及故障过程只保留在历史记录；检查产品文档不再把试拉当运行前置条件。

## 4. 退役旧完整 Council 路径

- [x] 4.1 退役 `prepare-live-batch`、`launch-live-batch`、`summarize-live-batch` CLI/宿主入口；依照 3.1 清单删除无保留消费者的 `live_batch` 实现及 Schema。验证旧入口不启动模型且返回明确错误或不再提供该命令。
- [x] 4.2 仅删除清单确认无消费者的旧 live Council 共享模块分支；保留 `collection.py` 所用 `live_input.py` 函数和其他必要代码，无法安全拆分时记录保留理由即可完成。fixture、普通股数据交接及多维补充资料入口已通过受影响接缝验证，不要求所有旧分支清零。
- [x] 4.3 检查代码、配置、Markdown、JSON manifest 与归档记录引用后，清理无引用的专属测试和重复说明；被引用的历史报告保持原样。私人截图、运行包、原始数据和历史锁不删除。交付具体保留/删除清单，并确认后续多维研究模块不在误删范围。

## 5. 限定验收与完成批准

- [x] 5.1 使用合成 PortfolioHandoff 执行数据准备聚焦测试，覆盖多持仓无产品上限、主源成功、允许备用、禁止备用、身份冲突、Future Evidence、缓存复用、实际 Handoff 采集入口的单证券失败隔离和下游消费；未启动产品 LLM、旧三股 Council、Regression 或完整 Gate。
- [x] 5.2 与 5.1 合并执行 301 项必要聚焦验证，核对已有证据适用范围，并通过 OpenSpec strict validate、退役入口与引用检查。来源访问适配器未改变网络请求语义，复用既有真实采集证据，未重新联网或重测研究深度。
- [x] 5.3 完成一次独立只读差异复核，确认旧产品启动入口已退役、数据包可被现有消费者校验读取、必要共享实现和历史引用保留；不要求共享旧代码全部删除，不把结构可读称为资料充分或 DOWNSTREAM_READY，不重跑产品 LLM 或完整 Gate。
- [x] 5.4 已向用户提交清理摘要、保留/删除文件清单、测试结果和残余兼容风险；用户于 2026-09-16 明确批准同步且归档。本 Change 完成不代表 Council、投资建议或候选版本晋升通过。
