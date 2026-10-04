# 修复开发测试历史断言与最小开发约定

## Why

开发测试把旧模型、固定根沙箱、历史开发顺序和已归档的活跃目录当作当前前提，造成无关失败。本 Change 只记录实际保留的小修复及两条开发约定，不再承担开发控制面重构或 Codex 配置优化。

## What Changes

- 治理测试改查合法配置结构，不固定旧主模型、单一根沙箱或旧并发值，保留现有角色和产品边界检查。
- Demo 工作流测试不再要求 PRODUCT 的固定阶段顺序，也不读取已归档 Change 的旧活跃任务路径；保留 Demo 不冒充真实产品的检查。
- 根指令明确 Reviewer 按需使用，既有 Change 的明确复核要求保留；开发流程仅增加对应的“按需”措辞。
- 根指令明确外部引入的 OpenSpec 及其他 Skill 只读，不修改，项目规则维护在自有内容中。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `codex-development-environment`：开发测试检查稳定行为与合法结构，而非历史用户配置、开发顺序或活跃目录状态。
- `three-plane-governance`：Reviewer 按需及外部 Skill 只读的最小约定。

## Impact

实际实施仅涉及 `AGENTS.md`、`docs/development/workflow.md`、`tests/test_governance.py`、`tests/test_agent_package_demo_workflow.py` 的本次相关改动；既有只读券商和其他并行修改不纳入本 Change。

项目 Codex 配置、开发环境说明、产品代码、外部 Skill、历史规格和归档均不修改。用户级配置弃用 `type` 字段的单行清理属于独立维护，不纳入本项目提交。原较大流程改造已撤回，本次仅将现有五份规划对齐到保留的小修复，沿用原 Change ID，不新增实施任务或工具。

保留修复后的相关 22 项测试已通过；2026-10-04 用户明确批准本次小修复完成、同步且归档，后续仅按既有委托进行本范围收尾。
