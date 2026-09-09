## 1. 封闭底层绕过与退役入口

- [x] 1.1 删除 `nested_codex.py` 的自动沙箱绕过分支，令 `externally_sandboxed=True` 和非空 `preflight_report` 明确失败；更新 `tests/test_nested_codex_launcher.py`，以默认/False 命令等价、原生参数保留、True 拒绝及未读取输入/未创建运行目录/未调用子进程的断言验证，不能只删除旧测试。
- [x] 1.2 在 `scripts/council-dev.py` 和底层 CLI 一致拒绝旧 review、environment-preflight、permission-probe、nested-codex-probe 及 `--preflight-report` 两种拼写；退役旧直接执行函数和 `restricted_main`，保留现用纯路径函数。以 `tests/test_development_environment.py` / `tests/test_host_proxy_scripts.py` 中参数化接缝测试验证各调用层均返回明确失败、无旧执行副作用，正常路径及失败传播不变。

## 2. 同步根入口与清理无效配置

- [x] 2.1 更新根 `AGENTS.md` 的三类入口说明，保留开发/产品角色、业务安全及发布边界；若环境文档或诊断 Skill 有旧入口建议，仅改对应说明。以根指令检查和差异复核确认没有把底层命令作为真实运行默认入口，没有新增探针或自动启动要求。
- [x] 2.2 只移除根 `.codex/config.toml` 的废弃 project-edit 域名表；用 TOML 语义测试对照基线，验证原生 workspace-write、对应网络设置、模型与 Agent 注册不变，未新增权限框架或更改代理配置。

## 3. 限定接缝验证与证据

- [x] 3.1 仅运行上述受影响确定性测试和 `openspec validate retire-legacy-sandbox-paths --strict`，在 `reviews/development/retire-legacy-sandbox-paths-verification.md` 记录实际命令、测试选择、结果、源码快照及涉及文件完整 hash；覆盖拒绝前无副作用、自检白名单、正常参数保留和失败传播，注明测试不证明模型实际加载或全进程隔离。
- [x] 3.2 按既有启动/加载验收规则，接缝通过后提供现有宿主 normal Smoke 命令并停止等待用户执行或另行授权；收到一次修复后运行证据后核对 invocation 原生参数、AGENTS/Skill/Agent/MCP/Hook 加载、终态及既有完成产物，记录 run_id、版本和完整 hash。不得自动启动、复用旧 normal 冒充新源码执行或扩大为全量 Gate；若用户要求最终完全零 LLM 验收，先获明确范围调整批准并同步规划，此前本项保持未完成。 完成证据：`reviews/development/retire-legacy-sandbox-paths-normal-smoke.md`。

## 4. 差异复核与人工完成批准

- [x] 4.1 独立 Reviewer 只读本次源码/配置差异、调整后规格和底层接缝及宿主证据，生成 `reviews/development/retire-legacy-sandbox-paths-independent-review.md`，注明完整快照、证据标识及逐项结论；不重跑产品、Replay、Regression、Calibration、Ablation 或 Gate，不将全进程隔离 `UNVERIFIED` 改成 PASS。 完成证据：`reviews/development/retire-legacy-sandbox-paths-independent-review.md`，SHA-256 `3014ed6127d8e8b48e04e427c9af1814206d9177e2b97df4016f8e2c4b4f3c90`。
- [x] 4.2 提交限定完成摘要供人工批准，并将明确批准及关联报告 hash 保存到 `reviews/development/retire-legacy-sandbox-paths-approval.md`；批准前不勾选本项、不归档、不提交或推送，不将 Change 完成解释为候选晋升。完成证据：用户于 2026-09-09 明确批准，记录见上述批准文件；`CANDIDATE_PROMOTION: NOT_PROMOTABLE`、`ISOLATION: UNVERIFIED` 不变。
