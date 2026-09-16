# 单股格式修复接缝与一次真实重试

## 范围与修改

2026-09-10，用户批准定点修复格式修复指令并重试一次真实单股。未新增 Change、Agent、数据来源或重试框架，未运行全量 Regression/Gate，也未修改事实、Evidence Closure、格式修复 Validator、Risk 或代理设置。

- `product/runtime/invocation.py`：要求逐项依照本次完整输出 Schema 的顶层 properties 与嵌套位置输出，禁止混用其他角色字段；不另写一套 Schema 字段清单。
- `product/runtime/smoke_prompt.py`：一次修复消息必须附原报告、错误、Schema；明确只修指定结构，所有其他字符串、数值、来源、时间及 uncertainties/data_gaps 原样保留。针对仅多出顶层 evidence_refs 的错误，明确只删除该多余字段，父线程不得代改。
- 原 `format_repair.py` 与 `validation.py` 保持不变；没有静默截断 ID 或修改历史失败报告。
- 本地插件通过现有 cachebuster/安装流程更新到 `0.3.0+codex.20260910115541`；安装缓存的 invocation/smoke_prompt/format_repair 三个文件与仓库 SHA-256 相同。没有变更生产版本指针。

## 确定性验证

实际命令、完整测试输出见 [测试记录](live-format-repair-tests.json)，源码完整 hash 见 [运行证据](live-format-repair-smoke-result.json)。

| 验证 | 结果 | 证明范围 |
| --- | --- | --- |
| Invocation、Run Package、live profile 29 项测试 | PASS | 合成接缝，不是真实研究 |
| 仅移除 Analyst 多余顶层 evidence_refs，陈述及 uncertainties 保持不变 | PASS | 一次修复后可进入 CIO 准备 |
| 删除陈述中的来源/时间，或缩短 Thesis | 确定性拒绝（测试 PASS） | `FORMAT_REPAIR_ADDED_FACT_CONTENT` 仍生效 |
| Prompt 字面保留约束、各角色 Schema 顶层边界 | PASS | 已生成指令包含约束，不保证 LLM 必然遵守 |
| 插件结构校验 | PASS | 实际执行 `validate_plugin.py product` |
| `openspec validate us-equity-live-advisory-slice --strict` | PASS | 当前 Change 规划合法性 |
| `git diff --check` | PASS | 空白/补丁格式检查，不是独立审阅 |

测试日志末尾的 `NATIVE_EXECUTION_PROOF_FAILED` 是负向单元测试的预期标准输出；该测试本身通过，不能当作真实运行结果。

## 一次真实重试：FAIL，未重复启动

- 根目录：`/private/tmp/stock-agent-format-repair.dKhRRb`
- run_id：`live-4b6a421c-d4d0-4b24-af8a-eaf34513a1cd`
- 模型：`gpt-5.6-terra`；耗时 392.006 秒。
- 源码快照：`7877765dc0022db752f07a4dd8d152a878865eaedf34d2139a517ca7985345ce`。
- 原始命令的 SEC 联系身份只在外置环境使用；仓库证据中的命令已脱敏。输入是原已批准的合成 MSFT 持仓，不是用户真实仓位。
- `codex_exit_code=0`，但宿主返回 5；终态 `FAILED_VALIDATION`，阶段 `SPECIALIST_VALIDATION`，错误 `INVOCATION_ID_MISMATCH`。
- 本次没有请求格式修复，因此不能声称真实运行已证明修复路径成功；该路径本轮只有上述确定性正负证明。

### 最早可确认的偏差与阻断

Agent 输入原本有 96 个允许 Evidence ID，但实际工具事件首先出现 `EMPTY_EVIDENCE_QUERY`；Analyst 没有成功 query，输出 0 条 claims，并声称缺少可用身份/证据。独立 Skeptic 使用正确身份成功查询 8 个真实 Evidence（Yahoo 价格、派生指标及 SEC 披露）。不能把 Analyst 未取到证据归因为 Yahoo/SEC 整体不可用。

Analyst 清单身份为 `inv_e086b6539783063d258226cb`，实际输出却为 `inv_aa44cf77325380af22e1bb41`；Hook 的 SubagentStop 也记录了同一个错误身份，证明不是父线程落盘后才出现的差异。确定性 Validator 正确拒绝。现存 dispatch Hook 不保留原始派发消息，故不能进一步断言错误一定在父线程派发或子 Agent 内引入；不能用“LLM 非确定性”代替这项证据缺口。

后续聚合 `SKILL_LOAD_PROOF_MISSING` 是未完成完整执行证明后的诊断，不能覆盖产品首先拒绝的身份错误。本次确有读 Skill 事件及两个 SubagentStart/Stop，但完整成功执行证明未形成。

| 实际阶段 | 结果 |
| --- | --- |
| 数据准备、Gate、允许 ID 输入 | 已形成真实产物 |
| 两个独立角色生命周期 | 有实际 Hook 事件；不代表完整派发内容合格 |
| Analyst 证据查询/身份 | FAIL：空查询、身份错配 |
| Skeptic 查询 | 成功；原始输入/输出 hash 在 MCP 事件中 |
| Specialist 校验 | 正确拒绝，但产品研究验收 FAIL |
| CIO / Risk / decision / report / Eval | 未到达或缺失，不宣称 PASS |
| 源码运行前后完整性 | `source_integrity_unchanged=true`；不代表全进程隔离证明 |

外置完整 JSONL、stderr、Hook、输入/报告、Gate、Trace、错误及 process result 的 SHA-256，连同候选版本和完整源码快照，保存在 [运行证据](live-format-repair-smoke-result.json)。不回写历史运行包。

## 任务状态与下一步

Task 3.2/5.1 的本次指令接缝已补充测试证据；Task 2.6、5.2、5.3、5.4、5.5 仍未完成，不把来源成功或安全拒绝替代研究质量验收。当前不具备最终人工批准条件。

下一项具体问题是原始 Invocation/allowed_evidence_ids 向 Analyst 的派发及消费接缝，而不是数据 Provider 或代理。应先只读核对可取得的实际派发内容，缺原文时明确保留未知；再定点防止身份/允许集合丢失或改写，保持错误身份及空查询 fail-closed。本轮已用完批准的一次真实重试，未追加付费运行，未归档、提交或推送。
