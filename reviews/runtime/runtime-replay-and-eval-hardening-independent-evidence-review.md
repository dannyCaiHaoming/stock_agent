# runtime-replay-and-eval-hardening 独立证据复核（修订）

- 日期：2026-09-09（Asia/Shanghai）
- Reviewer：全新独立 Reviewer；未参与实现。
- 方法：严格只读、定点复核；未运行测试、LLM、Regression、Replay、Ablation、Promotion、OpenSpec validate 或 Release Gate。
- 唯一写入：本记录。
- 判定原则：不采信报告中的 PASS；以直接读取的 JSON/JSONL、源码、Git 差异及独立 hash 重算为准。

## 1. 规格、范围与任务状态

- 已读根 AGENTS.md、Proposal、Design、Tasks、三个 delta spec、两份 review 及上一轮独立 Gate 报告。
- 规格要求 Artifact/Execution Replay 分离、统一终态 Trace、真实 Runtime Eval、12-case typed Regression、隔离 Ablation、确定性 Promotion 硬门禁；自动 Gate 不得修改生产系统，实际晋升须人工批准。
- 11.1–11.9 的实现与证据闭包已具备；Task 11.10 保持 `[ ]`。11.10 是本次独立复核之后的 Gate/人工批准/归档流程项，不作为技术实现阻断，也未被修改。
- 历史 Execution Replay、Ablation、Calibration、Promotion 仅用于证明 Change 能力已实现；未包装为当前候选锁的晋升证据。

## 2. 源码差异、全文审计与哈希

- 指定 `git diff --` 显示三个 tracked 测试文件共 +335/-14；`nested_codex.py`、`codex_hook_recorder.py`、`test_nested_codex_launcher.py` 当前为 untracked，故 Git diff 为空。未跟踪是尚未归档状态，本身不构成失败。
- 已全文读取并审计上述三个 untracked 文件；内容可读、控制流可定位，无“无法审计”缺口。
- 字节 SHA-256：
  - `product/runtime/nested_codex.py` = `8aec4e641a0cfdee0040e33e2481cda79d99eb48f7cf70f1d4b53a2449ee74c2`（匹配要求）。
  - `product/runtime/codex_hook_recorder.py` = `e276180b0bfd3d9d21e48f0b6e2ff7bcf2ecd2df3f33cbe7d58b3843cf43bf31`（匹配要求）。
  - `tests/test_nested_codex_launcher.py` = `83d48343431c9ef47926a89f253f54da380c3f06a2d81c7b4cdd254995a85997`。
- launcher 固定 product cwd、run-scoped sqlite/log/tmp、Hook 与 prompt，进程退出后以 execution proof、Risk、Trace、产物矩阵和 check-run 判定；Codex exit=0 不是成功充分条件。
- hook recorder 将日志路径限制在 run_dir，原子拒绝重复/未授权 Agent，最小化事件且不保存 prompt/推理正文；并行屏障要求两个 Specialist 均 Start 后才允许首个 Stop。

## 3. Source integrity 独立重算与写入隔离

- 按 `product/runtime/run_package.py::integrity_snapshot` 定义，只读枚举 82 个受保护 product 文件，逐文件 SHA-256 后计算 canonical snapshot。
- 独立重算结果 = `24fe59edbc75db2c5d667df7e58b069f63e136aad59a0ff22782cb27e0fa74fb`，与 normal smoke、六个 Regression run 的 before/after manifest 及 capsule 声明一致。
- 重算集合内 nested/hook 哈希分别为要求的 `8aec…74c2`、`e276…bf31`。
- 现有 Proposal/Design/Specs 未要求 Codex 进程完全零 filesystem-write；它们要求源运行/产品文件不被修改并允许持久化新运行产物。
- 三次 normal smoke 与六个接受 Regression run 的 environment manifest 仅列出 run_dir、run_dir/.codex-runtime/{sqlite,logs,tmp} 四类可写路径，全部位于各自 run_dir；写探针均成功。
- 九次 process result 均为 `source_integrity_unchanged=true`，before/after 均等于 `24fe…74fb`。因此 `workspace-write` 在现有规格下体现为 run-scoped 物化能力，未观察到源代码写入。

## 4. Runtime 工具、Risk 与学习/晋升边界

- MCP registry 的 `AccessMode` 只有 `READ`；fixture MCP 仅暴露 query/calculate，annotations 为 readOnly=true、destructive=false、openWorld=false。
- Trace 中实际 MCP events 均为 `access_mode=read`；Specialist 权限仅 `fixture_evidence.query` / `fixture_math.calculate`，无 broker/account/order/production-promotion 工具。
- Risk policy 的 RuleBasis 仅 accounting_identity、mathematical_definition、data_quality、explicit_mandate；metric allowlist 仅守恒、时效、仓位/行业/现金权重、换手、ADV 参与、long-only、leverage。
- risk-veto/high-concentration 的底层 Risk 记录给出 POSITION_LIMIT、LIQUIDITY_LIMIT、SECTOR_LIMIT 的 observed/limit/policy_rule，并确定性映射为 `NO_TRADE + RISK_VETO`；未见主观投资评分进入 Risk Engine。
- `ImprovementProposal` 是带 replay/rollback 的提案契约；promotion policy 明示 `automatic_production_mutation=false`，PromotionRecord 强制 approved_by、decided_at、rollback_conditions。未发现学习面自动修改生产文件或版本指针的授权。

## 5. 三次 normal smoke 与六个接受运行

- normal-smoke-01..03 的 environment/process/dispatch/lifecycle/Codex events/Trace/decision/Risk/eval 已直接交叉核对。
- 三次 run、parent session、两个 child session 均独立；每次两个 Specialist Start 均早于首个有效 Stop；Company Analyst、Skeptic、CIO、Risk lineage 和终态产物完整。
- 三次均为 Terra、launcher PASSED、SAFE_NO_TRADE、advisory_only=true、Risk APPROVED，且 native eval 的结构、Trace、Risk passage、artifact replay 均 PASSED。
- 六个接受运行 normal、insufficient、strong-conflict、risk-veto-retry-01、high-concentration、llm-overconfidence 的同类底层文件均已直接核对：唯一 run/session、完整双 Specialist+CIO、Risk 未绕过、source integrity 未变。
- llm-overconfidence 的重复 Skeptic 调度被 `DENY_DUPLICATE_AGENT` 拒绝；实际仅有两个不同 Specialist child session。

## 6. 六个 Runtime Eval / grader proof

- 六个 `eval/result.json` 与 `grader-execution-proof.json` 已全文读取；全部 status=PASS，所有确定性 hard gates 为 PASS。
- 公共 lineage：agent=dev_eval、model=`gpt-5.6-terra`、prompt=`937f77555a8f4f251de353019cc52b3e7e58fc532a16b2013f0f62a250edd4de`、rubric=`8c4e0b1233b26f8799e9e083070945b936781b528a56f6dd2da3cc5cf409131f`。
- 逐案 canonical 重算（input/output/proof/eval）均一致，proof hash 也与 eval result 的 execution_proof_hash 一致：

| case | parent / child session | input hash | output hash | proof hash |
|---|---|---|---|---|
| normal | `01a08206-437f-7c12-8d48-5f472a630b90` / `01a08206-a9e6-7102-bb7b-5b413cfae103` | `70716c462b0e6175672a91c47ba3cacea2e21c3dea79e2af0235043ac8a7a9b1` | `d3d01692fc145b5a487c0a2d5a983de607326bdc909c3a76133e5f6be9383752` | `8936a981083d3427f569f857b59e0a5c11bbb00077f5011cbb0fbf32551d76a2` |
| insufficient | `01a0820a-9487-7990-bf2b-c5265ada99b1` / `01a0820b-0276-7dd2-878c-2468f6f9b57f` | `9054784f2f7333606cb8996d99198aa6863b97d2b252c316653f06686c6a8b2b` | `89727cb8a59527ffdfe1b1b05e4b09a80c15f7ddf5e9a54fb40c043f2c1c59b0` | `0af94c40142142441276e60d6ce27f191a94d53f3ac0e534fe24f4f056e05c24` |
| conflict | `01a0820a-9486-7e13-90c5-ff25105ead5c` / `01a0820b-0f08-7e60-835d-4bdd0b517485` | `1f64bb326436ba6ad378ecf2ab1adc0f4d3ecfc322dc2ea7073bbd63722ec965` | `c7375c09d11da69d2b3cb1f78ec5e2b6bd0d84def6c891a034f37ac06848d08b` | `cde173b965a86e5d4161223ddafeb85187d3b532342e60ff7aaf720006aea695` |
| risk-veto | `01a0820d-cd19-74c2-8298-dc7cf24efae2` / `01a0820e-3e09-7731-b110-c6dc13c370dc` | `2a563310d4ff86b08cdc96483e8e84527a06f387899089220b98faadc638b901` | `3bc64fb29d00683b83862aedc8f076cc2515565f5d591663b45f6d11295fa8c5` | `12edf64d848ae4953c0eaeb2af2711d047116083ddf1d0cfa800d84057d164a2` |
| concentration | `01a0820d-cd21-71a2-a9a9-e7ee72a852bb` / `01a0820e-3870-77b3-8764-8af48a767501` | `465da2c9f61523601ee4daf3e2fb891e37e6166cb3f42235d12d04520224e6a4` | `063c73116ff9119805eeb1baed51c2dd62be4978014c79b30848b679c1cfe412` | `9be2d83fd820ee22991477f9a0b16c574b63dfc04e5c3e033cccdf9f4171088f` |
| overconfidence | `01a0820d-cd17-7441-99bb-467b3d431adc` / `01a0820e-3209-7613-bf3e-cb49be738925` | `9b1411d9690443a7b7a432e64817ca3c99bd7a6475ec1d6c94a98c15c81e9a8e` | `8e1c51aba9b8fe867cbe8766ab5e7b2c9ab73805deb86a2af81afa3a25f789b0` | `f62266085a3ec0c562322581b68e3e0898efe252fa178a3266ba294f37ebbf08` |

- 12 个 parent/child session ID 全局唯一；每案 parent != child；raw prompt/reasoning 均未保留。

## 7. Regression suite 与当前候选边界

- suite input：candidate=`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`；Regression Set=`1.1.0` / `6004fb79ed7ec5de46310e017cf493b2362b3259ddf2222982d78e75d9a143ef`。
- suite result：12/12 PASS；suite hash=`179b70a83526db786357354a5bdcddcae55c06cabe05e513e81b8db3e55c7b39`。
- normal、future-information-leakage、risk-veto 的 execution-proof/outcome 已直接读取；均绑定当前 candidate。Future case 为真实 pre-Gate deterministic injection、零 LLM、两个未来 Evidence 被排除、leak_count=0；risk-veto 为真实 Risk REJECTED 且未绕过。
- diagnosis 第 9 节的一串 Regression hash 与底层不符；底层 suite/input/Trace 一致支持要求的 `6004…43ef`，故报告文字视为摘要错误，不影响底层闭包。

## 8. 缺口分类与结论

- Reviewer 尚未读取：无；最初指定的既有证据现已补读完成。
- Change 技术证据：11.1–11.9 闭包成立；未发现对应 Proposal/Specs 的技术阻断。
- 仓库当前候选晋升证据：仍缺同一 `618f…ac198` 锁下完整 Execution Replay、当前锁 A/B/C Ablation、Promotion Gate PASS 及人工批准记录。历史证据仅证明能力，不补足当前候选晋升图。
- 未修改 Task 11.10，未归档、提交、推送或晋升。

CHANGE_REVIEW: PASS
CANDIDATE_PROMOTION: NOT_PROMOTABLE
阻断项：无（Change 实现/11.1–11.9）；当前候选晋升缺口为同一 candidate lock 下 Execution Replay、A/B/C Ablation、Promotion Gate PASS 与人工批准记录，对应 decision-trace-evaluation 的 Execution Replay/Ablation 要求及格式、controlled-learning-loop 的真实证据图/人工批准要求及 Task 11.10。
