# Codex 兼容性记录：0.153.4

## 已验证环境

- Codex CLI：`codex-cli 0.153.4`
- `multi_agent`：`stable = true`
- 实际运行的 `multi_agent_version`：`v2`
- 检查日期：`2026-09-06`

## 可重复探测命令

```text
codex --version
codex features list
codex exec --help
codex plugin --help
codex mcp --help
codex debug --help
```

## 已确认能力

- `codex exec` 支持非交互运行、显式 `--model`、`--json` JSONL 事件、`--output-schema`、`--strict-config`、`--cd` 和 `--add-dir`。
- 项目级 `.codex/agents/*.toml` 可由 `spawn_agent.agent_type` 选择；子会话会记录非空 `agent_role`、父会话 ID、独立 session ID 和对应开发指令。
- `runtime_company_analyst` 与 `runtime_skeptic` 已在同一父运行中分别启动，且两个派发均发生在第一次 `wait_agent` 之前。
- 两个专业 Agent 均实际调用 fixture-only 只读 MCP；Company Analyst 另调用确定性计算工具，未发现 Web、外部 Provider、券商、账户或原始 fixture 读取。
- `product:portfolio-council` 可由已安装本地 Plugin 发现，专业 Agent 的 Skill 配置、Invocation Manifest、输出协议和 MCP 事件可共同形成可验证证据链。

## 0.153.4 事件格式适配

父 rollout 中的 `spawn_agent.message` 以受保护的加密包保存，子 rollout 不再重复保存可读任务正文。因此执行证明同时支持两种模式：

1. 旧格式：子会话中存在可逐字核验的 `run_id`、`invocation_id` 和 task prompt。
2. 当前格式：父会话具有格式有效的受保护派发包，派发参数与子会话身份匹配，子 Agent 的最终结构化输出以 `run_id`、`invocation_id` 和 `agent` 回绑，并与落盘报告哈希一致。

普通占位字符串不能冒充受保护派发包。无论采用哪种模式，task prompt 的本地版本和 hash、Agent 文件 hash、模型、Codex runtime、Skill 配置、MCP 事件及最终输出 hash 都必须闭合；缺少任一项均失败。

## 实际探针结论

旧版的 `BLOCKED_CUSTOM_AGENT_DISPATCH` 已解除。真实探针证明：

- `spawn_agent` 保留 `agent_type=runtime_company_analyst` 或 `runtime_skeptic`；
- 子会话加载对应 `.toml` 中的 `developer_instructions`；
- 两个 Agent 使用不同 session，Skeptic 的 `fork_turns=none`；
- 更新后的最小化执行证明可以验证该真实双 Agent rollout。

兼容性阻断解除后，正常、冲突与 Risk 三类真实运行均已成功通过 CIO、Risk Engine、终态产物和实际 Eval；未来或过期场景也已按设计在 Agent 前安全终止。兼容性结论不代表真实市场数据能力已经实现。

参考：[OpenAI Subagents](https://learn.chatgpt.com/zh-Hans/docs/agent-configuration/subagents) 与 [OpenAI Codex 更新日志](https://learn.chatgpt.com/docs/changelog?translationFallback=zh-Hans)。
