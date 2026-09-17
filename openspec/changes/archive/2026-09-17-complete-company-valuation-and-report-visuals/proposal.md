## Why

当前系统已有冻结行情、SEC 财务、估值 Skill 和相对表现 SVG，但尚无统一估值快照、按当时已公开资料构造的历史估值序列，以及直接可读的图文研究报告。需要把现有数据转化为用户能够核对价格、盈利口径和历史位置的研究材料。

2026-09-17 验收后修订：MRVL 模型运行超时且出现源码完整性与终态记录问题。将解除本次估值图文交付阻断所需的有界查询、引用校验、运行隔离及失败归集直接纳入本 Change，继续原任务，不拆分新需求。

## What Changes

- 使用现有 SEC、Yahoo 和已批准的 Moomoo Quote 数据能力，形成当前估值快照；分别保存供应商报告值与系统计算值，展示 PE、P/S、P/B、FCF Yield、EV 与条件可得的 EV/EBITDA、forward PE。
- 新增逐历史观察点的 PIT 财务选择与期间标准化，优先交付可复算的 trailing PE 历史；默认申请近五年、月末采样，覆盖不足如实显示。历史 forward PE、历史一致预期和完整 EV 序列不承诺免费可得。
- 形成 K 线/成交量/均线、相对表现与回撤、财务趋势和历史估值图；同一冻结数据驱动 JSON、图表与中文报告，缺口和重组断点显式呈现。
- 报告展示估值口径、有效样本、覆盖范围及必要限制；Company Analyst 使用既有 valuation Skill 解释适用性，不把分位或指标阈值自动变成投资结论。
- 将现有多维 SVG 扩展为版本化图表产物，并通过研究报告呈现接缝输出可本地打开的静态 HTML 和可移交的 Markdown/JSON/图表目录。
- 明确数据可行性、最小真实验收与条件增强范围；保持现有 Agent 分工。数据不足时保留逐指标状态，不影响其余资料交付。
- 补齐估值所需的基本面解释材料：公司指引及修订、SBC/回购/稀释与 GAAP–non-GAAP 调节、债务到期和流动性、公司自定义经营 KPI、客户集中度及治理披露；复用现有 SEC 候选原文和财务字段，补标准化、证据核实与报告消费，不重复建设采集底座。
- 增加有明确定义的盈利质量/资本效率/偿债比率，以及最多 5 家、默认 2–3 家经核实可比公司的经营与估值对照；由既有研究角色解释可比性，不做行业固定阈值或机械排名。
- 条件提供财报实际值与事前预期对照；只有预测版本、财政期和会计基础可验证时计算 surprise。不承诺完整历史一致预期、免费完整电话会全文或完整供应链数据库。

- 修复本次验收接缝：有界小型启动包、既有冻结事实查询与真实附件工具接入、预计算/本次计算引用闭合、当前开发工作区保护、本地超时清理、状态一致性及 MRVL 实际图文交付；本轮不预设新增通用分页目录或生命周期平台。

## Capabilities

### New Capabilities

- `equity-valuation-history`: 当前与历史 PIT 估值、支持估值解释的公司基本面补充、有限同行对照、口径/覆盖约束及现有研究消费。
- `equity-research-visuals`: 同源价格/财务/估值图、指引/质量/债务/KPI/同行补充图表、图文研究报告、可追溯数据及缺口显示。

### Modified Capabilities

无。运行修复作为本次 equity-valuation-history 附件消费与验收要求纳入现有两份规格，限定新版本估值研究路径；不改写既有研究结论、动作权限或历史锁定报告语义。

## Impact

- 复用 `product/mcp/live/{sec,financials,market,yahoo_research}.py`、研究 supplement/Gate/MCP、`product/deterministic/valuation.py`、`product/deterministic/market_analysis.py`，增加专用估值与历史选择契约。
- 扩展 `product/council/technical_chart.py`、研究输出和运行包接缝；采用独立版本化附件索引，旧报告无附件时保持可读。
- 基本面补充复用 `collection.py`、`disclosure.py`、`research_supplement.py` 与现有 company-research/industry-comparison Skill；同行仅是经批准的研究参照，不加入用户持仓、不触发额外 Agent 或组合决策。
- Moomoo 仅作已验证字段的补充；本 Change 无须新增第四数据源、付费 API 或通用 OpenBB 后端。不新增 Agent、交易、全市场扫描、完整 DCF 或自动后台采集。
- `capture-futu-client-research-data` 当前实现仍有未收尾内容；复用补充数据与真实 launcher 前，核对其完成状态和适用证据，不复制其等待屏障任务。本 Change 可先完成规划及独立确定性实现，最终真实集成验收依赖该接缝可用。
- 本次修订只更新规划。运行增量涉及 common_stock_stage、fixture_mcp、equity_research_package、codex_hook_recorder、nested_codex 及相关 Schema/Agent 配置；实施前复核共享文件现有修改，不复建等待屏障、不全局切换其他运行模式。
- 既有确定性与独立复核证据保留；4.1、6.5、6.6 按本轮暴露的缺口/增量重新打开，第 7 组集中补齐运行修复，随后继续 6.4/6.7。已消耗的一次 MRVL 模型授权不自动续期，后续真实运行需新的明确授权。
- 当前环境对“所有本地与远端进程均只读”的强保证仍为 UNVERIFIED，本轮不把该宿主级证明设为完成前提。验收目标是模型运行使用隔离临时源码副本或受支持的只读来源，只有运行产物目录可写，并以运行前后 hash 证明当前开发工作区未被改动；本地进程树须有界终止，远端取消未知如实记录且不得自动重试。
