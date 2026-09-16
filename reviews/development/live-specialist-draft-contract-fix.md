# Specialist 研究草案契约限定修复

日期：2026-09-11。Change：`us-equity-live-advisory-slice`。

## 人工批准

用户对上一轮提出的限定调整回复“是”：Specialist 生成研究内容，技术 hash 由程序根据实际执行封装；保留原始输出，不修补历史失败，不降低 Evidence/PIT/Risk，同时修正评分子 Agent 的读取指令。批准只涵盖该调整及实施，不是 Task 5.5 完成批准。Proposal、Design 9、相关两份 Specs 和 Tasks 已同步；数据规格无需改动。

## 已实施

- 新运行使用 `native-research-draft/1.0.0`；模型展示 Schema 仅移除 `skill_execution`，其他研究/身份/引用字段不变，磁盘 canonical Schema 和最终 Validator 不放宽。
- 现有 Stop Hook 保存 `agents/<agent>.native.json` 原始草案，再保存仅增加冻结 `skill_execution` 的完整报告。实际角色/模型/Invocation 必须匹配，模型自己输出技术字段则拒绝，不将错误元数据静默覆盖。
- 执行证明读取原始草案，重新封装并与完整报告比较，同时对照真实 Stop 的原始输出 hash 和 capture hash。研究内容被改动或原草案缺失时拒绝；真实角色/Skill/MCP 等已有证明继续执行。
- 旧 `native-final-json/1.0.0` 和 fixture 路径保持原语义，不修改上一批 MSFT、AAPL、NVDA 的产物。
- 评分协调 Prompt 明确要求把完整 manifest 读取写入 dev_eval 子任务；父线程读取不替代。没有放宽输入读取校验或修改 rubric。

## 限定测试

最终95项通过，耗时5.481秒：

```sh
env TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 \
 /private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest \
 tests.test_native_output_handoff tests.test_native_execution_proof \
 tests.test_specialist_start_context tests.test_start_context_dedup \
 tests.test_eval_execution_proof tests.test_runtime_eval_job \
 tests.test_native_invocation_validation tests.test_nested_codex_launcher \
 tests.test_live_cio_final_response tests.test_live_eval_contract -q
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

OpenSpec strict 与差异格式检查通过。新增覆盖草案原样保存、技术字段唯一封装、身份/模型拒绝、非法引用不修补、覆盖拒绝、展示 Schema 投影、真实执行证明接缝及草案篡改拒绝；独立进程从外部 cwd 直接执行 Hook 亦通过。首次合成证明测试因复用本测试刚生成的旧证明触发禁止覆盖，调整临时夹具生命周期后通过，未放宽产品禁止覆盖行为。

这些是确定性接缝证据，不是新契约的真实 LLM 验收。本轮未追加模型、真实数据采集或全量 Gate。一次辅助版本查看命令路径输入错误，未执行目标程序；不影响上述独立测试结果。

## 本轮相关文件 SHA-256

| 文件 | SHA-256 |
| --- | --- |
| product/runtime/invocation.py | 7bd990468df7fa283de69530a62b75a868b98644c6b4c5558d8fbc97b36369cd |
| product/runtime/codex_hook_recorder.py | 49464ce412ba197087192413d8c3be370ffd66a0baf432b338787cbdb8fef99e |
| product/runtime/execution_proof.py | f1434d5eddc444e7ec94de7a9b2047913575342321e16ce51faf3b717594c03d |
| product/runtime/run_package.py | 2943055e13bebbb90c0b85ade794e69ace9647b52f3cb57218c376a6cae75e89 |
| product/runtime/nested_codex.py | 0741f81cc08560276a3d619441ce16c6b0fe25d3322bd3b469787154d87e0e51 |
| product/runtime/smoke_prompt.py | 4044f7c77c9e16a7e3258f9d0314cd80fe57987ef78078b17c5c89279021a55d |
| product/runtime/runtime_eval.py | 6c967e705e397da1335972f124707d740391d8baf8f12eccdcd411ab20f78d53 |
| tests/test_native_output_handoff.py | f6506466293709fbcd089d2f156732173a3b8c897ee091675865e2419e1e69a6 |
| tests/test_native_execution_proof.py | 79e9788a676e22074c145f721e65b219942003c670a848b4a519867b9a6673dc |
| tests/test_specialist_start_context.py | e64192645e1a62e35c5167975238879840504192eacf8e892862616afd6caad2 |

此表仅为相关文件字节标识，不宣称全工作区快照或新的产品版本锁。工作区其他既有修改保留。

## 尚未完成

当前21/24任务。新源码尚未通过插件刷新及同一候选锁下的真实三股/语义验收；已安装的 `0.3.0+codex.20260910180624` 仍属于上一轮源码，不能冒充本轮加载证明。上一轮 NVDA 成功只证明其原锁，AAPL/MSFT 失败不改记成功。5.3、5.4独立复核、5.5人工完成批准继续未完成，全进程隔离 UNVERIFIED。未归档、提交、推送。
