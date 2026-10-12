## Context

见 proposal.md。当前 `predecision_cio_stage` 在准备入口、请求 Schema 和宿主脚本只接受 MRVL、`SOURCE_CUTOFF`、`RESEARCH_SYNTHESIS`；研究级 Risk 为 `NOT_RUN`，旧建议 finalizer 已拒绝。现有普通 PIT Gate 会排除 `retrieved_at > decision_cutoff` 的事实；SEC 原始披露有可定位 accession/公开时间，但 Yahoo 估值与不少 Moomoo/Macro 字段仅有当前快照或未知历史 vintage。产品现有 Council 动作 Schema 与 Risk 绑定完整账户，不适合直接承担模拟单股意见。

## Goals / Non-Goals

**Goals:**
- 让一个明确历史时点的资料、正反研究、条件化建议和事后结果各自拥有不可混用的身份与时间边界。
- 复用专业 Agent、Skills、Evidence Closure、宿主 launcher 和已有 Risk 边界；保留原 MRVL 非动作研究级入口。
- 在没有真实账户时对假设空仓/持仓给出可复盘的单股方向，并如实表达历史版本与 LLM 记忆限制。

**Non-Goals:**
- 不运行券商写接口、不生成可执行订单，不从假设持仓推断用户实际可承受仓位。
- 不建设策略优化器、参数搜索、自动 Prompt 学习、大规模模拟成交引擎或保证无前瞻偏差的历史绩效系统。

## Decisions

1. **另设显式历史阶段，不解除旧建议入口的拒绝。** 使用单股历史请求（证券身份、UTC 决策时点、期限、基准、`FLAT`/`HELD` 假设）驱动现有研究角色的受限阶段适配。研究上下文标记 `HYPOTHETICAL`，不得伪装已确认的真实 `PortfolioHandoff`，也不创建第二编排器。旧 `PREDECISION_CIO_SYNTHESIS` 对 `PORTFOLIO_ADVICE` 的拒绝保持不变。替代方案“给旧 MRVL 研究报告加 action 字段”会破坏已验证契约。
2. **历史 Gate 是明确的新模式。** `CAPTURED_AT_TIME` 只用真正事前已封存的原始版本；`VERIFIED_RECONSTRUCTION` 允许事后检索原始历史披露，前提是同一内容版本、公开时间、来源定位/hash 可核验且 `as_of <= cutoff`。两者都保留真实 `retrieved_at`，并在 Gate 标记模式、依据和受限字段。SEC 原始 filing 的 accession/原文可作候选；SEC 当前聚合修订值、Yahoo/Moomoo 当前估值/共识、无版本的宏观实际值不得凭旧观察期进入。行情需核对当时市场时段、原始价格与后来的公司行动调整，无法证明历史口径则仅作事后评价或记 gap。替代方案“把 retrieved_at 改成旧日期”会伪造血缘。
3. **建议和事后结果物理隔离。** CIO 只能读取已通过历史 Gate 的正反研究包；只读封存 `single-stock-advice.json`、报告与 Trace 后，确定性评价才读取未来行情和基准。建议保留 `BUY/HOLD/ADD/TRIM/EXIT/NO_TRADE` 词汇，但约束 `FLAT` 与 `HELD` 的合法动作；不写目标权重、金额或股数，也不生成账户级 `decision.json`。如果需要真实账户金额，转入以后有账户快照和硬风控的明确 Change；本阶段直接拒绝。替代方案“复用完整组合 Decision Schema 并填虚构账户”会制造假 Risk 通过。
4. **小样本先验评价。** 实施前固定 MRVL 的少量事件前后截止点、一只第二证券、评价期限、基准和模型/Skill/Schema 版本。先证明至少一个历史样本真正可重建并运行，再独立展示后续表现与无法评价项；所有样本都保留，包括失败和 `NO_TRADE`。相同样本不能同时用于改 Prompt 与宣称提升；必要的新候选须另取保留样本。LLM 参数知识无法完全冻结到过去，界面和 Trace 明示限制。

## Risks / Trade-offs

- [历史数据系列无原版本或经过事后修订] → dataset 级排除，关键资料不足时停止建议；不得用今天的快照填空。
- [部分历史时点没有足够 Macro/Market 资料] → 先输出覆盖矩阵与 `NOT_EVALUABLE`/不可建议原因，改变选定时点需留痕，不能静默挑赢的样本。
- [假设动作被误解为当前账户建议] → 独立 Schema/文件名、显著时间与假设标签、无权重金额、Risk 明示未运行。
- [LLM 可能记得未来事件] → 严格隔离输入仍不能消除模型预训练知识；结果只称历史回放与纸面评价，不作无偏实盘收益声明。
- [跨多阶段新模式影响现有入口] → 保留原锁与历史读取，先做模型前时点/权限测试，再做有界真实宿主验收；失败不改默认入口。

## Migration Plan

依赖 `verify-research-evidence-to-cio-chain` 验收后启用独立历史入口；旧研究和账户级 fixture 决策保持原版本。先用零模型样本验证历史准入及未来结果隔离，再按预先固定的真实样本与预算执行，独立复核建议和结果。若历史来源不足，保持入口受限并输出可核查缺口，不降级到当前快照回填。
