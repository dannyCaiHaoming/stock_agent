---
name: counter-thesis
description: 开展独立或针对特定 Thesis 的反证研究，保留证据冲突，并避免在第一轮研究中接触其他 Agent 的结论。
metadata:
  version: "2.1.0"
---

# 反方论证

每项事实性挑战都必须使用 `evidence-grounding`。

## 运行模式

- `INDEPENDENT_FIRST_PASS`：只接受目标证券、非结论性研究问题、截止时点和当前 Invocation 允许的 Gate Evidence IDs。不得接收正向报告、bundle、摘要、未解决问题、报告 hash、私人组合字段或其他 Agent 结论；上下文污染属于派发前系统失败，不得降级成资料不足。
- `TARGETED_PRESSURE_TEST`：为未来 Profile 保留，本 Change 的固定 fixture Smoke 禁止启用。

## 方法

- 寻找最有力且合理的替代解释、不利情景、治理问题、会计限制、竞争威胁和足以破坏 Thesis 的证据。
- 针对实质内容而非措辞提出挑战，不得为了形式对称制造稻草人。
- 区分观察事实、假设、解释和未解决冲突。
- `CounterThesisReport/2.1.0` 中每个假设必须在本报告 `assumptions` 内定义唯一 ID 和明确陈述；challenge 的 `assumption_ids` 只能引用这些定义。纯情景显式说明是假设，不能用假设代替事实引用。
- 事实性挑战必须引用本次 Invocation 允许且实际查阅的 Evidence；没有有力反证时可如实说明查阅范围与限制，不凑挑战数量。
- 说明哪些新证据可以解决每项挑战，以及哪些可观察事件会使 Thesis 失效。

## 结构化输出

新阶段返回 `CounterThesisReport/2.1.0` JSON 对象，包含 `status`、`mode`、`scope`、`challenges`、`assumptions`、`evidence_refs`、`counter_evidence_refs`、`uncertainties`、`data_gaps`、`invalidation_conditions` 和 `confidence`。旧 2.0.0 仅按其冻结契约读取。不得决定最终组合动作。

当来源缺失、过期、冲突、调用失败或超时时，应返回结构化缺口状态，不得编造不利证据。
