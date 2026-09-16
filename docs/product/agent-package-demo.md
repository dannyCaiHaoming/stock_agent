# Agent Package Milestone 0：零 LLM 装配 Demo

本 Demo 用合成 Portfolio 和 Evidence 展示固定数据流：

```text
Demo Input
  → point-in-time Evidence Gate
  → Company Analyst Demo Adapter ┐
  → Independent Skeptic Demo Adapter ┘
  → CIO Demo Adapter
  → deterministic Risk Engine
  → decision.json + report.md + demo_run.json
```

它会静态核对仓库实际 Plugin manifest、`portfolio-council` Skill、三个角色定义、专业 Skills、fixture MCP、输出 Schema 和 Risk 契约。静态绑定通过只表示 `binding_verified=true`；运行始终记录 `llm_used=false`、`skill_reasoning_executed=false`、`real_subagents_started=false` 和 `main_thread_cio_executed=false`。

## 完整 Demo

输出目录必须不存在：

```bash
python3 scripts/council-dev.py demo run \
  --repo . \
  --input evals/fixtures/agent-package-demo/mvp-demo.json \
  --output-dir /private/tmp/portfolio-council-demo
```

成功后按顺序查看：

- `input.json`
- `package-topology.json`
- `evidence/gate.json`
- `agents/requests/*.json`
- `agents/responses/*.json`
- `dispatch/records.json`
- `tools/events.json`
- `risk/result.json`
- `decision.json`
- `report.md`
- `demo_run.json`

## 三个角色单独调用

三个命令使用与完整链路相同的 Request/Response 契约。先运行两个 Specialist，再把它们未经改写的响应交给 CIO：

```bash
python3 scripts/council-dev.py demo agent \
  --repo . --input evals/fixtures/agent-package-demo/mvp-demo.json \
  --agent runtime_company_analyst --output /private/tmp/demo-analyst.json

python3 scripts/council-dev.py demo agent \
  --repo . --input evals/fixtures/agent-package-demo/mvp-demo.json \
  --agent runtime_skeptic --output /private/tmp/demo-skeptic.json

python3 scripts/council-dev.py demo agent \
  --repo . --input evals/fixtures/agent-package-demo/mvp-demo.json \
  --agent runtime_cio --output /private/tmp/demo-cio.json \
  --analyst-response /private/tmp/demo-analyst.json \
  --skeptic-response /private/tmp/demo-skeptic.json
```

## 边界

- 不访问网络、真实行情 Provider、券商或账户。
- 不启动 nested Codex、真实 LLM、Codex Subagent 或主线程 CIO。
- 不执行 Runtime Eval、Replay、Regression、Calibration、Ablation 或 Promotion。
- 合成 fixture 中的 Thesis、反证、动作和置信度仅用于演示传递；Python 不根据证券或指标生成投资判断。
- 真实 fixture/live 产品链路失败时不得回退到 Demo。
