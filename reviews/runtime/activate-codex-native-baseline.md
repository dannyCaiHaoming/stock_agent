# Codex-native Fixture Council 实施基线

## 基线版本

- 仓库提交：`0feb278 feat: establish LLM-native portfolio council`
- Python 包版本：`0.1.0`
- 基线日期：`2026-09-05`
- 测试命令：`python3 -m unittest discover -v`
- 测试结果：92 个测试通过，0 个失败。

## 0.1.0 运行时结论

0.1.0 已验证 Evidence、Portfolio、Risk、Trace、Learning 和 Eval 的确定性契约，但 `tests/test_council.py` 与 `tests/test_end_to_end.py` 通过 Python callback 生成专业报告和 CIO 草案。该路径只能作为测试参考，不能作为以下事项的完成证据：

- `portfolio-council` Skill 被 Codex 实际加载；
- Company Analyst 与 Independent Skeptic 作为独立 Subagent 被调用；
- 专业 Skills 被纳入实际调用指令包；
- LLM 生成 Thesis、Counter Thesis、Action 或 Confidence；
- 真实 Codex 事件、MCP 工具调用与 Agent 输出形成运行血缘。

`product.council.orchestrator` 因此被保留为 test-only reference state machine。Codex-native 产品入口不得导入或调用它来编排 LLM。

## 后续回归基线

实现 `activate-codex-native-fixture-council` 后，完整确定性测试不得少于本记录的 92 个通过项；新增测试需要覆盖资源发现、Evidence Gate、fixture MCP、Invocation Manifest、终态、Trace、Replay、Eval 与真实 Smoke 真实性门禁。
