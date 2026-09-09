# Promotion Gate 报告

- Gate ID：`rrh-final-promotion-current-baseline-gap-20260908`
- 结果：`FAIL`

## 硬门禁

- deterministic_tests: `PASS`
- semantic_calibration: `PASS`
- runtime_regression: `PASS`
- execution_replay: `PASS`
- evidence_closure: `PASS`
- pit_leakage: `PASS`
- risk_bypass: `PASS`
- schema_success: `PASS`
- mandatory_no_trade: `PASS`
- trace_completeness: `PASS`
- version_completeness: `FAIL`
- ablation_comparability: `PASS`

## Reasons

- `PROMOTION_HARD_GATE_FAILED:version_completeness`

## 软指标与限制

- 语义基线比较：`NOT_COMPARABLE`，delta=None
- 成本/延迟比较：`FAIL_COST_COMPARISON`
- Ablation：`NO_MEASURABLE_GAIN`；增益是否强制：`False`
