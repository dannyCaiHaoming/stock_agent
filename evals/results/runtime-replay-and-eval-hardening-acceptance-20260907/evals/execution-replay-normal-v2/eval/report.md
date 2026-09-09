# Runtime Eval 报告

- Eval ID：`rreh-eval-execution-replay-normal-v2-20260907`
- Run ID：`rreh-execution-replay-normal-20260907`
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

- analyst_thesis_grounding: `PASS` / grade=3 — Claims c1-c4 are labeled FACT and cite their supporting records. Claim c5 is labeled INTERPRETATION, declares assumption a1, and limits the inference rather than treating the cited margin, debt/revenue ratio, or plan update as a valuation conclusion.
- cio_conflict_handling: `PASS` / grade=3 — CIO records the specialist consensus, reports no conflicts consistently with the gate conflict set, lists unresolved questions, and makes the evidence gaps the stated basis for NO_TRADE and reevaluation.
- confidence_calibration: `PASS` / grade=3 — The analyst, skeptic, and CIO all state bounded confidence rationales tied to the narrow frozen evidence and identified uncertainties; CIO confidence remains low and does not convert limited facts into a stronger conclusion.
- no_trade_reasoning: `PASS` / grade=3 — CIO NO_TRADE is tied to the limited static evidence set and explicitly identifies missing cash-flow, debt-structure, demand, capacity-execution, and valuation evidence; its reevaluation conditions request those verifiable inputs.
- skeptic_counter_evidence: `PASS` / grade=3 — The independent-first-pass skeptic gives three specific, falsifiable challenges—margin durability, capacity execution, and valuation downside—links each to frozen evidence, and states concrete evidence needed to weaken each challenge.

## Grader Lineage

- Agent：`dev_eval`
- Model：`gpt-5.6-terra`
- Prompt hash：`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`
- Rubric hash：`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`
- Input hash：`f6d6853f209de4ff530da47daf6bb455bbcf9f7406f5f35015e932f32e52e195`
- Execution proof hash：`03dd606cc6e1a36f2e20a20d7e0749033d461fa38ef3606b540dda207be49337`

## Reason Codes

- 无
