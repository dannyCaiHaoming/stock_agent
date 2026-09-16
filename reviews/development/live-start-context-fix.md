# Live Specialist 冻结上下文交付：限定修复

批准记录：`live-start-context-approval.md`。继续当前 `us-equity-live-advisory-slice`，不是完成或晋升批准。

## 实现与证明边界

- 复用现有 SubagentStart，在真实角色启动事件中生成并注入完整冻结 Input/Invocation/Prompt/Schema；逐角色记录内容 hash、父/子 session、model 和回执。父线程只派发固定角色短票据，不拼写 Invocation ID。
- 使用 Hook `additionalContextLimit=0` 避免默认文件溢出；生成器先执行 128 KiB 字节上限，超限明确失败、不截断。此设置只针对有界启动上下文。
- MCP 查询前、CIO 收集专业报告时、真实执行证明以及 launcher 完成检查均重算冻结内容绑定；报告必须回传 receipt 到 `artifact_refs`，不得污染 Evidence ID。
- PreToolUse 仍在实际被调用时严格拒绝错误票据、重复角色与错误隔离参数。live 不再要求缺少覆盖证明的两个 PreToolUse ALLOW；不声称 SubagentStart 能阻止子 Agent 启动。缺失、失败、篡改或未回执不能进入成功终态。
- Evidence Closure、PIT、Risk 与格式修复规则未放宽；fixture 与历史包沿用原契约，历史原文、产物和版本锁不改。
- 修正完成检查遇到缺失 run_manifest 的普通错误，优先保留实际 FAILED_VALIDATION 的根因。

## 当前确定性验证

实际命令、120 项输出及完整受保护源码/安装资源 hash：`live-start-context-tests.json`；包括13项新增启动接缝。OpenSpec strict validate、插件校验及11个安装关键文件逐字节一致检查通过。校验器复用外置 PyYAML，未改变 live 依赖。

受保护源码快照：`fc154fac8e605a637eeedcd8e6c49d1703ee040b7d8a6ac965483823dbe6621a`。插件版本：`0.3.0+codex.20260910152435`。其中合成旧快照只用于接缝单测，不证明 v4 数据准入或模型研究；真实运行另记。

Task 3.2/3.5 的本次增量及5.1的受影响确定性部分有上述证据；Task 2.6、5.2–5.5仍未完成。上一轮90项与原始SEC离线重解析只证明当时数据修复，不冒充本轮真实运行结果。

## 真实运行

获批的一次真实单股验收在 `/private/tmp/stock-agent-start-context-smoke.AErH4g/run`，使用现有宿主入口、外置合成持仓、已批准来源配置与 Terra。已结束，真实结果为 **FAILED**；完整底层文件 hash 与最小化事件见 `live-start-context-smoke-result.json`。

- run_id：`live-ea56970a-e572-4c6d-8708-86d372bd3546`；父会话：`01a08bee-2bea-7d20-bcc2-cdf5d1b0e0fc`。
- candidate lock canonical hash：`e29b183434be9d7941439e42e122f22283906ae9c4e30635d86f0bca8c96cbf8`。
- 真实采集选择 Yahoo/MSFT；快照 `3ac90957d48f877a2abf14898b635845707f6ca77e1b103b612b57279b43826c`，386条事实、41条派生指标、20000字符有界披露。材料可供研究，不等于研究已完成。
- FIRST_DIVERGENCE：第一条真实 `collaborationspawn_agent` 在 PreToolUse 返回 `DENY_DISPATCH_CONTRACT`。当前短票据 expected/actual message hash 不同，role、task_name、fork_turns均正确；两角色合计5次拒绝，无 SubagentStart、MCP、专业报告、CIO、Risk 或 Eval。没有新外层模型重试。
- 已确认的直接原因是短消息逐字比较拒绝；有限 JSON 排序/空白/转义组合未匹配实际 hash。最小化记录未保存消息正文，**无法确认具体字段差异或是运行机制对消息的处理**，不得笼统归因于 LLM 随机性，也不声称 SubagentStart 已真实交付成功。
- 内层 exit=0 不代表成功：launcher exit=7，宿主 exit=5，耗时162.05秒，源码完整性未变。运行 Trace 的 terminal_state 仍为 null，final-message 的 FAILED_VALIDATION 文本不是合法终态；check-run明确失败。process-result 的 SKILL_LOAD_PROOF_MISSING 是未形成最终证明的下游摘要，直接根因以实际 Hook 拒绝事件为准。
- Task 2.6、5.2–5.5 保持未完成。单股未过，故不启动三股、语义评分或独立收尾复核，不把缺失产物写为 PASS。

后续若要调整短票据的逐字匹配契约（例如只核对显式角色/隔离/运行身份、以冻结包绑定作为内容交付依据），须透明说明并获批后实施，不能静默删掉拒绝。新真实付费运行也需授权。本轮不自动重跑、不归档、不提交、不推送；全进程隔离继续 UNVERIFIED。
