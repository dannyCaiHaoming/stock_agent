## ADDED Requirements

### Requirement: Council 终态加固必须通过真实 fixture 稳定性门禁
候选版本 MUST 通过 Codex-native 产品入口分别实际运行正常研究、未来或过期证据、Evidence 冲突和 Risk veto 四类版本化 fixture，并对每次运行执行终态检查和实际 Eval。Evidence 冲突 fixture MUST 在没有修改候选产品文件的情况下连续运行至少三次；三次均 MUST 生成与合法 `COMPLETED` 或 `SAFE_NO_TRADE` 终态一致的 `decision.json`、`report.md`、`decision_trace.json` 和 Eval 结果，全部 Evidence References 必须闭合，且任何已形成 CIO 草案的运行不得绕过 deterministic Risk Engine。

#### Scenario: 重新执行四类真实 fixture
- **WHEN** `harden-council-terminal-contracts` 候选进入 Release Gate
- **THEN** 四类 fixture 均通过真实 Codex-native 入口运行并保存各自命令、显式模型、唯一 `run_id`、终态产物、Trace 和实际 Eval 判定；未来或过期证据场景仍可在专业 Agent 前安全终止

#### Scenario: Evidence 冲突连续三次形成合法终态
- **WHEN** 操作者以相同候选版本和三个全新输出目录连续运行 Evidence 冲突 fixture
- **THEN** 三次均完成双 Agent 独立研究、CIO 冲突综合、Risk Engine 检查、Evidence Closure、三项发布产物和实际 Eval，且不得依赖固定 Thesis、Action 或 Confidence

#### Scenario: 任一次冲突运行产生非法 NO_TRADE
- **WHEN** 三次 Evidence 冲突运行中的任一次生成 `maximum_notional: 0`、非空 `target_weight_range`、悬空 Evidence 或缺失 Risk lineage
- **THEN** 该次 Release Gate 返回非零，连续稳定性验收整体失败，不得以另外两次成功抵消
