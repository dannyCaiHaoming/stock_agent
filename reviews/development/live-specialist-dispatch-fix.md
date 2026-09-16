# Specialist 派发身份与证据输入接缝修复

## 原因与证据边界

对应当前 `us-equity-live-advisory-slice` Task 3.2、5.1，以及未完成的 5.2。

上次真实运行 `live-4b6a421c-d4d0-4b24-af8a-eaf34513a1cd` 的冻结 Analyst 输入有 96 个允许 ID；清单身份为 `inv_e086b6539783063d258226cb`，子 Agent 输出/Stop Hook 却是 `inv_aa44cf77325380af22e1bb41`。MCP 有空查询错误，无 Analyst 成功查询；Skeptic 成功取得真实证据。原始事实与 hash 见 `live-format-repair-smoke-result.json`。

可确认的实现缺口：主线程原先需自行组合完整派发消息，现有 PreToolUse 只检查角色及重复派发，没有将实际消息与冻结 Invocation/Input 比较。旧 dispatch 事件不保留原消息，在本地目标会话文件名中也未找到该次 ephemeral 父/子会话。因此不能断言错误 ID 最早由父还是子 Agent 引入，不编造完整根因证据，也不归因为数据 Provider 或代理不可用。

## 限定修改

1. `invocation.py` 新增确定性消息生成函数，复用现有 Invocation 校验，读取固定 run-scoped Input、Prompt、Schema、Gate，核对路径、run/agent/invocation 身份、输入/Prompt/Schema/Skill hash 及允许 ID 集合。将完整既有资料序列化为单个消息，不生成 Thesis/action/confidence，不新增模型编排。
2. `smoke_prompt.py` 使用上述消息映射，要求将对应 JSON 字符串作为 `message` 原样派发；不再要求手工拼装 ID。live 文案转换在附加冻结消息之前完成，避免改写输入字符串。原预 Agent 安全终态不生成派发消息；实验入口只为实际存在的 Specialist 生成消息。
3. 现有 `codex_hook_recorder.py` 更新到 `1.4.0`，在原派发检查内重建预期消息，核对 `message`、`task_name`、`fork_turns`；不一致或依赖缺失明确返回 deny，不使用 `updatedInput` 偷改参数。记录预期/实际消息 hash、是否匹配和原事件 hash，不记录上下文正文。被拒绝的调用不占用角色名额；合法重复派发仍拒绝。

Hook 拒绝格式依据 [OpenAI 官方 Hook 文档](https://learn.chatgpt.com/zh-Hans/docs/hooks) 的 PreToolUse 契约。此次仅用现有已注册 Hook，不增网络探针、沙箱、权限配置或新运行框架。实际 Codex 是否加载新 Hook 仍需后续宿主 Smoke 留证，独立进程测试不代替该证明。

保持 `format_repair.py`、Evidence/报告 Validator、Risk、数据采集和现有来源不变。非法输出仍按原规则拒绝；即使输入传递正确，LLM 也可能在输出时写错身份，本修复不保证模型必然完成研究。

## 实际验证

完整命令、标准输出与文件 SHA-256 见 [测试记录](live-specialist-dispatch-tests.json)。

| 验证 | 结果与范围 |
| --- | --- |
| 57 项受影响确定性测试 | PASS；含派发、既有 Hook/launcher、Invocation、运行包、live profile 与实验入口兼容单元测试，不是实际 Ablation/Regression |
| 两个角色完整参数原样传递 | PASS；只包含各自输入，不带其他角色结论或原始 Evidence 值 |
| 错误 ID、空 ID 集合、缺输入、错误角色、额外消息、缺 message、错误 task/fork | 明确 deny，负测 PASS；没有静默修复 |
| 底层输入被改或 Manifest 缺失 | 明确 deny，负测 PASS |
| Hook 独立进程，从非仓库 cwd 运行 | 正确输入 ALLOW，错误输入 deny；未启动 Codex/模型 |
| 历史 live 包只读消息生成 | 两个角色各保留 96 个 ID，正确身份，生成消息与新 Smoke 中字符串完全一致；诊断，不是 execution replay |
| 历史原始产物 hash 重核对 | 与上次 evidence JSON 的 artifact_hashes 全部一致，未覆盖失败包 |
| OpenSpec strict validate / git diff --check | PASS |

第一次只读 live 核对误用了未安装交易日历的系统 Python，报环境依赖缺失；改用既有锁定 live venv 后成功，未安装新依赖。测试日志中的 `NATIVE_EXECUTION_PROOF_FAILED` 为预期负测输出，不是实际产品运行。

## 完成状态与下一步

当前仍为 19/24。Task 2.6、5.2–5.5 保持未完成；本轮不追加付费运行、不执行全量 Gate、不修改生产指针、不归档提交推送。

下一步仅需在允许一次真实重试后，用既有更新流程刷新安装包并从现有宿主 launcher 运行一个全新单股 run_id，核对新 dispatch_binding、实际独立角色查询和完整终态，再进入原定语义 Eval。不能用旧包生成的新消息冒充已经重跑，也不能假定当前安装缓存已经更新。无需用户修改数据源或代理配置。
