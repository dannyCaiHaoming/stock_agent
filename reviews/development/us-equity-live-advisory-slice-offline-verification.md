# 美股 live 切片：限定离线验收归集

日期：2026-09-10。对应 `us-equity-live-advisory-slice` Task 4.2、5.1；不是独立复核、真实研究或 Change 完成批准。

## 源码、输入和执行证据

- 基线：`e512a6364e1a7f52dc25f715d8edae76229bc279`。
- 候选声明：`0.3.0-candidate.2-live`；版本文件 SHA-256：`ef54acedf275d2cf7d63ae6377c0a2eeb9cc4d7367fff9b74df23fa51196c7a3`。
- live profile SHA-256：`c57ba9e9666a024d2cf55138e1113e25754ed06a3edadc1b1f4b456e63cec45c`。
- 既有 73 文件清单：[phase-3](../../docs/data/live-offline-phase-3.sha256)，清单 SHA-256：`1398443cebf089f805d7fcf8a79a5616590c3adfb9bfe7515f6f6ba4ebf38558`。本轮实际逐项重验，73 项全部一致。
- 本轮唯一新增测试：[test_live_eval_contract.py](../../tests/test_live_eval_contract.py)，SHA-256：`c5e6dbaf09e627bc145844101c924c2e3fdfcb0432cf697c060b73c0a736ba3a`。无产品源码、入口、角色指令或依赖变更。
- 依赖锁：[requirements-live-macos-py313.lock](../../requirements-live-macos-py313.lock)，SHA-256：`47e6aefe5fd91a2f36d3fd7bdb46d7494e5be9ce4245b28fdb61edf7798d1b86`。使用上一阶段相同外置 venv，不安装新依赖。
- 执行标识：`us-equity-live-offline-eval-2026-09-10`。[命令及实际返回结果](us-equity-live-offline-eval-test-results.json)，SHA-256：`2f1b23bb7f62551ed08b235766b4a704454539314f0593c3df9dc0f9d7e8d951`。这是工具返回结果归集，不是独立执行事件证明。

基线＋phase-3 清单＋新增测试 hash 界定本次测试输入代码。合成行情、两期财务、披露、组合、角色输出及评分替身定义在这些文件中；不含真实持仓或数据授权。每个案例在独立临时目录生成实际 Gate、专业/CIO 结构、Risk、Trace 和 Eval 产物，测试结束后清理；本记录不声称保留了可重放的真实运行包。

## 受影响范围与测试结果

| 规格 / Tasks | 本次验证或复用证据 | 结论与证明边界 |
| --- | --- | --- |
| advisory-decision-output：安全与研究分开；4.2 | 新增 4 项测试，代表性样例包含具体 NO_TRADE、空泛 NO_TRADE、HOLD、TRIM；读取实际运行生成的 Gate/CIO/组合和绑定 hash | PASS：native 成功只得到 `RUNTIME_SAFE_RESEARCH_UNASSESSED`；没有评分不能 finalize；替身语义 FAIL 传播为 FAIL，不因安全通过而覆盖 |
| advisory-decision-output：引用/风险；4.2 | 专业报告真正注入 `missing` ID；另在临时正常运行移除 `risk/check-1.json` | PASS：未知引用在专业验证失败，不发布 decision；正常验收预期下 Eval FAIL。缺 Risk 实体文件在创建语义输入前拒绝，不只篡改摘要 |
| advisory-decision-output：评分血缘；4.2 | 错误 grader input hash（即使重算输出 hash）被拒绝；实际 finalize/verify、嵌套 `eval/result.json` 和 `eval/report.md` 验证 | PASS：评分与被测输入绑定；phase-3 已有 rubric 错配测试继续通过 |
| live-us-equity-data；1.2–1.3、2.1–2.5 | 105 项 `test_live_*.py` 全部通过；身份、时间、缓存、预算、可比期间、集合采集等覆盖见 phase-3 记录 | PASS：确定性实现；未证明 Yahoo/SEC 网络访问或来源许可 |
| portfolio-council-orchestration；3.1–3.5 | 同一 105 项包含 source/profile、输入、MCP、Risk、批次、宿主替身接缝 | PASS：确定性接缝；未证明当前应用实际加载更新资源或真实 LLM 执行 |
| advisory-decision-output；4.1、4.3 | 同一 105 项包含中文渲染、金额/权重、NO_TRADE null、合成持仓 Schema 和宿主文档契约 | PASS：结构和展示；不是语义质量结论 |
| 5.1：限定验证 / Design 7.1、7.6 | 本轮聚焦 4 项、live 集合 105 项、strict validate、diff 检查 | PASS：只覆盖当前 Change 的离线验收，没有执行完整 Gate |

HOLD/TRIM 是合成 CIO 输入动作，不强制最终投资动作；测试实际执行 Risk，若要求修订则保留合成草案执行第二次确定性校验，允许风险终态否决。不能把替身评分的 PASS 称为真实有据 HOLD/TRIM 已通过研究验收。语义是否合格仍由 Task 5.2/5.3 的实际评分作业判断。

初次编写新测试时，合成披露缺少 `form` 被 Gate 排除，CIO 使用专业报告未引用的 price 被拒绝；补正测试输入后通过。另修正测试读取失败返回的字段。未放宽产品 Validator，也未把这些测试编写错误计作环境故障。

## 实际命令

工作目录为仓库根；临时目录显式允许写入，不创建嵌套沙箱。

```sh
env TMPDIR=/private/tmp /private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B -m unittest tests.test_live_eval_contract -v
env TMPDIR=/private/tmp /private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -q
shasum -a 256 -c docs/data/live-offline-phase-3.sha256
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

结果分别为：4 tests OK（代表性一项含四个子场景）；105 tests OK；73 个 hash 一致；strict valid；diff 无错误。退出码全部 0。没有跳过 live 可选日历测试。

## 旧证据适用表

| 旧证据 | 本次处理 | 适用理由 / 限制 |
| --- | --- | --- |
| [阶段三](../../docs/data/live-integration-progress.md) 的 101 live tests | 本轮 105 项重新执行覆盖并扩充 | 相同产品和依赖，新增 4 项 Eval 测试；不将历史次数累加成 206 项 |
| 阶段三 131 项 fixture/共享/Eval/旧入口测试 | 直接复用，不重复调用 | 本轮产品/旧测试/依赖 hash 全部不变，新增测试不被产品导入；只适用于该集合，不称全量测试 |
| [本地 SDK 契约](../../docs/data/live-sdk-contract.md) | 复用 | 相同锁定环境；静态源码端点检查不冒充真实请求或访问授权 |
| phase-2 与更早记录 | 仅保留历史 | 不用旧 hash 覆盖 phase-3，不新增其证明范围 |
| 旧 fixture Smoke、Replay、Ablation、Promotion | 不用于 live 正常能力验收 | 来源、输入和加载路径不同；不替代当前 live 实际研究 |

## 真正剩余任务和停止条件

- Task 1.1：Yahoo 按用户要求暂停，访问条件仍 `BLOCKED_PENDING_AUTHORIZATION`。不能填造 AUTHORIZED，也不自动更换源。
- Task 5.2：尚无真实单股采集＋当前资源加载＋独立 Analyst/Skeptic/CIO＋Risk＋实际语义评分。
- Task 5.3：尚无单股通过后的三股共享快照真实批次与逐股实际语义评分。
- Task 5.4：等上述底层证据齐全后做一次独立只读差异复核；目前不能宣称 PASS。
- Task 5.5：最终人工完成批准尚未取得，不归档、提交或推送。

Task 4.2、5.1 的确定性实现与离线验收完成不代表上述任务完成。当前不具备 Change 最终人工批准条件；不申请候选晋升。`ISOLATION: UNVERIFIED`，生产版本指针不变。
