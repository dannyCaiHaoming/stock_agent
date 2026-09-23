# 独立反证阶段实施与验收记录（2026-09-23 至 2026-09-24）

本记录对应 `activate-independent-skeptic-for-multidimensional-research`。范围止于同一 point-in-time 运行内的正向多维研究、逐普通股 Independent Skeptic 和正反研究交接；没有 CIO、Risk、交易、Outcome、Runtime Eval、Execution Replay、Regression、Ablation 或 Candidate Promotion。2026-09-24 已获得人工同步归档批准。

## 实现结果

- 新增显式 `INDEPENDENT_COUNTER_THESIS_RESEARCH` stage；原 `MULTI_DIMENSIONAL_HOLDING_RESEARCH` 继续止于正向研究，不自动启动 Skeptic。
- 新增版本锁定的 `CounterThesisReport/2.1.0` 与 `PreDecisionResearchPackage/1.0.0`，逐证券保存输入、Invocation、dispatch、执行证明、JSON/中文正文和最终交接引用；旧 2.0.0 报告仍可按原版本读取。
- 第一轮 Skeptic 输入采用字段白名单，只从同次 Gate 构造目标公司、共享 Macro/Market、已冻结同行关系和来源闭合计算的允许集合；拒绝正向报告、bundle、摘要、未解决问题、hash、Artifact References、Agent/CIO 结论及私人持仓金额、成本、数量或现金。
- 只读工具按可信 `(run_id, task_name, invocation_id, security_id)` 映射授权；最终报告引用不仅要属于允许集合，还必须由同一可信 Invocation 实际查询。执行证明保存实际查询 ID。
- 可信 dispatch、Start 与最终 Stop 绑定用于区分“任务已结束”和“报告成功”。唯一映射可封装模型遗漏的技术身份，冲突或多义绑定拒绝；原始草案保留。失败任务会释放并发槽位，全部任务终止或依赖阻塞后有限收尾。
- Macro/Market 已区分单股和多股提示：单股解释本证券敏感性、假设与反向情景，多股才比较持仓差异。Evidence 只接受完整精确 ID，不作模糊纠错、截断恢复或删主张凑通过。
- 同一冻结运行的显式恢复使用独立 attempt/Invocation，保留失败产物和采用记录；输入、Gate 或版本变化要求新运行。没有新增自动研究重试、补查询再提交机制、Agent 或第二套编排器。

## 确定性验证

最终聚焦集合覆盖独立反证阶段、多维阶段、正向/反向契约、Invocation 隔离、Hook、宿主入口、版本锁、资料准备、旧阶段回归和治理边界：

```text
TMPDIR=/private/tmp python3 -m unittest \
  tests.test_independent_skeptic_stage tests.test_multidimensional_stage \
  tests.test_multidimensional_research_contracts tests.test_common_stock_research_contracts \
  tests.test_native_invocation_validation tests.test_product_config \
  tests.test_research_input_topology tests.test_research_materials_stage \
  tests.test_governance tests.test_host_proxy_scripts tests.test_live_host_entry \
  tests.test_native_evidence_gate tests.test_live_contracts_gate \
  tests.test_nested_codex_launcher tests.test_multidimensional_schedule
Ran 323 tests — OK (skipped=1)

openspec validate activate-independent-skeptic-for-multidimensional-research --strict
valid

bash -n scripts/run-product-smoke.sh
通过

python3 -m py_compile product/runtime/codex_hook_recorder.py \
  product/runtime/multidimensional_stage.py product/runtime/independent_skeptic_stage.py
通过

git diff --check
通过
```

一次未设置 `TMPDIR` 的 macOS 临时目录测试因 `/var` 与 `/private/var` 路径归一化保护失败；在仓库规定的 `/private/tmp` 外置目录重跑全部通过。该结果属于环境路径保护，不是产品断言失败。

新增回归覆盖包括：缺技术身份的可信封装、显式冲突拒绝、StopBlocked 不提前终止、失败释放槽位、单股/多股提示、精确 Evidence ID、所引证据必须实际查询、同行全部未物化时禁止同行 claims、attempt 10+ 路径、不 mock `validate_forward_gate` 的正向包到 Skeptic 集成、核心 `FAILED/TIMEOUT/NOT_RESEARCHED` 阻断和合法 `SOURCE_LIMITED` 接受。

## MRVL 宿主纵向沿革

所有运行目录均位于 `/private/tmp`，未把私人 Handoff、原始数据或会话写入仓库。模型运行只经 `scripts/run-product-smoke.sh` 宿主入口；只读来源为 SEC、Yahoo 和 Moomoo SG。

| 目录 | 决定性结果 | 处理结论 |
| --- | --- | --- |
| `activate-independent-skeptic-mrvl-20260923-v1` | 系统 Python 缺少锁定 `certifi`，Company 0 任务 | 未启动模型；环境失败 |
| `...-v2` | 仓库外旧 Memory 的 raw closure repair 未完成 | 未启动模型；旧缓存不改写 |
| `...-v3` | 新 Memory 冻结成功，基础 preparation 因扩展 Gate 精确相等检查失败 | 未启动模型；修正 Gate 子集契约 |
| `...-v4` | Company 完成；正向 bundle 内 Macro/Options 实际失败 | Skeptic 门禁正确拒绝，未拼接历史结果 |
| `...-v5` | 8 个 Stop 中 5 个保存、3 个失败，父进程仍等待到超时 | 暴露终止识别、身份封装与精确引用问题 |
| `...-v6` | 数据冻结完成，宿主 PATH 未包含 Codex 可执行文件 | 模型未启动；环境失败 |
| `...-v7` | Codex app-server 初始化受宿主沙箱拒绝 | 模型未启动；按授权从宿主重跑 |
| `...-v8` | 正向 7/8；Industry 在同行均未物化时仍输出 claim，精确引用校验拒绝 | 父流程已有限收尾；一次目标恢复保留原失败，但同样失败，随后修正规则并按版本变化新建运行 |
| `activate-independent-skeptic-mrvl-20260924-v9` | 正向 8/8 合法，Skeptic 实际查询并生成合法报告，交接包 `DOWNSTREAM_READY` | 作为最终真实纵向验收证据 |

v9 使用全新 run `host-common-stock-e23531ee-571d-44ee-b974-e5a426b36171`。Company 为 `LOW_CONFIDENCE`，Technical 为 `COMPLETE`，Fundamental/Event 与 Industry 为 `INSUFFICIENT_EVIDENCE`，Macro 为 `LOW_CONFIDENCE`，Market 为具有实际 SPY 20/60 日计算和 VIX/ETF 代理事实的 `SOURCE_LIMITED`。这些核心报告均不是 `FAILED`、`TIMEOUT`、`NOT_RESEARCHED` 或依赖阻塞。同行身份仍因 `SEC_YAHOO_EXCHANGE_CONFLICT` 未物化；Industry 输入据此将 `claims.maxItems=0` 并合法保留资料不足，而不是虚构同行事实。一次公开研报材料获取失败属于非核心专项资料缺口，没有被冒充完成。

Skeptic 通过新的宿主显式入口从该同次正向运行准备并启动，产生 1 个 Start、1 个 Stop、1 份 `LOW_CONFIDENCE` 报告和 4 次非空 Gate-scoped 查询。报告的 2 个 Evidence ID 均属于该 Invocation 的实际查询集合。最终交接：

```text
consumability=DOWNSTREAM_READY
complete_portfolio_decision=false
coverage[US:COMMON_STOCK:MRVL]=READY
package_hash=104597b5956aef80ab9609dbf5a074e63df2f0a2a2f617ed49be085045360a26
```

文件 SHA-256：

| 产物 | SHA-256 |
| --- | --- |
| `research/holding-research-bundle.json` | `513608204d9361d0943341fd09f0caecb568d2d33c8a9e3c4a5388a9d85618c8` |
| `research/skeptic/dispatch-index.json` | `02b854aa97160ea7eeb0dd6aa7453417052540b3b46e2098ef515011d3053d20` |
| `research/skeptic/execution-proof.json` | `53bf5707caee8da7d0557751c588215658070e7364dd1aa1225bdfba8124d9e8` |
| `research/skeptic/pre-decision-research-package.json` | `deb67f02e842a94a99df693a257da68d83ed020c9ee92bf64bd2f01054d937cb` |
| `research/skeptic/reports/661d623066c1fc31375b969a/counter-thesis.json` | `8c15c9a4f61eb4fa2cd632b558c4e70d5cae3eac54947aa7259776a6cf7ba3d7` |
| `research/skeptic/reports/661d623066c1fc31375b969a/counter-thesis.md` | `35e9b88e7544113f70566f2d3adfda465f0d43ecae71d7ef643d4696bc46ff24` |

运行目录中没有 `decision.json`、Risk、CIO、Outcome、Replay 或回测产物；manifest 保持 `complete_portfolio_decision=false`，没有启动下游阶段。

## MRVL 反证正文人工复核

内容复核对照同次 Gate 中实际查询的 SEC 10-K/10-Q Evidence，而不是仅看 Schema 或工具计数。结论如下：

- 三条挑战均为 MRVL 特定：FY2026 数据中心收入 61.003 亿美元、占比 74% 与客户/design-win 集中；先进制程/TSMC、贸易限制和客户自研替代；Celestial AI/XConn 收购整合、现金、股份及或有对价。
- 事实性表述均引用同一 Invocation 实际查询的完整 Evidence ID；没有把风险披露误写为风险已经发生。报告明确说明风险披露不能证明发生概率或幅度。
- 客户集中、供应与替代传导、收购执行分别定义为报告内假设，challenge 引用闭合；没有用假设冒充事实。
- 每条挑战都说明了收入、毛利、份额、现金支出或摊薄的传导路径，并列出可获得的解决证据；失效条件为可观察的客户集中、供给/许可/份额、收购贡献和或有对价进展。
- 报告诚实保留关键客户/order、供应与替代、收购贡献以及同行未物化缺口；`LOW_CONFIDENCE` 与证据边界一致，没有输出投资动作。

内容复核未发现空泛挑战、无依据事实、隐藏假设或不可检验的推翻条件；`5.3a` 通过。

## 只读 Change 复核

在实施结束后以只读方式重新核对 Proposal、Design、三个 delta spec、任务清单、范围内源码与测试、v9 底层输入/dispatch/查询/报告/执行证明/交接包及 v1–v8 失败分类。复核结论：

- 新旧阶段边界、同 run/cutoff/Gate/hash 绑定、第一轮隔离、逐 Invocation 工具权限、Evidence 查询闭合、恢复不覆盖和正反交接语义均有对应实现与聚焦测试。
- v9 是版本变化后的新运行；没有用 v2/v4/v8 的报告拼接成功结果。失败状态、来源限制和未物化同行均原样保留。
- `SOURCE_LIMITED` 仅在有合法核心报告和实际计算时被门禁接受；`FAILED`、`TIMEOUT`、`NOT_RESEARCHED` 和依赖阻塞仍 fail closed。
- 没有新增 Agent、自动语义评分、第二套编排器、补查询再提交、自动研究重试、CIO/Risk 或网页扩建；设计保持在当前纵向切片内。
- 暂停中的 Tiger 只读接入改动仍存在于同一 dirty worktree，属于另一个 OpenSpec Change。本 Change 没有删除、覆盖或把这些文件计入验收；归档/提交前必须按范围分离审阅。

未发现阻断本 Change 的范围内缺陷。

`CHANGE_REVIEW: PASS`

该结论只表示本 Change 的规格与实现验收通过，不表示 Candidate Promotion。2026-09-24 人工完成批准后，三个 delta spec 已同步至主规格；归档提交继续按 Change 范围隔离暂停中的 Tiger 改动。
