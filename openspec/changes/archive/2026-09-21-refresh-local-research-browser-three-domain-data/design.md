## Context

参见 [proposal.md](proposal.md) 的动机。现有网页由标准库 HTTP 服务、`ReadOnlyResearchMemory` 和 `ArtifactCatalog` 组成；`ArtifactCatalog` 仅扫描固定快照、计算、附件和多维报告位置，尚未识别 `audit/provider-coverage.json`。Macro 与 Market 已按所选快照进行来源、run 和 cutoff 绑定，Company 则以 Memory View 为主并从冻结运行中补充附件和四类报告。

新版数据准备在运行目录生成 `research-provider-coverage/1.0.0`。它包含 provider 观察、数据集到 capability 的路由以及 Capture / Gate eligible / Delivered / Actual research use 状态。该产物是审计摘要，不是新的事实库，也不能替代原始 Evidence、快照或研究报告。同一运行的 `evidence/gate.json` 已冻结对应实际值；第一轮页面只接入 coverage，导致用户只能看到 12/100/192 等计数而看不到宏观指标、FedWatch、Put/Call、IV 或合约字段。

## Goals / Non-Goals

**Goals:**

- 在现有只读适配层内安全读取 coverage，并为三域构造小型展示模型。
- 对 coverage 明确声明且同运行 Gate 允许的 Macro、Market 与 Options Evidence 建立语义白名单 projection，让用户先看到实际冻结内容，再查看技术审计。
- 让用户一眼区分“采到”“通过 Gate”“已交付”“实际被研究使用”和“报告存在”。
- 将新增 Macro、Market、Company 和 Options 数据能力放回正确研究域，同时保持旧运行可读。
- 保持页面无需 JavaScript、外部资源或新的服务依赖。

**Non-Goals:**

- 不在网页中调用 OpenD、SEC、Yahoo、官方宏观来源或任何 Provider。
- 不由浏览器计算新的宏观、市场、期权或资金流结论。
- 不在浏览器新增投资评分、资金方向判断或预测；只允许确定性的单位格式化、排序、分组及由原始 Call/Put 值计算直接展示比例时的显式标注。
- 不修改 coverage schema、数据准备路由、Agent/Skill 输入或 Research Memory。
- 不新增 Options Agent、数据源 Agent、浏览器数据库、通用查询 DSL 或第二套产物索引。
- 不把本次页面验收扩大成真实产品 Smoke、Runtime Eval 或候选晋升。

## Decisions

### 1. 将 provider coverage 作为现有 ArtifactCatalog 的一种受支持审计产物

在固定候选位置加入 `audit/provider-coverage.json`，registry 增加 `research-provider-coverage/1.0.0` 类型。读取时核对 `coverage_hash`、必要字段类型、decision cutoff 和现有 source context；仍使用显式 run dir/run root、有界直属目录发现和 `_safe_regular_file` 防护。

选择该方案是因为 coverage 已随运行冻结，且网页已有版本化产物 registry。替代方案是新建 coverage 服务或扫描所有 JSON；前者重复生产侧职责，后者扩大暴露面和目录成本，均不采用。

### 2. 在读取层生成领域化 projection，不把完整 coverage 直接交给模板

读取层按 capability 建立允许映射：

- Macro：`MACRO_CONTEXT`。
- Market：`MARKET_STATE` 与 `OPTIONS_FLOW`，两者分区。
- Company：`FUNDAMENTAL_EVENT`、`RESEARCH_REPORT`、`OWNERSHIP_DISCLOSURE`、`INDUSTRY_COMPARISON`；只保留目标 security 或明确共享记录。

coverage projection 仅保留 dataset、provider/source layer、scope、状态、计数、时间、failure code、limitations、capability 和稳定身份。共享 Macro/Market dataset 的 coverage `security_id` 只表示本运行服务的研究对象，projection 将其标为共享环境；只有 `OPTIONS_FLOW` 保留证券范围。模板不接收任意 coverage 嵌套原文，因此既降低私人字段泄露风险，也避免渲染层重新解释生产结构。

替代方案是在模板中遍历原始 JSON；这会把验证、路由和隐私判断分散到 HTML 代码中，不采用。

### 3. Coverage 版本选择跟随当前运行上下文，而不是另造全局“最新”

Macro/Market 以所选快照的 source/run/cutoff 选择 coverage；Company 以所选 View 的 run/cutoff/security 选择。首页只汇总每个已配置运行中能够闭合的最新 coverage，并显示对应 cutoff，不把不同运行数字相加成单一“全局覆盖”。

若运行没有 manifest run id，coverage 不进入 Macro/Market 内容投影并显示绑定错误；不可逆 source identity 只用于区分准入目录，不能替代运行绑定。manifest 有 run id 但没有 cutoff 时，须由 manifest 的 coverage/Gate 双 hash 精确引用产物。这样避免“最新 coverage + 历史快照”的时间穿越，同时兼容当前生产 manifest。

替代方案是永远显示目录里时间最新的 coverage；它会污染历史版本阅读，不采用。

### 4. Actual research use 只接受显式证明

页面直接展示 coverage 中的 `actual_research_use_status`。若其为 preparation 阶段未评估，即使 Delivered 大于零也不升级状态。只有同一运行的有效研究产物或未来受支持的 use audit 显式引用 Evidence 时，才能增加独立的“使用证明”展示；该判断不反写 coverage。

这避免把数据链完成误报为研究链完成。仅凭报告 capability 相同但无 Evidence 闭合，不足以证明具体数据集被使用。

### 5. Options 留在 Market 页面并以证券专项分组

`OPTIONS_FLOW` 继续遵循现有三域拓扑，显示在 Market 的“证券专项”区。报告仍保持单一 artifact identity；Company 若提供关联入口，只引用同一身份，不复制正文或创建 Company 版本。`MARKET_STATE` 的共享市场输入与 `OPTIONS_FLOW` 的证券级输入分别校验和呈现。

替代方案是增加第四个 Options 顶级导航或 Agent；当前数据和职责不足以支持独立域，会造成过度设计，不采用。

### 6. 复用现有页面和无脚本组件，内容优先、审计折叠

首页增加三域简明 coverage 摘要；Macro/Market 域页主区先展示指标卡、轻量 SVG 趋势/点阵图与关键明细，coverage/provider/dataset 技术表移动到页面底部并默认折叠。48 条期权合约和 100 条经济日历使用有界表格及默认折叠，不在首页堆叠。窄屏继续使用现有横向可滚动表格。按钮文字改为“重新读取本地资料”，底部继续明确不会联网或调用模型。

不引入客户端状态、图表库或前端构建链。新增视觉元素只复用 badge、card、details 和 table，必要样式保持局部。

### 7. Gate Evidence 只通过 coverage 声明和语义白名单进入展示

在固定候选位置加入 `evidence/gate.json`，仅支持 `common-stock-research-evidence-gate/1.0.0`。读取端验证 `bundle_hash`、run/cutoff、`allowed_evidence_ids` 与 Evidence 必要来源时间字段；manifest 声明 cutoff 时要求三方精确一致，生产 manifest 未声明 cutoff 时仅接受 `gate_hash` 与 `provider_coverage_hash` 同时精确引用对应产物。随后以所选 coverage 的 provider `dataset_observations[].evidence_ids` 为上限，按 dataset 构造白名单 projection：

- `dot_plot`：year、rate、vote_count、median_rate、current_rate。
- `economic_calendar`：title、country、timestamp、importance、actual、consensus、previous。
- `macro_history`：label、period、actual、consensus、previous、unit_type、release time、vintage status。
- `fedwatch_expectations`：meeting_date、target_range、probability。
- `option_market_statistics`：date、Call/Put/total、ratio，并保留 volume 与 open interest 身份。
- `options_snapshot`：contract、expiration、strike、type、bid/ask/last、volume、open interest、IV、已有 Greeks 与时间。
- `options_underlying_context`：IV/HV、percentile/rank、Call/Put volume 和 open interest。
- `vendor_money_flow`：provider category、amount 或 capital in/out、currency、period 和 definition。

任何其他 value key、PRIVATE_KEYS、嵌套对象、绝对路径、source locator、Evidence ID 长列表和完整 Gate 均不进入模板。除 Greeks 明确子字段外，允许字段只接收安全标量；替代方案是让模板遍历 Gate，该方案扩大暴露面并混入语义判断，不采用。

### 8. 旧式快照与新版 Gate 内容并列，而不是互相阻断

官方 Macro snapshot、benchmark snapshot 和 market calculation 仍按原逻辑展示；当它们缺失而新版 Gate 内容可用时，页面只在对应小节显示“官方/基准快照未保存”，不得用全页空状态遮盖 Dot Plot、历史宏观、FedWatch 或期权统计。Gate 内容保持供应商/市场来源标签，不升级为官方观测。

## Risks / Trade-offs

- [Coverage 当前缺少独立 JSON Schema 校验器] → 读取端采用 schema version、canonical hash、必要结构和字段允许列表校验；不合法产物整体隔离，不尝试宽松修复。
- [同一运行包含多个证券，Company projection 可能误收共享或他股数据] → security-scoped 记录必须精确匹配；只有明确无 security 的共享域数据才允许进入 Macro/Market，Company 不借用共享记录冒充公司覆盖。
- [真实 v4 样本位于临时目录，不适合作为仓库 fixture] → 测试使用结构等价、最小且 hash 有效的确定性 fixture；验收另读取真实冻结运行并记录完整 hash，不提交私人或大体积产物。
- [页面信息增加后可读性下降] → 首页只放摘要，域页按能力分组，dataset/provider 细节默认折叠；不把数百条 Evidence ID 写入页面。
- [未来 coverage 增加字段] → 已知 schema 只消费允许字段，新增字段不自动展示；新 schema version 通过局部 registry/adapter 扩展。
- [Gate 体量较大且 value 结构多样] → 扫描仍限固定文件；读取后只保留 coverage 引用且命中 dataset 白名单的紧凑 projection，经济日历与合约长表默认折叠，不引入通用 Evidence 浏览器。
- [共享数据沿用持仓运行的 security_id] → projection 依据 dataset/capability 标记共享宏观或共享市场范围，另行显示“为本次 MRVL 研究准备”，不把该 security_id 当作数据自身范围。

## Migration Plan

1. 增加 coverage registry、校验和领域 projection，保持无 coverage 运行行为不变。
2. 增加 Gate registry、绑定校验和逐 dataset Evidence projection；不改变生产 Gate 或 coverage。
3. 将 projection 注入现有 overview、Macro、Market 和 Company model；不改变既有 URL。
4. 增加内容优先的指标、趋势、分区报告与重新读取文案，将 coverage 技术表默认折叠，并更新产品说明。
5. 运行聚焦确定性测试、OpenSpec 校验及桌面/窄屏视觉检查；使用当前真实冻结运行核对底层值、时间、计数与页面。
6. 如需回退，只移除 Gate/coverage 展示 adapter 与对应渲染；旧快照、报告、Memory 和运行产物无需迁移或回写。
