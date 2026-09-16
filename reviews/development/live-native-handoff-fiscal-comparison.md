# 三股原生交接与财年比较修复记录

日期：2026-09-11。Change：`us-equity-live-advisory-slice`。本记录不是完成批准或 Promotion PASS；Task 5.3/5.4/5.5 保持未完成。

## 本轮范围与实现

- Specialist：新 live 运行由已有 Stop Hook 保存最终 JSON 原对象，父线程不再转抄；独占写入、身份/模型绑定、冲突拒绝与原输出 hash 校验。非法 Evidence 不截断、不修复。
- Runtime Eval：新 live 作业让独立评分 Agent 只输出版本化评分草案；既有执行证明入口保存原草案，按真实会话及冻结输入生成技术元数据，原评分内容不变。旧结果及错误 hash 不修补。
- 财务比较：仅同一披露、相同发行人/tag/unit/context、非重叠且明确的年度/季度周期间允许比较，记录期间天数及未按天调整限制；不加入投资评分规则。
- 启动输入：超限 live 包中重复的完整 Evidence ID 数组使用可严格等价还原的引用表示；128 KiB 上限、权威文件与完整 ID 集合不变。

## 聚焦验证

107 项确定性测试通过（6.271 秒）；未执行全量 Gate、Regression、Calibration、Ablation 或 Promotion。

```sh
env TMPDIR=/private/tmp/stock-agent-handoff-tests.OHYmrI PYTHONDONTWRITEBYTECODE=1 \
 /private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest \
 tests.test_native_output_handoff tests.test_live_financials tests.test_start_context_dedup \
 tests.test_specialist_start_context tests.test_live_cio_final_response \
 tests.test_native_invocation_validation tests.test_live_collection \
 tests.test_live_eval_contract tests.test_eval_execution_proof tests.test_runtime_eval_job \
 tests.test_native_execution_proof tests.test_nested_codex_launcher -q
```

OpenSpec strict validate、插件验证及 `git diff --check` 通过。测试中的 fake adapter 仅用于确定性接缝，不代表真实模型执行。中途曾因插件 cachebuster 更新与 version-manifest 尚未同步产生锁不一致测试错误，完成同步后上述107项重新通过；不是忽略失败。

## 当前真实执行绑定

- 外置包：`/private/tmp/stock-agent-handoff-final.HgATup`。
- 批次：`live-batch-e971c405-a809-4e23-a86c-33fdbd3cfc1f`。
- Batch manifest canonical hash：`24ed4b1a125284ecde48d1a3ad1103b8d0bea19fb33491e3c0e7552969f2e629`。
- 冻结数据 snapshot hash：`80b4bf2ad5439442d248ba43e172876786a085bee2abb00f2dae461e68fce19e`。
- 实际安装插件：`0.3.0+codex.20260910180624`。
- plugin.json SHA-256：`346665fa9b4fd2f1efe00d5facde375ba7974caa3b9409ea77b0bd319b047d08`。
- 既有 protected-source snapshot：`219d1f3762460d112f03c4450ed396f419d66a8bd70ab61546eaedc4de54807b`。此值只覆盖既有 integrity_snapshot 范围，不是全工作区快照，更不是全进程强制只读证明。

真实执行使用现有宿主 `scripts/run-product-smoke.sh --profile live-us-equity --portfolio /private/tmp/stock-agent-live-three.xcXLr5/portfolio.json /private/tmp/stock-agent-handoff-final.HgATup/smoke`，PATH 指向上述合并依赖环境；SourceAccess 与 SEC 身份由外置文件/环境传入，不公开身份字段。逐子运行完整命令、参数、环境检查及事件保存在对应 invocation 和 batch launch-logs。合成持仓，不是用户真实持仓。

| 证券 / run_id | 实际运行结果 | 当前证据 |
| --- | --- | --- |
| MSFT / live-51e6dfeb-5626-42ce-b0c9-ac86e57eda3f | FAILED_VALIDATION，SPECIALIST_VALIDATION | 两个 Specialist 均有实际 Start/Stop，原报告均由 Hook 保存；Analyst 的 Skill hash 错误，严格拒绝。未进入 CIO/Risk，不当作研究通过 |
| AAPL / live-e23fd32e-4bf7-4c3b-b0fd-b206bad0bde1 | 运行时 PASSED，SAFE_NO_TRADE | decision.json、report.md、decision_trace.json、eval/result.json；独立研究质量评分另列，不与 native Eval 混淆 |
| NVDA / live-1ef29855-30dd-4fcf-ab97-c5312b78641f | 运行时 PASSED，SAFE_NO_TRADE | decision.json、report.md、decision_trace.json、eval/result.json；独立研究质量评分另列 |

批次进程退出5，真实判定 FAILED。AAPL 原生 Eval hash `0ca7c52a1f849c9fb8b623424f49e48b232bc0428b2f1d89eb732803ef040984`；NVDA 原生 Eval hash `2b97131aa2818db584a3a9fdbc986922f032edb2e1e771f3920ea8b59970ca1a`。

## 已关闭与未关闭

原样交接有实际关闭证据：MSFT 原始最终 JSON 与保存报告 hash 一致，未发生父线程转抄。AAPL 报告实际使用 FY2025/FY2024 营收变化并解释周财年限制，证明新财务比较进入研究内容，而非仅离线计算通过。

MSFT 新失败是模型原始 `skill_execution` 的 valuation invocation_hash 一个字符错误：

- 输出：`fea35a8e883ea1242323a6a0130017c3666ae5c1d8ea0f41fb513c040fc07985`
- 冻结期望：`fea35a8e883ea1242323a6d0130017c3666ae5c1d8ea0f41fb513c040fc07985`

这是技术元数据仍由模型转抄的实现脆弱点，不是交接文件损坏。Analyst 同时报告 live 工具不可用，但同一运行 Skeptic 有两次真实 MCP 查询；因此不能推导为整个 MCP/网络不可用。未伪造 Analyst 工具调用，未改原报告或期望 hash。

三股完整质量通过仍缺失；不能勾选5.3，也不为已知失败启动泛化独立复核。全进程隔离继续 UNVERIFIED。

更早 `/private/tmp/stock-agent-native-handoff.xJxRri` 批次在模型前因新增财务 Evidence 导致启动包超限，零模型调用；完成上述无损去重后使用本新批次，旧产物未改。上一轮 `/private/tmp/stock-agent-three-dedup.wQ7Oed` 结果及失败评分仅保留历史，不包装为当前锁通过。

## 独立语义评分：AAPL

作业 `live-handoff-semantic-e23fd32e`，目录 `/private/tmp/stock-agent-handoff-final.HgATup/semantic-aapl`。独立 Terra 父会话 `01a08c8e-0f20-7f33-be7f-95a892f56a80`、dev_eval 子会话 `01a08c8e-8467-7c90-b040-3d12b5005be1`。固定输入、命令与事件保存于同级 `semantic-aapl-invocation/`。

实际执行 `eval-prepare` → `eval-smoke-prompt` → 现有 Codex dev_eval → `eval-execution-proof --collect-native-output`；最后一步失败 `EVAL_NATIVE_MANIFEST_READ_MISSING`，未执行 eval-finalize。CLI 协调进程退出0不代表评分通过。

已读取子会话底层工具事件：子 Agent 对 manifest 执行了 jq 字段比较，但没有完整输出 manifest；完整读取发生在父线程，不能替代当前契约要求的子线程读取证明。原草案保存成功、程序封装未改评分；因证明失败，不当作正式 Eval 结果。

- 原草案文件 SHA-256：`58d40ec1bd0e6ad55b9200810e8ebd87b44c50376f9696b38787fa00bc343b78`。
- 封装结果文件 SHA-256：`6fb5de7b1348423b52d79268d25a868148cf66fc758362438de471e87d0c091c`。
- 调用 Prompt 文件 SHA-256：`8bc75c9dfe0325700d718144dbfc365c1d17b1c49254bb6a61978e0d54839f10`。
- 批次 runtime-result 文件 SHA-256：`04a3dfa23e7d98890d3afd184492dcb20f587deec2013b18cbc8e19b32d34bcb`。

草案将 Analyst grounding 评为1，其余四维为3；仅作诊断线索，不认定为已验证评分。该草案提及“决策日价格”及额外估值数据要求：现有 rubric 要求合格价格、两期可比业绩及披露，不要求实时数据；必须对照 PIT/时效与实际引用再判断，不把评分文本自动升级为新验收标准，不据此新增数据源或扩大范围。

## 独立语义评分：NVDA

作业 `live-handoff-semantic-1ef29855`，目录 `/private/tmp/stock-agent-handoff-final.HgATup/semantic-nvda`，固定 Prompt 与实际 CLI 事件在同级 `semantic-nvda-invocation/`。独立 Terra 父会话 `01a08c90-0f3a-71c2-a6e8-c197962332e7`，dev_eval 子会话 `01a08c90-903f-7ce0-9748-3faf605ca60e`。

实际完成 prepare → 独立 dev_eval → 原生草案收集/执行证明 → finalize；五维度均 PASS、grade3。再次调用 `verify_runtime_eval_job` 从底层产物重算，返回 PASS：Evidence 10/10、PIT泄漏0、Risk实际尝试1、合法 SAFE_NO_TRADE。未仅依据协调进程退出码判定。

- Eval hash：`28a8c7e9e6dd57be03f2a6e27db60e53dd9c8275d343f8c126111f755c108781`。
- 执行证明 hash：`14cb886ed541dee35eac22fafc8d65383b0846f6d38ae7a6d0c55c6aca484ae7`。
- 原生评分封装 output_hash：`3fb18f55b9975537d57249f2a4dd249f5ec0f5e2a5fb003998a79a712c77a68a`。
- Trace 验证 hash：`f6300f2b84e44c9aa23cb8f169ed6ee60fc7e76118bf11fe1b5293f145ad7846`。
- Artifact Replay hash：`6fb7e6864b7c6149b3b385f612d5d6ee2ebb66baa9edd5d2fb564a20c04289dd`。

两次评分结束后重新计算 protected-source snapshot，仍为 `219d1f3762460d112f03c4450ed396f419d66a8bd70ab61546eaedc4de54807b`。所有本轮模型进程已结束，没有自动重试。

## 收尾状态

本轮修复有107项聚焦测试和 NVDA 真实完整闭环证明，但三股并非3/3：MSFT 技术元数据错误；AAPL 评分输入读取证明缺失，草案研究质量意见尚不能作为正式验收结论。当前21/24任务，未启动已知前置未满足的5.4，也未请求5.5最终批准。未归档、提交、推送。

下一步需要明确 Specialist 原始研究内容与程序技术元数据的契约边界：不能通过修补这次错误 hash 解决。若采用类似评分草案的程序封装，须先同步现行“原对象保存”设计，保存原始模型内容、真实调用与新封装的各自血缘，并保持旧包校验不变；这不是放宽 Evidence/PIT/Risk。评分派发则应把完整 manifest 读取明确放入子 Agent 任务，父线程读取不能替代。不得为此重跑完整平台 Gate。
