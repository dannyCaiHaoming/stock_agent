# Portfolio Council 研究建议

- Run ID: `harden-conflict-01`
- 终态: `SAFE_NO_TRADE`
- 动作: `NO_TRADE`
- 仅供建议: `true`
- Risk 状态: `APPROVED`

## Thesis

已验证报告确认的单点经营利润率和价格不足以在核心收入口径冲突未解时建立可审计的商业质量或估值 Thesis。

## Counter Thesis

两项同一期间、同一语义字段的收入证据给出不兼容值，且缺少解释差异、盈利质量与资本结构的证据；任何方向性组合判断均不可验证。

## Evidence IDs

- `ev-conflict-margin`
- `ev-conflict-price`
- `ev-conflict-revenue-a`
- `ev-conflict-revenue-b`

## 失效与重评条件

- 若截至决策截止日的权威披露说明两项收入采用不同口径，或更正、撤回其中一项，则收入冲突对本结论的影响必须重新评估。
- 若补充一致口径的连续财务、现金流和资本结构证据，当前证据不足结论必须重新评估。
- 获得可核验的权威收入对账、更正或口径说明后重新评估。
- 获得统一口径的连续财务、现金流、资本结构及估值输入后重新评估。

## NO_TRADE

- 原因码: `EVIDENCE_CONFLICT`
- 说明: 核心收入证据存在未解决的同期间冲突，且缺少可审计的盈利质量、现金流、资本结构和估值基础；因此不发布方向性组合建议。
