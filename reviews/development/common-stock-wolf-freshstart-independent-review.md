# WOLF fresh-start 定点修复独立复核

日期：2026-09-14
Reviewer：`01a0a05b-5261-7cd0-aa3a-b33ddb4fe309`（`dev-reviewer`）
结论：`REVIEW: PASS`
阻断项：无

## 复核方式

Reviewer 只读检查当前 Change 的规格与任务、源码差异、真实 WOLF 报告、冻结 Gate、执行证明、MCP 事件、Eval 输入和实际 `dev_eval` 产物。没有修改文件，没有重新运行测试或模型，也没有把本结论扩大为完整 Council、Promotion 或人工完成批准。

## 结论

1. `sec-comparison/1.2.0` 明确将能力限定为同指标、单位和期间结构的算术比较；`accounting_basis_status`、每股分母状态和趋势解释状态保持未验证或需 Evidence 复核。
2. Company Agent、`company-research` Skill、派发 Prompt 与 Rubric 对 `fresh-start`、重组、前后继主体、重述及重大处置使用一致边界：缺少额外可比 Evidence 时不得解释为趋势、改善、恶化或现实反证。
3. Evidence Closure 保持精确 ID 集合校验。旧 typo run 的错误 ID 被拒绝；新报告引用的 15 个 ID 独立重算后未知集合为空，没有模糊匹配、截断或静默纠错。
4. 当前 WOLF 报告明确披露新报告主体和跨重组不可比，没有使用旧派生差额解释趋势；经营现金流、收入、亏损、EPS、现金、债务和客户集中度保留数值、期间、单位与来源。OCF 未冒充 FCF。
5. `eval-wolf-freshstart-v4` 直接绑定当前 WOLF invocation、报告 hash 和 Rubric `1.7.0`，由实际 `gpt-5.6-terra` `dev_eval` 子会话生成，结果 `PASS`，不是静态摘要。

## 关键锁

- `financials.py`：`d841fee0ee5cd6a0adf18fcb2553704204bbb817cd157504769d7f1a0b2d4bd6`
- Company Agent：`b7ecd21655e2f7a0d7aa1119ce63f9d94391d677598595586419a77a9d96b949`
- `company-research` Skill：`57302d4433b7ed19f49564e4abbb31d198d5b24b6aaf70a06ac6f3f602ecfddb`
- dispatch implementation：`4959ab46beb2439382b3c159ac5bb584fd554c5b436ec176473a618358a08129`
- Rubric：`7d77d54dc32264c9fdd3bb5905f239f795feda512c5a005a92876985cfcaa98f`
- WOLF 报告 JSON：raw `1ee804570535e4e3f0c17f5d1a05d868d959a2c9ceeaf2cd3e83d300a9355802`
- WOLF 报告 Markdown：`cf110c0f78badf328c5b62b521987e9911847e5492e45771a8a26162e36eebc2`
- Eval result：canonical `157631dff5e02fd2481a8c342fc219f182da18554e78ba7e0db050e69b074c7a`；raw `eaa5bf3d466202720e802d9cd45a41d6abdf6280eac066fc146ce18f1afaa992`
- 被拒绝 typo 输出：`8fab38e8c0861e6420f46427dd68d78d3285151b5fab672ef10b2f26f31f8f3b`

## 非阻断观察

- 冻结 Gate 继续保留旧 `sec-comparison/1.1.0` 派生事实；本轮没有改写历史 Evidence，新报告也没有使用其 delta 解释趋势。真实运行不证明重新产出了 1.2.0 派生事实，1.2.0 元数据由聚焦确定性测试证明。
- WOLF 的现金缓冲反证表述略绕，但实际 `counter_claim_refs`、同日事实和约束机制正确，不影响验收。
- Reviewer 按约定未复跑主线程的 `101/101` 与 OpenSpec strict；它直接核验了源码和运行产物。主线程执行证据与独立只读复核分开记录。
- 工作树存在本 Change 之前的较大差异，因此复核依赖当前文件完整 hash 和 run 绑定，而不声称可仅由 Git 隔离所有历史改动。

本 PASS 可关闭 Task 9.4；Task 5.4 仍等待用户明确人工完成批准。
