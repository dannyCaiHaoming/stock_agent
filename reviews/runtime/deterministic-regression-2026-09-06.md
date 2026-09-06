# 确定性回归记录：2026-09-06

## 范围

本记录覆盖 `activate-codex-native-fixture-council` 的确定性单元测试、集成测试、Schema、MCP、架构边界、状态机、Replay、Trace、Risk Engine 和产物驱动 Eval 门禁。

本记录与同日运行时就绪审计共同支持真实 Codex 验收。`codex-cli 0.153.4` 已解除自定义 Agent 委派阻断，正常、冲突和 Risk 三类真实 LLM 场景均抵达 Risk Engine、终态三件套和实际 Eval；未来或过期场景按设计在 Agent 前安全终止。

## 命令与结果

| 命令 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -v` | PASS：160 项测试，0 失败 |
| `openspec validate activate-codex-native-fixture-council --strict` | PASS |
| `git diff --check` | PASS |
| Codex Plugin 校验器检查 `product/` | PASS |
| Codex Skill 校验器检查六个 `product/skills/*` 目录 | PASS |
| `codex debug prompt-input '$product:portfolio-council fixture preflight only'` | PASS：模型可见 Skill 列表包含已安装的 `product:portfolio-council` |

## 已覆盖的确定性验收范围

- 同时针对 `as_of` 和 `retrieved_at` 的 point-in-time 过滤。
- Evidence 来源元数据和引用闭包。
- Gate-scoped、只读 fixture MCP 行为。
- 两个专业 Agent 的独立输入构造。
- 不新增事实或 Evidence ID 的一次性格式修复。
- 子 Agent 最终输出与落盘报告的哈希绑定。
- Codex 0.153.4 受保护派发包与结构化输出的任务回绑。
- CIO 输入最小化和 Gate-scoped Evidence 查询。
- CIO 对结构化冲突及其置信度、动作影响的消费。
- deterministic Risk Engine 的批准、修订和否决边界。
- 三类终态的产物矩阵。
- Decision Trace 遍历和产物哈希。
- Artifact replay 与版本锁定的 Native rerun 准备。
- 不依赖固定投资动作的四类 fixture Eval 不变量。
- 禁止宣称市场收益、Alpha 或预测提升的 Eval 范围门禁。
- 禁止 Python LLM 编排和硬编码投资结论的架构门禁。

## 剩余发布门禁

确定性测试、四场景 Smoke、脱敏验收包和运行时就绪复审均已完成。Change 归档前仍需人工审阅验收矩阵并明确批准。
