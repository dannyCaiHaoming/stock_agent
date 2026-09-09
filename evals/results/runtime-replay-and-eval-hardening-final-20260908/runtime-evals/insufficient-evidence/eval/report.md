# Runtime Eval 报告

- Eval ID：`rrh-final-eval-insufficient-evidence-20260908`
- Run ID：`rrh-final-insufficient-evidence-20260908`
- 终态：`SAFE_NO_TRADE`
- 结果：`PASS`

## 硬门禁

- artifact_replay: `PASS`
- evidence_closure: `PASS`
- pit_leakage: `PASS`
- risk_bypass: `PASS`
- schema_and_artifacts: `PASS`
- terminal_contract: `PASS`
- trace_completeness: `PASS`

## 语义 Rubric

- analyst_thesis_grounding: `PASS` / grade=3 — The analyst labels the supported close-price statement as FACT and cites ev-insufficient-price, while explicitly withholding company, fundamental, and valuation conclusions because the required evidence is absent.
- cio_conflict_handling: `PASS` / grade=3 — CIO records the specialists consensus, the absence of artifact conflicts, material unresolved questions, and their effect on NO_TRADE; decision.json consistently records APPROVED risk status and SAFE_NO_TRADE.
- confidence_calibration: `PASS` / grade=3 — Analyst, skeptic, and CIO confidence rationales limit confidence to the sourced price fact or the insufficiency conclusion and remain low in the presence of the documented evidence gaps and uncertainty.
- no_trade_reasoning: `PASS` / grade=3 — The sole allowed close-price fact is explicitly insufficient for a security-level thesis; NO_TRADE and the three point-in-time reevaluation conditions match the stated gaps and SAFE_NO_TRADE.
- skeptic_counter_evidence: `PASS` / grade=3 — The independent-first-pass skeptic gives a specific, falsifiable insufficiency challenge grounded in the price fact, identifies missing evidence categories, and states what permitted point-in-time evidence would resolve it.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`1c73fb253955cc87e8c382a59b2eeb2e4e3f1c8239a5bac1de9019d8319d9426`
- Execution proof hash：`c5943028d71340b8cdeac8847a39292da9f8334fd02b450a874ddc0752ea82db`

## Reason Codes

- 无
