# 新派发版本的一次真实单股 Smoke：FAIL

## 批准与执行范围

用户对“刷新本地插件，并通过现有宿主入口再执行一次真实单股 Smoke”回复“好”。本轮仅刷新缓存、执行这一次 MSFT 合成持仓验收并记录实际结果；未追加运行、修改投资实现、代理或校验标准，也未归档提交推送。

沿用上轮 57 项确定性测试：测试记录中的相关源码 SHA-256 经实际核对全部未变；仅更新插件缓存版本及对应 `version-manifest.json` 的 plugin hash，不将旧测试冒充新模型执行证明。插件结构校验、OpenSpec strict validate、`git diff --check` 均通过。

## 运行标识

- 安装版本：`0.3.0+codex.20260910123014`。关键安装缓存文件与仓库 hash 完全一致，见配套 JSON 的 installed_source_matches。
- 模型：`gpt-5.6-terra`。
- run_id：`live-60dfbf24-2090-4058-b29b-6e49ba6afcb5`。
- 产物根目录：`/private/tmp/stock-agent-dispatch-smoke.1vVMPf`。
- 源码快照：`c91354a6ee89b5d6fba9903e5cc530ec5eb1db00c3e8314b8172f73ce74abd6c`。
- 耗时 299.427 秒；Codex 退出码 0，宿主返回 5；没有将退出码 0 当作成功。
- 产品终态：`FAILED_VALIDATION`；阶段 `SPECIALIST_VALIDATION`；错误 `INVALID_CONFIDENCE`。

脱敏实际命令、输入/输出/事件完整 hash、候选锁与完整源码快照见 [运行证据 JSON](live-specialist-dispatch-smoke-result.json)。SEC 联系身份和完整原始日志只保留在外置环境，不复制到公开记录。

## 实际结果

| 项目 | 结果 | 底层观察 |
| --- | --- | --- |
| 安装新版本 | PASS | 缓存内容与本次源码一致 |
| 冻结输入 | 已生成 | 两个角色各有 96 个允许 Evidence ID |
| 输出身份 | PASS（仅此字段） | 两个角色输出均与自身 Invocation 相符 |
| 子 Agent 生命周期 | 有真实事件 | 两次 Start，Analyst 一次 Stop、Skeptic 两次 Stop；recorder_version 为 1.4.0 |
| 新派发消息检查 | 未获执行证明，FAIL | `subagent-dispatches.jsonl` 不存在，没有实际 dispatch_binding；不能用代码、配置或生命周期存在代替 PreToolUse 已执行 |
| Evidence 查询 | 先错误、后有成功事件 | 两次 EMPTY_EVIDENCE_QUERY；随后分别以 Analyst/Skeptic 身份查询 6 个 ID 成功。只能确认 MCP 事件所记录的调用身份，不替代完整独立研究执行证明 |
| Specialist Schema | FAIL | 两份报告 confidence 都是字符串 `LOW`，现行契约要求数值；未转换或补写 confidence |
| CIO / Risk / decision / report / Eval | 未完成 | 没有相应终态发布产物；只保留失败 Trace |
| 源码运行前后完整性 | PASS（hash 范围） | source_integrity_unchanged=true；全进程隔离仍 UNVERIFIED |

Skeptic 落盘报告仍声称缺少允许 ID，与冻结输入和后续成功查询事件并不一致；不把这个声明当作数据源事实。Analyst 有 3 条 claims，Skeptic 落盘报告没有 challenges，不能视为充分研究。两者均未通过结构校验，未进入语义评分，不输出投资建议。

聚合 launcher 的 `SKILL_LOAD_PROOF_MISSING` 是失败运行未形成完整执行证明后的状态；实际有根/产品 AGENTS、Skill 及 live reference 的读取事件，但不能因此认定整体加载证明通过。产品首先明确拒绝的是 INVALID_CONFIDENCE。

## 具体剩余问题

1. **派发检查接缝未获实际触发证明。** 新 recorder 已用于生命周期，但没有 PreToolUse 记录。当前 launcher matcher 是精确的 `^collaborationspawn_agent$`；原始 JSONL 只保留 wait 类型的协作事件，未提供足以确认实际 spawn 规范工具名的原文。因此工具别名或调用路径不匹配是排查方向，不写成已证实根因。
2. **实际输出没有遵守完整结构化契约。** 身份字段正确不等于完整消息传递成功；confidence 类型错误、初始空查询与 Skeptic 的缺 ID 声明仍存在。不得把 `LOW` 猜测成固定数字，不得替 Agent 改写报告，也不得因失败放宽校验。

后续应先针对真实派发检查覆盖路径和输入传递验证，不继续盲目反复付费 Smoke。本轮停止于证据归集，未启动第二次运行或全量 Gate；Task 2.6、5.2–5.5 仍未完成，整体 19/24，不具备最终人工批准条件。
