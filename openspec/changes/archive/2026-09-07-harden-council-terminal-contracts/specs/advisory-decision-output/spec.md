## ADDED Requirements

### Requirement: Council 决策条件必须来自单一规范契约
系统 MUST 维护一个版本化、机器可读的 canonical decision contract，作为 CIO 动作条件、JSON Schema 条件分支、运行时确定性校验和 CIO 可见示例的唯一规范来源。`action == NO_TRADE` 时，`target_weight_range` 与 `maximum_notional` MUST 均为 JSON `null`；数值 `0`、空数组或任何其他非 `null` 值 MUST 被拒绝。JSON Schema、运行时 Validator 与 CIO Prompt 的派生产物 MUST 通过一致性校验，任何契约缺失、版本不一致或派生漂移 MUST fail closed，且不得放宽现有 Evidence Closure、Risk 或仅供建议边界。

#### Scenario: 合法 NO_TRADE 通过条件校验
- **WHEN** CIO 草案的 `action` 为 `NO_TRADE`，且 `target_weight_range` 与 `maximum_notional` 均为 JSON `null`
- **THEN** JSON Schema 与运行时 Validator 均接受这两个执行字段，并继续校验 NO_TRADE 原因、说明、重评条件、Evidence Closure 和其余既有约束

#### Scenario: 数值零不得冒充 null
- **WHEN** CIO 草案的 `action` 为 `NO_TRADE`，且 `maximum_notional` 为数值 `0`
- **THEN** JSON Schema 与运行时 Validator 均确定性拒绝该草案，运行进入 `FAILED_VALIDATION`，且不得进入 Risk Engine 或发布建议

#### Scenario: NO_TRADE 携带目标仓位范围
- **WHEN** CIO 草案的 `action` 为 `NO_TRADE`，且 `target_weight_range` 为任何非 `null` 值
- **THEN** JSON Schema 与运行时 Validator 均确定性拒绝该草案，且错误明确归因于动作条件契约

#### Scenario: 正常建议遵守对应动作契约
- **WHEN** CIO 草案使用 `BUY`、`ADD`、`HOLD`、`TRIM` 或 `EXIT`
- **THEN** 系统按 canonical decision contract 校验该动作适用的执行字段、理由字段与禁止字段，而不套用 NO_TRADE 的空值规则

#### Scenario: CIO 获得一致的合法与非法示例
- **WHEN** 系统构建 CIO Invocation 的可见指令
- **THEN** 指令包含从同一 canonical decision contract 派生的合法 `NO_TRADE`、`maximum_notional: 0` 非法及非空 `target_weight_range` 非法示例，并标明 `0` 不等于 JSON `null`

#### Scenario: 派生产物与规范契约漂移
- **WHEN** 已保存的 CIO JSON Schema、Prompt 片段或运行时规则与 canonical decision contract 的版本、哈希或确定性派生结果不一致
- **THEN** 测试与运行前完整性校验失败，不允许该候选进入真实 Council 运行
