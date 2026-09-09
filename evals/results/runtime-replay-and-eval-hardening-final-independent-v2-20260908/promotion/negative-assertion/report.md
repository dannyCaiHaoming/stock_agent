# Promotion Gate 报告

- Gate ID：`rrh-final-independent-v2-negative-assertion-20260908`
- 结果：`FAIL`

## 硬门禁

- deterministic_tests: `FAIL`
- semantic_calibration: `PASS`
- runtime_regression: `FAIL`
- execution_replay: `PASS`
- evidence_closure: `PASS`
- pit_leakage: `PASS`
- risk_bypass: `PASS`
- schema_success: `PASS`
- mandatory_no_trade: `FAIL`
- trace_completeness: `PASS`
- version_completeness: `FAIL`
- ablation_comparability: `PASS`

## Reasons

- `PROMOTION_HARD_GATE_FAILED:deterministic_tests`
- `PROMOTION_HARD_GATE_FAILED:mandatory_no_trade`
- `PROMOTION_HARD_GATE_FAILED:runtime_regression`
- `PROMOTION_HARD_GATE_FAILED:version_completeness`

## 软指标与限制

- 语义基线比较：`NOT_COMPARABLE`，delta=None
- 成本/延迟比较：`FAIL_COST_COMPARISON`
- Ablation：`NO_MEASURABLE_GAIN`；增益是否强制：`False`
