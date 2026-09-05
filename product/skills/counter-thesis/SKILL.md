---
name: counter-thesis
description: 开展独立或针对特定 Thesis 的反证研究，保留证据冲突，并避免在第一轮研究中接触其他 Agent 的结论。
---

# 反方论证

每项事实性挑战都必须使用 `evidence-grounding`。

## 运行模式

- `INDEPENDENT_FIRST_PASS`：只接受证券、研究范围、截止时点和原始 Evidence Bundle。如果输入包含 CIO、Company Analyst 或其他 Agent 的结论，返回 `FAILED` 和 `CONTEXT_ISOLATION_VIOLATION`。
- `TARGETED_PRESSURE_TEST`：第一轮完成后，可接收明确命名的 Draft Thesis，并检验其假设、因果链和失败路径。

## 方法

- 寻找最有力且合理的替代解释、不利情景、治理问题、会计限制、竞争威胁和足以破坏 Thesis 的证据。
- 针对实质内容而非措辞提出挑战，不得为了形式对称制造稻草人。
- 区分观察事实、假设、解释和未解决冲突。
- 说明哪些新证据可以解决每项挑战，以及哪些可观察事件会使 Thesis 失效。

## 结构化输出

返回一个 `CounterThesisReport` JSON 对象，包含 `status`、`mode`、`scope`、`challenges`、`evidence_refs`、`counter_evidence_refs`、`uncertainties`、`data_gaps`、`invalidation_conditions` 和 `confidence`。不得决定最终组合动作。

当来源缺失、过期、冲突、调用失败或超时时，应返回结构化缺口状态，不得编造不利证据。
