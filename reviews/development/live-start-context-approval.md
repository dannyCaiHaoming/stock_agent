# Live 启动上下文交付调整批准

- approval_id：`live-start-context-approval-2026-09-10`
- Change：`us-equity-live-advisory-slice`
- 用户明确答复：批准。
- 批准对象：使用真实 SubagentStart Hook 注入并验证冻结 Input/Invocation/Prompt/Schema，复用 MCP、原始输出回执和终态校验，不再要求所有 live 派发必须产生 PreToolUse ALLOW。
- 接受的限制：不能保证子 Agent 启动前阻止错误；Hook/原生权限不构成全进程强制隔离，ISOLATION 保持 UNVERIFIED。
- 不变约束：绑定缺失/漂移/超限仍 fail-closed；保留适用的 PreToolUse、独立 Skeptic、Schema/Evidence Closure、PIT、Risk、只读数据与合法终态；不新增模型后端或安全豁免。
- 实施及验证：Design 2.1 与原定受影响接缝、单股→三股及独立复核；不扩大模型重试次数。
- 不包含：Task 5.5 完成批准、归档、Git 提交/推送、Promotion PASS 或生产指针修改。
- 批准前证据：`live-research-materials-fix.json`，SHA-256 `8cdc048e92fca8101d01bb5349e04c64a4403011404150d78d140fce7affc7e1`。该文件保留原先待批准的历史事实，不回写。
