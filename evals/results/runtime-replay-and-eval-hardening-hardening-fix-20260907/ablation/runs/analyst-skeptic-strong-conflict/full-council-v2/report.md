# Portfolio Council 研究建议

- Run ID: `rreh-hardening-ablation-conflict-full-council-v2-20260908`
- 终态: `SAFE_NO_TRADE`
- 动作: `NO_TRADE`
- 仅供建议: `true`
- Risk 状态: `APPROVED`

## Thesis

Gate 授权证据确认存在同一证券、同一as_of的收入TTM冲突；在收入基线未仲裁前，18%经营利润率和USD 100价格观测不足以支持可验证的经营质量、利润额或估值Thesis。

## Counter Thesis

两份收入观测可能反映不同合并范围、期间边界、会计分类、重述或数据错误；但现有证据无法判定哪一种解释成立，也无法确认利润率与任一收入分母可比。

## Evidence IDs

- `ev-conflict-margin`
- `ev-conflict-price`
- `ev-conflict-revenue-a`
- `ev-conflict-revenue-b`

## 失效与重评条件

- 可追溯的权威披露确认两项收入的可比口径并将其调节为唯一TTM收入值，或明确排除/更正其中一项。
- 同口径财务报表确认经营利润率的分子与经调节收入分母一致。
- 获得两项收入来源的原始定义、合并范围、期间边界和单位说明，并由权威披露或来源更正将其调节为唯一TTM收入值。
- 获得同一报告口径的营业利润金额、收入分母及计算定义，以核验18%经营利润率。
- 获得截至决策截止日的股本、资本结构和一致口径财务历史后，重新评估基本面与估值解释。

## NO_TRADE

- 原因码: `EVIDENCE_CONFLICT`
- 说明: 同一as_of的收入TTM事实冲突未解决，且缺少可仲裁来源、口径调节和与收入一致的利润数据；不形成行动意图。
