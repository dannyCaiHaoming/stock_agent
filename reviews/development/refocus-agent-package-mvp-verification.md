# `refocus-on-agent-package-mvp` 限定验收记录

## 验收范围

本记录只验证 `DEMO_SCAFFOLD` 的 Agent Package 静态绑定、结构化输入输出、只读 Tool Port、固定数据流、PIT、Evidence Closure、deterministic Risk 和中文 Demo 报告。不证明真实 LLM、专业 Skill 推理、Codex Subagent、当前主线程 CIO、live 股票研究、Execution Replay、语义 Eval、Regression、Calibration、Ablation 或 Promotion。

暂停中的 `us-equity-live-advisory-slice` 仍为 21/24，Task 5.3、5.4、5.5 保持未完成；本 Change 未归档、回退或改写其实现与历史证据。

## 聚焦确定性测试

实际命令：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_agent_package_demo \
  tests.test_agent_package_demo_workflow \
  tests.test_native_evidence_gate \
  tests.test_native_decision_contract \
  tests.test_native_risk_runtime \
  tests.test_development_workflow \
  tests.test_governance
```

结果：67 项通过，0 项失败。覆盖 Tasks 1.1–3.4 与 4.1 声明的 Package 拓扑、Capability 五段映射、Demo Schema、Tool Port、角色独立性、Dispatch、PIT、Evidence Closure、三类终态、Risk、失败传播和默认入口。

执行过程中发现既有治理测试把 `dev_reviewer` 中文描述锁定为旧文案；已将该断言收敛为配置结构、注册路径和非空描述检查，不改变有效开发 Agent 配置或产品权限。

## 外置输入完整 Demo

输入不使用仓库内置路径直接运行，而是复制到新的外部路径后显式传入：

```bash
cp evals/fixtures/agent-package-demo/mvp-demo.json \
  /private/tmp/refocus-agent-package-mvp.HQFHVd/external-input.json

PYTHONDONTWRITEBYTECODE=1 python3 scripts/council-dev.py demo run \
  --repo . \
  --input /private/tmp/refocus-agent-package-mvp.HQFHVd/external-input.json \
  --output-dir /private/tmp/refocus-agent-package-mvp.HQFHVd/run
```

实际结果：

- `terminal_state=DEMO_COMPLETED`
- 三个独立响应：`runtime_company_analyst`、`runtime_skeptic`、`runtime_cio`
- 固定阶段：Input → Package Topology → PIT Gate → Specialist fan-out/fan-in → CIO → Risk → Decision → Report
- 最终示例动作：`HOLD`
- `llm_used=false`
- `skill_reasoning_executed=false`
- `real_subagents_started=false`
- `main_thread_cio_executed=false`
- `advanced_assurance_run=false`

关键产物 SHA-256：

| 产物 | SHA-256 |
|---|---|
| `external-input.json` | `8214c5a9d1e968166275f51c35114383e07c918468a3282c28cc676e4209106a` |
| `package-topology.json` | `03916f9ebf41449605c29ac041decc54c63e08f54955f175f40106128e707036` |
| `evidence/gate.json` | `029c90efd327ae2e87dfda91591cfda9a4304ef665d7986448fa26bf35884b1e` |
| Analyst Response | `5210c04138a419d9c1b1831699a15a046b91d72cbc1d80d1409e1d9491d1c4a6` |
| Skeptic Response | `2b8d58a6f0e71b749ff0ba5e636e54cec348536705e188acf06ac95bbcb39ced` |
| CIO Response | `7b3b40037bd390f925547a4b58c5e539ea0a51e1f67ed5cdea20d5baf219bead` |
| `dispatch/records.json` | `dbec2da52fff5aa7c4f7313e2ee401b0f0ed1ebeb3609be5d8395009044f8498` |
| `tools/events.json` | `e9160cd0cb5563db99c4805fddaa694483f45f4fe2f6101be843f5ad6fd023cc` |
| `risk/result.json` | `2a289bd65b31e127eef78519abc287703cd1de29653b69355463f7b0a7e433fb` |
| `decision.json` | `64e8a3d1f4ea048ce4782d4d0c88a460b3a43d122bfafae1f1b79618ab58c1f0` |
| `report.md` | `8eb6066c4fc148e8e36b3166fa318333421107892499f37879b1b4969ff05b24` |
| `demo_run.json` | `0153ea68156549e13a0086ca10907b5d0cb1994bd5c1e31c30210ad1546e7023` |

该证据覆盖 Task 4.2。合成 Thesis、反证、动作与置信度来自显式 fixture；Python 只做机械投影、结构校验、确定性计算、Risk 和渲染。

## OpenSpec 与格式

实际命令：

```bash
openspec validate refocus-on-agent-package-mvp --strict
git diff --check -- AGENTS.md PRODUCT.md docs/development/workflow.md \
  scripts/council-dev.py tests/test_governance.py \
  openspec/changes/refocus-on-agent-package-mvp
```

结果：OpenSpec strict validate 通过；相关已跟踪差异未发现空白错误。该结论覆盖 Task 4.3，但不扩大为真实产品或候选晋升结论。

## 完成边界

Tasks 1.1–4.3 已有实现与限定证据。

## 人工完成批准

2026-09-11，用户在收到 Demo 命令、产物路径、完成范围和保留限制后明确回复“批准”，授权将 Task 4.4 标记完成。

批准范围仅为 `refocus-on-agent-package-mvp` 的 Change 实现完成，不代表真实研究能力、Skill 推理、Codex Subagent、主线程 CIO、live 能力或 Promotion PASS，也不包含归档、Git 提交或推送授权。
