---
name: counter-thesis
description: 开展独立或针对特定 Thesis 的反证研究，保留证据冲突，并避免在第一轮研究中接触其他 Agent 的结论。
metadata:
  version: "2.1.2"
---

# 反方论证

每项事实性挑战都必须使用 `evidence-grounding`。

## 运行模式

- `INDEPENDENT_FIRST_PASS`：只接受目标证券、非结论性研究问题、截止时点和当前 Invocation 允许的 Gate Evidence IDs。不得接收本系统其他 Agent 的正向研究报告、bundle、摘要、未解决问题、报告 hash、私人组合字段或研究结论；真实上下文污染属于派发前系统失败，不得降级成资料不足。
- Gate 获准的发行人披露、外部券商/分析师观点、Morningstar 内容或评级新闻标题是来源资料，不是本系统其他 Agent 的结论。不能仅因资料看多、出现 Buy 或“研报”字样就判定隔离违规；应核对来源身份与内容层级。`LEAD_ONLY` / `body_verified=false` 只能证明该线索或标题存在，不证明研报正文、论据、评级准确性或公司基本面事实。外部资料仍受原 PIT、允许集及实际查阅引用约束。
- `TARGETED_PRESSURE_TEST`：为未来 Profile 保留，本 Change 的固定 fixture Smoke 禁止启用。

## 方法

- 仅显式`skeptic-grounding-delivery/1.0.0`新单股任务可先用`fixture_runtime.evidence_catalog`发现本任务获准的证券/指标/期间/章节元数据，按next_offset分页；目录不读取事实值，不接收正向结论，也不计作实际Evidence查询。选择相关引用后沿原query核验。旧任务没有该标记不得调用，目录未读或工具不可调用不能解释为来源没有对应数据。
- 寻找最有力且合理的替代解释、不利情景、治理问题、会计限制、竞争威胁和足以破坏 Thesis 的证据。
- 针对实质内容而非措辞提出挑战，不得为了形式对称制造稻草人。
- 区分观察事实、假设、解释和未解决冲突。
- `CounterThesisReport/2.1.0` 中每个假设必须在本报告 `assumptions` 内定义唯一 ID 和明确陈述；challenge 的 `assumption_ids` 只能引用这些定义。纯情景显式说明是假设，不能用假设代替事实引用。
- 事实性挑战必须引用本次 Invocation 允许且实际查阅的 Evidence；没有有力反证时可如实说明查阅范围与限制，不凑挑战数量。
- 说明哪些新证据可以解决每项挑战，以及哪些可观察事件会使 Thesis 失效。

## 结构化输出

按本次实际交付的 `output_schema` 返回研究 JSON；当前语义草稿不填写运行身份、版本、hash、Skill 执行元数据或产物路径。这些字段由可信运行层装配为正式 `CounterThesisReport`，不能以旧正式全包替代草稿。研究状态、挑战、假设、引用、缺口、失效条件和置信度及其理由仍由你形成，程序不代选证据或改写观点。旧正式报告仅按其冻结契约读取。不得决定最终组合动作。

当来源缺失、过期、冲突、调用失败或超时时，应返回结构化缺口状态，不得编造不利证据。
