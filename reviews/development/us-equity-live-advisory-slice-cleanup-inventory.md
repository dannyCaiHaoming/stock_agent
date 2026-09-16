# `us-equity-live-advisory-slice` 收缩清单与验收映射

日期：2026-09-16
范围：仅收缩美股真实数据基础与旧 live Council 入口，不扩建 Agent、数据源、沙箱或评测平台。

## 当前产品边界

- 权威用户输入：已确认 `PortfolioHandoff v3`。
- 本 Change 输出：内部普通股采集请求、逐证券冻结 snapshot、整批 `source-bundle.json`、PIT Gate 和 `data-preparation.json`。
- 本 Change 不输出：Thesis、投资动作、CIO 决策、Risk 结果或语义 Eval 结论。
- 数量约束：无三股产品上限；受请求、时间、并发和成本预算约束，未执行项必须显式记录。

## 已删除

| 目标 | 删除理由 | 消费者处理 |
| --- | --- | --- |
| `product/runtime/live_batch.py` | 只服务旧逐股 batch 入口，与当前 Handoff 数据准备边界重叠 | 同步移除 CLI、host 路由和专属测试 |
| `product.runtime.live_input.plan_live_batch` | 仅被上述 batch 实现/测试调用 | 无保留的现行消费者 |
| `prepare-live-batch` / `launch-live-batch` / `summarize-live-batch` CLI | 旧三股完整 Council 路径 | 命令不再注册，无法启动模型 |
| host `--profile live-us-equity --portfolio ...` | 绕过当前 `PortfolioHandoff v3` 入口 | 在代理检测、取数或模型前返回 `LIVE_COUNCIL_ENTRY_RETIRED` |
| `tests/test_live_batch_execution.py` 及 batch 专属断言 | 只验证已退役行为 | 保留非 batch 的冻结、Gate、引用与下游消费测试 |

## 明确保留

| 目标 | 现行/历史消费者 | 保留理由 |
| --- | --- | --- |
| `product/runtime/live_input.py` 的 `load_live_portfolio` 与 `freeze_snapshot` | `product/mcp/live/collection.py` | 当前真实数据采集必需 |
| `value_portfolio` / `build_live_specialist_inputs` | `run_package.py`、`native_eval.py`、`risk_runtime.py`、`live_report.py` 及历史运行包验证 | 直接删除会破坏历史读取和共享确定性验证；不再暴露为新产品入口 |
| `prepare-live` 内部 CLI、`profiles/live-us-equity.json`、`references/live-us-equity.md` | 历史冻结运行包、discovery、invocation、smoke prompt 与相关校验 | 作为历史/内部兼容读取，不是当前 host 产品入口 |
| `product/schemas/runtime/live-batch.schema.json` | `profiles/live-us-equity.json` 的历史 resource lock、已封存 hash 记录 | 虽无新 batch 运行时消费者，删除会破坏现存 profile discovery 和历史读取；不新增兼容层 |
| `live-portfolio/2.0.0`、SEC fact v1、source-access/snapshot v4 | `common_stock_data.py`、`collection.py`、各来源适配器和 Gate | 实际当前契约；v4 移除误放的三股产品上限，旧 profile/v1/v3 不改写 |
| `macro.py`、`options.py`、`ownership.py`、`public_research.py`、`peer_candidates.py` | 已归档 `expand-free-data-holding-research` 及多维研究阶段 | 后续能力，不属于本次清理目标 |
| `docs/data/*progress*`、`docs/data/*.sha256`、`reviews/development/live-*` | 归档记录、证据索引和历史 hash | 保持原样，不把历史表述冒充当前产品说明 |

## 文档收缩

- `docs/product/us-equity-live-advisory.md` 改为当前数据准备使用说明，旧 batch 只出现在“已退役”清单。
- `docs/data/us-equity-sources.md` 的首要状态改为 Handoff 数据准备；后续历史试拉段落保留，但不再作为运行前置。
- `portfolio-council` Skill 将当前 Handoff 研究阶段与 fixture 完整 Council 兼容链路分开，不再引导用户使用旧 live profile。

## 验收证据

### 聚焦测试

实际命令：

```sh
env TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  tests.test_live_host_entry tests.test_live_cli tests.test_live_profile \
  tests.test_live_contracts_gate tests.test_live_collection \
  tests.test_common_stock_research_contracts tests.test_live_admission \
  tests.test_live_source_routing tests.test_live_nasdaq \
  tests.test_live_yahoo_transport tests.test_live_eastmoney_transport \
  tests.test_live_sec tests.test_live_sec_client tests.test_live_filing_selection \
  tests.test_live_financials tests.test_live_security_metadata \
  tests.test_multidimensional_stage tests.test_research_materials_stage \
  tests.test_portfolio_council_skill
```

第一次整理结果为 292 项；前三次独立复核发现的范围内缺口均如实保留在各自报告中。当前源码快照的最终限定结果为：`Ran 301 tests in 2.084s`，`OK (skipped=10)`。机器可读命令、原始结果摘要、范围声明及完整测试输入 hash 见 `us-equity-live-advisory-slice-final-focused-tests.json`。跳过项为可选依赖/平台条件；本命令没有联网、没有启动产品 LLM、Regression 或完整 Gate。

覆盖映射：

| Tasks | 当前输入/实现 | 当前证据范围 |
| --- | --- | --- |
| 1.1 | 合成 NASDAQ/Yahoo/Eastmoney/SEC 响应及适配器 | 主源、允许/禁止备用、限流与失败分类；真实来源仅复用 `nasdaq-tls-fix.md`、`live-admission-v4-host-attempt.json` 既有证据，不扩大为当前 Council 验收 |
| 1.2 | 标准化 LiveFact、身份快照、SEC filing/fiscal 合成样例 | `source_id`/时间字段/raw hash、身份冲突、财务期间处理 |
| 1.3 | 来源选择、缓存、准入合成样例 | 单来源价格口径、主备不拼接、缓存 hash 重验、Provider 拒绝即停 |
| 1.4 | 带 future/stale/conflict 变体的冻结 snapshot | PIT 排除、Evidence Closure、缺口；共享配置在任何证券请求前验证 |
| 2.1/2.3 | `synthetic-manual-ten-positions.json` 派生的已确认 Handoff 与四证券 v4 snapshot | 七只普通股全部进入 `live-portfolio/2.0.0`，v4 SourceSelection 不再静默截断三只；旧 profile 限制不冒充当前产品限制 |
| 2.2 | 合成 `gate.json`、`data-preparation.json`、自包含逐证券 source package 与 snapshot | 按 `security_id` 下游消费；重算 Gate/preparation/source bundle/snapshot/SourceSelection/Evidence/conflict/data gap/failure 绑定；启动前重验 run manifest、stage、coverage、dispatch index、packet 及当前 Agent/Skill，外层重签不能掩盖底层漂移 |
| 5.1 | 实际 `collect_common_stock_data_from_handoff` 接缝，底层 Provider 使用确定性替身 | 一只身份失败时其他证券仍 `FROZEN/READY`，失败项保留结构化状态；不是仅测试回调组装器 |
| 2.4/4.1 | 宿主脚本与 CLI parser | 旧 host profile 在任何代理/取数/模型前拒绝；三个 batch CLI 不再注册 |
| 4.2/5.2 | fixture、普通股数据、多维与资料准备模块 | 必要共享函数和后续多维入口仍可解析且通过受影响接缝测试 |

一次将所有 `test_live_*.py` 当作发布集的尝试得到 239 项、8 个环境错误和 1 个旧断言失败：环境错误来自当前 Python 未安装可选 `exchange-calendars`，且都位于已退役完整 live Council 测试；旧 MCP 工具集断言没有包含已归档多维阶段的 `research_search` / `research_fetch`。后者已按实际契约修正并在上述 292 项中通过；前者不属于本 Change 的数据准备验收，没有冒充 PASS。

### 严格规格和退役入口

- `openspec validate us-equity-live-advisory-slice --strict`：`Change 'us-equity-live-advisory-slice' is valid`。
- `/bin/bash scripts/run-product-smoke.sh --profile live-us-equity --portfolio /private/tmp/unused /private/tmp/unused-out`：退出 `2`，返回 `LIVE_COUNCIL_ENTRY_RETIRED`。
- `python3 -B scripts/council-dev.py prepare-live-batch`：退出 `2`，命令未注册。
- 活跃代码引用扫描 `product scripts tests`：对 `product.runtime.live_batch|plan_live_batch|prepare-live-batch|launch-live-batch|summarize-live-batch` 零命中。
- 当前 v4 与现行批准记录扫描：无 `max_positions` 或 `source_selections.maxItems=3`；旧 profile/v1/v3 的历史限制仍保留。
- `git diff --check` 对本 Change 目标文件：通过。

### 当前关键锁

- `portfolio-council` Skill：`3.4.2`，SHA-256 `ed69a4603d431b5b7d4576c917021987e03719dc97bef772e9e3a1b22e345095`。
- `product/version-manifest.json`：SHA-256 `698cce75e254fe90e9459e07300a11632ee6aa501fe8ec4c267f83cb7af0e181`，其中 `council_skill` 与上述 Skill hash 一致，并登记 data-preparation/source-bundle 版本。
- host launcher：SHA-256 `e53e0a746637cd2c281ccae558bc4fa5d9ab188f1873a162405eea41c932d537`。
- runtime CLI：SHA-256 `469ed6f5e3109986e93e71b17529d3f812f4e72fcbe7f656b4e6f3e0b2e8be45`。
- Handoff 数据准备：`common_stock_data.py` SHA-256 `6b899c9097e2e1f2e5711aa35b56b3614fbe6e8401c391d5769fbc0803b72fa0`。
- 数据消费接缝：`common_stock_stage.py` SHA-256 `e62e66fbfd46a2e0bde19f2bbf7e6290efec410818d489755bf3bb4f3097955f`；`common_stock_research.py` SHA-256 `31990cbaec95bc07f6033aee3698f1126caee7091e196f4d54aadedd2806c27c`。
- 最终聚焦测试输入：`tests/test_common_stock_research_contracts.py` SHA-256 `de7de23e2cd01a032fe6781d3ced1dffdfca050c3f28627cf4ad2d92dd0fe104`；机器可读证据 SHA-256 `bbb51ed841b51223b4397f0e90e808d00cfd6b72739b09701a2f29e31bef4f55`。
- 当前采集器：`collection.py` SHA-256 `2646e232b99b8ae6255ba20e3267fdefa502dd62f39274c6d3ad7bcdf49668b3`。
- 当前 v4：snapshot Schema SHA-256 `625152e883e07022c44bdc47969cfbc2c150ae9610104fa039f369d4449479ff`；source-access Schema SHA-256 `a5fcecc2c492bb63b9a1b736af6f6f7a4d2c5486a9188949187d056257a39c15`；准入记录文件 SHA-256 `ea10c888f417bb370a63377936646fff478539694a47f3cb3aa4182a88141c11`，记录 canonical hash `84f7f933a5107a2948315ad66ff424b44f6db8773d691668a86a5eb4850f2960`。

### 独立复核

第一次独立复核见 `us-equity-live-advisory-slice-independent-review-1.md`，结论为 FAIL，并明确发现 v4 三股残留、Gate 被重签和真实入口整批失败三项阻断。第二次复核见 `us-equity-live-advisory-slice-independent-review-2.md`，仍为 FAIL：三股上限与单证券隔离已关闭，但指出 conflict、data gap、失败记录、snapshot id、collection error 与启动 manifest 的底层重验不完整，且 299 项只留有文字摘要。第三次复核见 `us-equity-live-advisory-slice-independent-review-3.md`，继续指出完整 preparation 重建、collection error 必填绑定和 stage/request/invocation/dispatch canonical 重建缺口。

当前实现已按现有 canonical 构造器补齐上述范围：从逐证券 package 重建完整 Gate/preparation，并验证补充 snapshot；启动前重建 stage、coverage、holding request、invocation、packet 和 dispatch index。运行包保存自包含 source package，新增一致重签攻击与启动前失败传播测试；301 项结果已保存为机器可读证据。该保证针对规格定义的结构、语义和交叉绑定；不声称没有外部签名或不可变信任根时能够识别攻击者对所有源码、产物和 hash 的同步替换。

第四次独立复核见 `us-equity-live-advisory-slice-independent-review-4.md`，结论为 `CHANGE_REVIEW: PASS`，确认 Task 5.3 可完成。Task 5.4 仍需用户明确人工完成批准；该 PASS 不表示真实 Provider、研究质量、完整 Council、Risk、Release Gate 或 Promotion 通过。

## 残余兼容风险

- 为了不破坏历史包读取，旧 live profile 的部分底层函数和 Schema 仍存在；安全边界依赖 host 旧入口明确拒绝与产品 Skill 的阶段路由。
- 当前 Handoff 批次按证券调用既有有界采集事务，因此整批最大请求量随已确认普通股数量线性增长；没有固定持仓产品上限，也没有“无限吞吐”保证。
- 历史进度文档仍包含“一到三股”和旧命令；这些是归档事实，不是当前使用说明。
- 本 Change 不重验真实 Provider 可用性或研究深度；来源未变时复用既有真实采集证据，不将其扩大为当前 Council 验收。
