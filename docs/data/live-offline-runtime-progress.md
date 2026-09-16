# Live 离线运行接缝：阶段二证据

日期：2026-09-10。Change：`us-equity-live-advisory-slice`。范围：用户允许 Yahoo 保持暂停时继续其余实现；本阶段没有发送 Yahoo、SEC 或模型请求，没有启动产品 Smoke、Regression 或 Release Gate。没有重新安装应用插件、改生产指针、归档或 Git 发布。

## 被测版本

- 基线 HEAD：`e512a6364e1a7f52dc25f715d8edae76229bc279`。
- 当前候选声明：`0.3.0-candidate.2-live`；`product/version-manifest.json` SHA-256：`ef54acedf275d2cf7d63ae6377c0a2eeb9cc4d7367fff9b74df23fa51196c7a3`。
- live profile SHA-256：`c57ba9e9666a024d2cf55138e1113e25754ed06a3edadc1b1f4b456e63cec45c`。
- [增量源码/测试完整 hash 清单](live-offline-phase-2.sha256)：61 个新增或修改的产品、依赖、rubric、测试文件，清单 SHA-256：`f0a17c7c7d546617d8b67e463f1e9ce930be0ea0a3cdf57246599ffc3f828df3`。这是基线之上的被测增量，不冒充全仓库或生产发布锁；文档本身不包含在该清单中。
- 隔离依赖环境：`/private/tmp/stock-agent-live-deps.cBmS73/venv`；Python 3.13，yfinance 1.7.0，exchange-calendars 4.13.2。PyYAML 6.0.3 只用于开发 Skill/plugin 格式校验，不是产品 live 依赖。
- Skill 源码 `portfolio-council/3.1.0`，Analyst `2.2.0`、Skeptic `2.1.0`、CIO `3.1.0`。只证明源码/契约配置，不证明当前应用缓存或真实 Agent 已加载它们。

## 实际执行与结果

工作目录均为仓库根。以下为确定性测试，不是实际产品运行；临时测试输入为合成数据，测试目录退出后清理，不将其描述为可复查真实 LLM 包。

```sh
env TMPDIR=/private/tmp /private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -q
```

结果：83 tests，OK，exit 0。覆盖 SEC 解析/限定获取替身、缓存、日历、行情标准化、输入/身份/PIT、live profile/工具/运行包、报告、批次汇总与 CLI。真实 calendar 和已安装 SDK 签名检查没有访问 Provider。完整生命周期测试明确 `authenticity_required=False`；合成 Analyst/CIO 报告不得作为真实研究证据。批次成功路径的校验器替身仅证明调用与失败传播，不证明三股 LLM 通过。

```sh
env TMPDIR=/private/tmp python3 -B -m unittest tests.test_native_run_package tests.test_native_evidence_gate tests.test_native_invocation_validation tests.test_native_eval tests.test_native_trace tests.test_native_replay tests.test_runtime_eval_job tests.test_native_execution_proof tests.test_product_config tests.test_portfolio_council_skill -q
```

结果：91 tests，OK，exit 0。用于本次共享生命周期、锁、Prompt、Risk 与 Eval 接缝兼容，不是全量测试。标准输出中的 `proof-failure / NATIVE_EXECUTION_PROOF_FAILED` 是预期负向用例，不是一次真实失败 Smoke。新增二次 Risk 修订仍被否决的测试证明已持久化结果及 Trace hash 不被终态处理改写。

```sh
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

结果分别为 `is valid` / exit 0。格式与规划校验不代表实现全部完成。

补充已执行：现有 Skill 的 `quick_validate.py` 与 plugin 的 `validate_plugin.py` 在上述隔离 Python 下通过。第一次使用基础 Python 时缺 PyYAML，随后仅在临时依赖环境安装后验证；没有以失败命令充当 PASS。早先执行证明测试遇到 `/var` 与 `/private/var` 临时路径别名绑定差异，显式 `TMPDIR=/private/tmp` 后通过；未放宽路径校验。

## Task 映射与证据边界

| Task | 当前实现/证据 | 仍未覆盖 |
| --- | --- | --- |
| 1.1/1.2 | 来源记录、可选安装锁、真实本地 SDK 参数及日历 | Yahoo 准入与实际端点；不启动访问核对 |
| 1.3 | 五类 Schema，完整组合、有限数值、目标/身份正负测试 | 本任务离线契约已完成，不证明真实证券身份 |
| 2.1/2.4 | Yahoo 日线合成标准化、去重增量缓存；SEC 有预算/有限重试 | Yahoo 必要身份数据、完整受限请求传输及集成采集仍未完成 |
| 2.2/2.3 | SEC 分页/财务/指定披露与固定片段、可比计算 | 已完成局部实施；真实网络材料仍属于 5.2/5.3 |
| 2.5/3.1 | 冻结包→原文字节/hash→calendar/PIT→source-aware prepare/Trace/replay/Eval；原 fixture 分支兼容 | 从实际采集完成到冻结的全入口；不扩大为 Execution Replay 保证 |
| 3.2 | 既有 Skill/三角色指令和 live MCP；未知/跨 run/跨 invocation 引用拒绝，本地 stdio 工具协议通过 | 更新资源的实际宿主/LLM 加载证明；原有缓存不当作新版证据 |
| 3.3 | Gate 重验后全组合估值，价格证据绑定，缺价/未来/成本/伪 Gate 拒绝；复用实际 Risk Engine | 真实行情质量与实际运行另验；不放宽行业/流动性未知的风险约束 |
| 3.4 | 唯一批次 IDs、共享完整组合与 cutoff、显式 focus、子失败保留及汇总校验 | 宿主逐子运行执行与完整三股实际验收 |
| 3.5 | 内部 `prepare-live` 参数、失败传播、自检禁止隐式启动；可复用既有 prepared-run | 自动采集的宿主 `--profile/--portfolio` 入口尚未完成；本阶段未修改宿主脚本 |
| 4.1/4.2 | 中文结构渲染/闭包/NO_TRADE、live rubric 与真实产物评分输入绑定；运行安全分类单列 | 样例语义评分及真实研究质量尚未验证，不给空泛 NO_TRADE 研究 PASS |
| 4.3 | 开发状态使用说明及合成输入 Schema 校验 | 自动取数入口完成后的最终用法与隐私检查收尾 |
| 5.1 | 本阶段受影响测试、strict validate 与增量 hash | 并非完整 Change 的最终限定验收记录 |
| 5.2–5.5 | 无本阶段可替代证据 | 真实单股、三股、实际语义 Eval、独立复核、人工完成批准 |

`live-contracts-progress.md` 中 68 项及当时 hash 是前一阶段证据，不冒充本次新版锁。历史 fixture/Replay 证据只适用于未变部分；当前共享实现以本次对应测试为准，旧真实 normal 不证明新版 live 研究或加载。

## 当前结论

阶段离线接缝测试通过；**Change 未完成、未具备最终人工完成批准条件**。Yahoo 暂停与来源准入是一类外部阻断；集成采集/宿主自动入口/批次执行尚未完工是实施缺口，二者不能混为一谈。不得把所有剩余工作都归因于用户配置或 Yahoo 暂停。

`ISOLATION: UNVERIFIED`。本阶段不要求用户调整网络、沙箱或 Shadowrocket。恢复 Yahoo 需另获明确指示并满足原准入条件；不自行恢复，也不因此擅自换源或扩大平台建设。
