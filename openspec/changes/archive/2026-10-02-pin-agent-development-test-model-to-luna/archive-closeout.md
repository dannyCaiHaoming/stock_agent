# Luna 开发测试默认模型：验收与发布收尾

日期：2026-10-02（Asia/Shanghai）。用户明确要求“把收尾事项也处理了？主规格的Terra也要改成gpt-6-luna”，接续本会话对本 Change 的同步归档讨论，批准按既定范围完成同步、归档及限定提交推送。最终状态：**COMPLETED / SYNCED / ARCHIVED / PUSHED**，任务5/5。Task3.1 已在实际推送核实后勾选。

## 范围与规格

仅将普通股、多维研究、独立反证的产品 Agent 开发测试默认模型固定为 `gpt-6-luna`。主规格 `codex-development-environment` 的一条 MODIFIED requirement 完整同步，原其它要求、Purpose 和四个既有场景保留，并增加未显式选模场景。候选、fixture、历史运行、`runtime_repeated` 和独立评分保持各自锁；根开发主会话及权限配置不改。predecision CIO 不属于这三个默认入口，不把已归档 CIO 原批准的 Terra 验收记录重写为 Luna。

模型常量、显式可选值及宿主默认分支已由前序相关实现发布，本次复用而不重复提交：基线 `40d48d6eadc3ff4e6e55ff24fc3c064b8fa45a57`，其中模型选择代码于 `05905dcd0f136bbce3a8d460d26d4aad38a3958e` 已存在。当前 HEAD 的相关字节 SHA-256 为：

| 对象 | SHA-256 |
|---|---|
| product/runtime/model_routing.py | 2ffd57757625376ef0d903caac7809e2bd4e56a9d0cfde8d5355ca600b1eb896 |
| scripts/run-product-smoke.sh（已发布版本） | 6dda8e238fbb909ba8cec158f3592f682c3075511ecf50526d19e705e75aef2e |
| product/model-routing.json | abb5243c1894d5cfd4f6f391c2ae4e5dab2d4580c00fefb1354436b1c56ac8b5 |
| .codex/agents/dev_eval.toml | d70b07d3ac8cb895496e4444d1256b5b1755773af75b29724e1555f4abf06283 |

## 实际验证及证据适用性

限定候选树 `b6fab4a3c3843d02aa8ae8d2e20d377a839cdcf0`（添加本收尾文档之前），从仓库外 Git 导出执行，不替换原工作区。本次命令：

```text
env PYTHONDONTWRITEBYTECODE=1 /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -B -m unittest tests.test_development_environment.ModelConfigurationTests tests.test_host_proxy_scripts.HostProxyTests.test_research_prepare_defaults_to_pinned_luna_without_model_call tests.test_host_proxy_scripts.HostProxyTests.test_multidimensional_and_counter_prepare_default_to_luna -q
```

实际5项通过，1.846s。验证三个入口准备参数的 Luna 默认值、开发测试与候选/Eval隔离；另实际直接检查显式 Terra 覆盖及未知模型 `PRODUCT_RUNTIME_MODEL_UNSUPPORTED` 拒绝。脚本语法通过，delta整条块与main精确匹配。Change strict、21项主规格strict通过、0失败。本次没有产品模型、Smoke、Eval、Replay、Regression、Ablation 或 Promotion 调用。参数包装测试只证明准备/传递，不冒称真实运行。

真实加载佐证复用原八维已独立通过的批次，不启动新运行、不重签原锁：外置 `eight-dimension-readable-results-20261001.wN788G/run`，run_id=`eight-dimension-readable-results-824833ae-747e-49a4-8ec3-c8df42d7ea51`。只读重验以下原件：

| 原件 | 字节 SHA-256 | 本次只读核对 |
|---|---|---|
| run_manifest.json | 2ba09184c9bb55b5591076bcac79b283c757da70a8ec20c6fb50aed5892656d6 | model=gpt-6-luna |
| invocation/subagent-events.jsonl | cb6e294e31266ad6dca0d8b15259c8c2ed64a6d343aec43edb644ad0b09d7a0f | 8个实际SubagentStart均为gpt-6-luna |
| invocation/process-result.json | 8a9e2f5f643a69fe4c8d5d095d9ce8ecf99a605423bb4d08ea784a427753a58f | process_exit_code=0、stage_status=PASSED、timed_out=false |

这证明当时配置实际进入真实研究，不保证当前账户模型永远可用，不构成新的 Company/Skeptic/CIO 完整链或模型质量对照。原具体内容8/8及限制见 `../2026-10-01-complete-eight-dimension-source-consumption/resume-review-20261001.md`（归档后相对路径）。原件保留在用户授权的仓库外 acceptance-runs，不复制私人转录。

## 限定发布与未纳入内容

仅提交主规格、两份模型说明、两份对应测试和本 Change 归档。宿主模型选择实现已发布，宿主工作区当前剩余 Tiger 和 `--question` 差异不属于本 Change，不再次纳入。共享 host-proxy 测试只取 Luna 默认准备检查，剥离其它需求的 `--question` 参数和断言；工作区原稿不改。Tiger、交易复盘、其它活跃 Change、本地模型/权限及所有其它用户修改保留。

独立 Reviewer `/root/macro_binding_admission_review` 对上述限定候选只读复核 PASS：10路径范围、delta/main完整一致、三个默认入口与显式选择/拒绝、候选/Eval/root隔离均核实；独立读取三份原真运行文件，确认8个Start全为Luna。Reviewer没有编辑、测试或新产品调用。Task2.1复用原已归档CIO设计的Luna默认及当时另行批准的Terra验收，不重写历史。

`CHANGE_REVIEW: PASS`。已实际归档至 `openspec/changes/archive/2026-10-02-pin-agent-development-test-model-to-luna/`，主规格同步及11路径限定提交为 `eba72863733121473c3bfc301679cd866987eebc`，已成功推送至 `https://github.com/dannyCaiHaoming/stock_agent.git` 的 `main`；实际远端 `refs/heads/main` 已核对与提交一致。提交前限定候选实现/测试字节与已验证版本相同，范围敏感信息检查未命中，归档后21项主规格严格校验通过。

本页和任务勾选的最终发布状态补记单独作文档收尾提交，不把该提交自身hash写入自身。其余用户修改仍留在工作区，未整体暂存或回退。`CANDIDATE_PROMOTION: NOT_RUN`，不把 Change 发布等同于产品晋升或新的模型效果验收。
