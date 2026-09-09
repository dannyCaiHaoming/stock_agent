# Promotion Gate 报告

- Gate ID：`rreh-promotion-candidate-20260907`
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
- ablation_comparability: `FAIL`

## Reasons

- `PROMOTION_HARD_GATE_FAILED:ablation_comparability`
- `PROMOTION_HARD_GATE_FAILED:version_completeness`

## 软指标与限制

- 语义基线比较：`NOT_COMPARABLE`，delta=None
- 成本/延迟比较：`FAIL_COST_COMPARISON`
- Ablation：`NOT_COMPARABLE`；增益是否强制：`False`
