## 1. 实际保留的小修复

- [x] 1.1 保留治理和 Demo 工作流测试的历史断言修复；差异走查确认不再固定旧模型/根沙箱、开发顺序或旧活跃目录，相关角色与 Demo 边界检查仍在。
- [x] 1.2 保留根指令的 Reviewer 按需/外部 Skill 只读约定，以及流程文档一处按需措辞；确认未扩写开发说明、修改配置或外部 Skill。

## 2. 检查与批准

- [x] 2.1 复用修复保留后已通过的三个相关测试模块结果，并校验当前精简 Change 的 OpenSpec strict、链接及格式；区分代码检查与本轮规划检查，不新增产品运行或工程任务。
- [x] 2.2 提交仅覆盖上述保留改动的完成摘要，取得一次明确人工完成/同步归档批准；未批准不同步主规格、不归档或发布，批准后沿用既有限定提交推送委托。

## 已有检查结果

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_governance tests.test_development_workflow tests.test_agent_package_demo_workflow -v
```

回退流程扩写后实际重验：22 项全部通过，0 失败、错误或跳过。归档收尾时按同一命令再次重验，仍为 22 项通过；两份主规格与当前 delta 完全匹配，原标题/Purpose/无关要求保留，24 份主规格 strict 校验全部通过。

当前精简规划的 OpenSpec strict、链接及格式检查通过。2026-10-04 用户明确批准完成、同步且归档；四项任务完成，主规格同步、归档及限定提交推送按既有委托连续收尾，不代表 Promotion PASS。

`docs/development/environment.md` 与外部 Skill 无剩余差异。根配置保留用户已有修改；只读券商等并行改动、用户级配置单行修复均不归属本 Change。原较大流程改造不恢复，也不声明模型行为、效率、真实产品验收或 Promotion PASS。
