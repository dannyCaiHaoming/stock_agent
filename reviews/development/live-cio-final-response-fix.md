# CIO 原生最终响应：实施与验证

本次继续 `us-equity-live-advisory-slice`，只关闭真实单股运行中已观察到的 CIO 长 Evidence ID 抄写错误。未新建 Change、Agent、Skill、模型编排后端或网络设施。未修改历史失败包、权威 Evidence Closure、NO_TRADE 条件、Risk 或原生权限。

## 修复及依据

- `invocation.py`：从 canonical CIO Schema 投影原生解码形状；顶层与 conflicts 引用限定当前 Gate 原始 ID。大型集合使用同一完整集合的精确正则，不删证据。
- `smoke_prompt.py`：仅宿主 live 原生最终响应模式让主线程直接返回草案 JSON，不再另抄 CIO 文件；fixture 和默认文件模式保留。
- `nested_codex.py`：启动时传入 `--output-schema`，记录实际文件/hash。要求完成事件和最终消息一致，拒绝缺失、非法 JSON、重复键及覆盖；逐字保存模型响应，再沿用实际执行证明、canonical Validator、Risk 和 Eval。
- 解码通过不是终态通过。所有投资内容仍由 LLM 生成，Python 不补动作、Thesis、confidence 或引用。

本机 `codex exec --help` 确认支持该参数；[官方非交互说明](https://learn.chatgpt.com/docs/non-interactive-mode)说明它约束最终响应，不约束模型另写的任意文件。[Structured Outputs 说明](https://developers.openai.com/api/docs/guides/structured-outputs)列明条件关键字及 enum 容量限制。因此仅投影解码 Schema，原 canonical 条件仍在输出之后完整执行，未放宽安全规则。

## 实际验证

完整命令、输出和受保护源码文件 hash 见 [测试记录](live-cio-final-response-tests.json)。

| 检查 | 结果 | 证明范围 |
| --- | --- | --- |
| 新增9项 CIO 接缝测试及既有相关测试，共52项 | PASS | 原生参数接入、两层合法引用集合、实际错字拒绝、null/0区分、事件绑定、原样保存和失败传播 |
| 合成合法最终响应→现有 finalize/Risk | PASS | 真实确定性处理；模型与执行证明为显式测试替身，不算实际 LLM |
| OpenSpec strict validate | PASS | 当前 Change 规格一致性 |
| git diff --check | PASS | 差异格式 |
| 新版真实单股 Smoke / 语义 Eval | NOT_RUN | 等待一次付费运行续批，不自动重试 |

受保护源码快照：`2f38efce146c3943070609db27039703d0402da1167c0de29459a6e04b7d286b`。该快照沿用现有产品文件范围，不代表全部工作区或强制隔离证明。`ISOLATION: UNVERIFIED`。

## 后续边界

当前19/24项。2.6、5.2仍缺真实最终报告与实际语义评分；随后才是5.3三股、5.4独立复核、5.5人工完成批准。本轮不勾选这些任务，不归档、不提交、不推送。

已安装插件仍为上一轮版本，未刷新；下一次获批真实运行前须使用既有更新流程，让全新 Codex 会话读取本次实现。旧真实失败不能包装成新版成功，52项合成测试也不能证明真实研究质量。没有启动模型、Replay、Regression、Calibration、Ablation 或完整 Gate。
