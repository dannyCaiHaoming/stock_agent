## Context

原流程改造已撤回。用户要求把同一个 Change 改为实际保留的小修复，不删除目录、不重新扩建流程。动机和范围见 [proposal.md](proposal.md)。

## Goals / Non-Goals

**Goals:** 让开发检查不因过期配置、旧阶段顺序或已归档路径而失败，并记录 Reviewer 按需与第三方 Skill 只读的简短约定。

**Non-Goals:** 不改 Codex 配置、产品、外部 Skill、开发环境说明、历史原件或其他 Change；不新增工具、Agent、测试模块、证据平台或效率承诺。用户级配置单行维护不在本 Change 内。

## Decisions

- `tests/test_governance.py` 只检查模型字符串、受支持沙箱枚举、网络布尔值和正整数并发，不固定旧用户选择；角色注册及其他现有边界检查保留。
- `tests/test_agent_package_demo_workflow.py` 删除 PRODUCT 固定顺序前提和旧活跃任务路径读取，保留 Demo 边界及长期规则不固定旧 Change 状态的检查。
- `AGENTS.md` 只保留 Reviewer 按需、已有明确复核要求不变、外部 Skill 只读的短约定；`docs/development/workflow.md` 仅对齐“按需独立评审”措辞。
- 用现有三个相关测试模块验证，22 项已经通过。配置文件不改，外部 Skill 无差异；静态检查不冒称真实模型行为或开发效率已验证。

## Risks / Trade-offs

- [共享文件存在先前修改] → 保留只读券商等已有改动，只认领本次相关部分。
- [旧 Change 仍有明确验收要求] → 按需 Reviewer 不自动取消这些要求。

## Migration Plan

本轮仅把五份规划对齐到已保留的修复，不新增实施。原 Change ID 沿用，原大范围改造不恢复；相关测试结果复用并注明范围，规划校验单独执行。取得最终完成批准后才同步主规格、归档和限定提交推送，未批准不发布。
