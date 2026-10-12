## ADDED Requirements

### Requirement: 历史单股建议必须由独立显式阶段消费同源正反研究
系统 SHALL 在研究资料历史准入和 `verify-research-evidence-to-cio-chain` 的研究链路验收完成后，通过独立的历史单股建议阶段消费同一证券、同一 `decision_cutoff` 的合格正向与独立 Skeptic 报告，由现有主线程 CIO 形成建议。该阶段 MUST 验证报告身份/hash、Evidence Gate、实际执行终态、关键引用和来源模式；正向或适用反证未就绪、材料不可重建或时点不符时 MUST 在动作前停止。原 `PREDECISION_CIO_SYNTHESIS` 的 MRVL `RESEARCH_SYNTHESIS` 入口与 `PORTFOLIO_ADVICE` 拒绝行为保持原样。

#### Scenario: 合格历史单股样本
- **WHEN** 指定证券和截止点有同源、已验证的正向与反证交接包
- **THEN** 历史阶段在独立运行中给 CIO 只读冻结资料与假设持仓状态，记录具体报告消费和建议来源，不重新解释旧运行成当前账户意见

#### Scenario: 历史资料包含未来事实
- **WHEN** 任一必需研究报告或 Gate 混入截止点后才可知资料
- **THEN** 在 CIO 前拒绝历史建议，保留失败与来源断点，不生成投资性 `NO_TRADE`

#### Scenario: 调用旧 MRVL 研究级入口请求动作
- **WHEN** 调用方使用原 `PREDECISION_CIO_SYNTHESIS` 请求 `PORTFOLIO_ADVICE`
- **THEN** 仍按原契约在模型前拒绝，不隐式路由到历史建议阶段
