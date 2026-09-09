# Promotion Gate 报告

- Gate ID：`rreh-promotion-hardening-final-20260908`
- 结果：`PASS`

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
- version_completeness: `PASS`
- ablation_comparability: `PASS`

## Reasons

- 无

## 软指标与限制

- 语义基线比较：`WITHIN_TOLERANCE`，delta=0.0
- 成本/延迟比较：`FAIL_COST_COMPARISON`
- Ablation：`NO_MEASURABLE_GAIN`；增益是否强制：`False`
