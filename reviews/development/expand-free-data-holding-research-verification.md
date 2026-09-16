# expand-free-data-holding-research 阶段验证记录

## 结论口径

本记录只验证 `expand-free-data-holding-research` Change，不代表完整 Portfolio Council、候选版本晋升或投资建议通过。当前状态为：技术结构、公司基本面与事件、P3 行业比较、P4 宏观市场、研报自动准备受限路径、研究包组装及下游消费已有底层证据；v34 已补齐 v32 未消费 SPY 市场状态的宏观内容缺口。SEC 内部人文档及 Gate 接缝完成定点修复，ALB、MRVL、WOLF 的最新 Form 4 已真实完成 3/3 获取、解析与 Gate 准入；v37 已用 GPT-5.6 Terra 完成 ALB 所有权 `SOURCE_LIMITED` 研究样本。旧独立复核仍不覆盖这些修复后的源码与产物。研报正文、13F 机构比较和期权仍保留具体限制，不宣称对应完整研究能力通过。

SEC 联系身份只通过宿主环境变量传入实际采集进程，未写入仓库、运行策略或本记录。

## 真实运行批次

### 1. 已有技术与基本面基线

- 运行 ID：`host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f`
- 模型：`gpt-5.6-terra`
- 原始目录：`/private/tmp/stock-agent-multidimensional-real-20260915-v13/run`
- 确定性重归集：`/private/tmp/stock-agent-multidimensional-real-20260915-v16-revalidated`
- 结果：19 个任务均派发，18 份报告通过契约；ALB 行业报告因 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 被拒绝。修复后的归集保留 18 份报告和 1 个明确失败缺口，24 个证券/能力覆盖项齐全，下游消费为 `CONSUMABLE`。
- 适用范围：证明 P1 技术结构、P2 基本面/事件和单项失败隔离；不证明后来新增的研报工具调用、同行物化消费或宏观差异化关联。

关键文件：

| 文件 | SHA-256 |
|---|---|
| v13 `invocation/process-result.json` | `78214f3ee4c8547fd312d2905d304a6b22875213d65cdd4066f8adcd590fceea` |
| v13 `invocation/subagent-events.jsonl` | `43dac656caf341c277e38d15aa8f03632dcd76b52a350c8db7482bfa46344f87` |
| v16 `research/holding-research-bundle.json` | `cbb6e9f85e4b4842615781040d75c490051c93a3baaa1dab3604a5fb6acad88f` |
| v16 `research/holding-research-bundle.md` | `2da1f341f1b3a26abb9296f59ba0a9addccf1ed275f691ecfd85f04166d690a7` |
| v16 `research/execution-proof.json` | `43eb0cb21254d9d090666eb04994a11278b5c59ab57a677bd09931192ecdecc5` |
| v16 `research/consumption-proof.json` | `dd981eefbc3e81f4f87a8a10bf4f0726e8172fa36b0ef117bc25c7042022527c` |

内容复核：ALB、MRVL、WOLF 的技术报告包含 20/60 日收益、相对 SPY 表现、回撤、波动、量价状态及重评条件；历史不足处明确留缺口。三家公司基本面与事件报告连接 SEC 事实、经营驱动、现金生成、融资/稀释或重组限制，未输出组合动作。

### 2. v24/v25 定点失败与修复

- v24：`/private/tmp/stock-agent-multidimensional-repair-20260915-v24`。自定义 `PATH` 遗漏 `/opt/homebrew/bin`，`codex` 未启动；未发生模型调用。
- v25：`/private/tmp/stock-agent-multidimensional-repair-20260915-v25`。MCP 可初始化并列出工具，但 `research_search` 子进程因 `STOCK_AGENT_FIXTURE_MCP_PYTHONPATH` 缺少仓库根目录而报 `ModuleNotFoundError: product`。运行在正式研究前停止。
- 修复：统一 launcher 将仓库根目录与虚拟环境 site-packages 一并写入绑定 MCP 的 Python 路径；未新增沙箱、未复制认证、未扩大文件权限。直接 MCP 协议复核后，OpenAlex 搜索返回 HTTP 200 并保存 `search-1.json`。

这些失败只用于证明实际根因及修复，不计为能力通过。

### 3. v26 GPT-5.6 Terra 多维批次

实际宿主入口：

```text
bash scripts/run-product-smoke.sh \
  --stage multidimensional-holding-research \
  --handoff /private/tmp/stock-agent-multidimensional-real-20260915-v13/run/audit/portfolio-handoff.json \
  --gate /private/tmp/stock-agent-multidimensional-real-20260915-v13/run/evidence/gate.json \
  --peer-candidates /private/tmp/stock-agent-multidimensional-real-20260915-v13/run/research/peer-candidate-pool.json \
  --model gpt-5.6-terra \
  /private/tmp/stock-agent-multidimensional-repair-20260915-v26
```

宿主环境另行提供 live 依赖、来源准入文件、SEC 联系身份和缓存目录；私人值未进入仓库。

- 运行 ID：`host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f`
- 资料准备：6/6 invocation 形成终态；三项同行选择为 `READY`，研报准备分别为两个 `BLOCKED_CONFIGURATION` 和一个 `SOURCE_LIMITED`。
- 实际研报工具产物：8 个搜索 JSON、4 个正文尝试 JSON。搜索由 Agent 生成查询并通过绑定 MCP 执行；正文 API 缺少外置 `OPENALEX_API_KEY` 时保持配置阻断，未冒充“市场没有研报”。
- 同行物化：ALB→DD、MRVL→ALAB、WOLF→PLAB，全部经身份核实、采集和 PIT Gate 后标记 `FROZEN`。
- 正式研究：19 个任务均被派发，17 份输出通过结构校验。ALB、MRVL 行业子 Agent 已有 `SubagentStart`，但 Codex 在 compact 阶段中断，未产生 `SubagentStop`；确定性 finalizer 将其记录为 `MULTIDIMENSIONAL_SUBAGENT_TERMINAL_EVENT_MISSING`，没有把父线程的“已完成”文字当成成功。
- 归集：17 份报告、2 个明确 FAILED gap、24 个覆盖项；下游消费检查为 `CONSUMABLE`，`downstream_models_started=[]`，`complete_portfolio_decision=false`。
- 内容边界：WOLF 行业报告仍为来源受限，未充分消费已冻结同行；共享宏观报告有事实和推导，但未比较至少两家公司不同敏感性；技术任务在旧大上下文中未充分使用预计算产物。因此 v26 不能关闭 Task 4.3 或 5.3，也不替代 v13/v16 的技术基线。

关键文件：

| 文件 | SHA-256 |
|---|---|
| v26 materials `invocation/subagent-events.jsonl` | `4d9382b17d6e80ca87d3e76439a770b895d2212a74e12e2161a3488733f47e14` |
| v26 `material-preparation-manifest.json` | `4c73ca50b47ef7a7c769bf9cc4e94a3aa6ebddbcfa350a7bea63c9d21941f29f` |
| v26 `peer-materialization-manifest.json` | `7ad188c0246cc3ef6e5004dba817526af5e0a011379bbb3af6da0187e657a754` |
| v26 peer Gate | `7f19a32f224a572958b7ee39319dfedebf4e1734ea6b97c7c63134b1a84c3dd6` |
| v26 formal `invocation/subagent-events.jsonl` | `f66d707ab2d21acc6768ef2b7298133604b3d1bdb2e2e12f566f4ccb070abfcf` |
| v26 `holding-research-bundle.json` | `d7f26ff326877f8cc44b7336d978dbd2cbb43d926e9f12c1744d5ff08043b18a` |
| v26 `holding-research-bundle.md` | `26a3bdc2ae33f4a4587ea9af9faeb486b9972f0a80aa8a1fef7fcc95bf4053ae` |
| v26 `execution-proof.json` | `762896f4e2aebd00ff5b0b7c4d6127e94ba3d818440df5a10cd31e33922ebec2` |
| v26 `consumption-proof.json` | `5b6d8a175dbe0b944289f34b06da692d3d186bd8bd9c57429ab52c5e9c817d3e` |

内部内容 hash：bundle `faa1c795b37a7ebba57f425b1e6fa52b38e3e32514dce592cb2e6b45e090b209`；consumption proof `e6c0a1441c65e0b4cb973a404b8241444f070a6e857ef6c59bcf45765fa5ee58`。

## v26 后的确定性修复与 v27 装配证明

本节没有再次调用模型。

1. 启动绑定：禁用与当前冻结 Gate 无关的 `live_runtime` MCP，保留 run-bound fixture MCP；修复其 Python import 路径。
2. 终态隔离：父进程结束后，已开始但没有终态事件的任务生成明确失败记录；从未开始的任务仍 fail-closed。
3. 技术输入：Agent 包不再嵌入全部 OHLCV Evidence ID；每股约 20KB，只携带预计算统计、图表引用、366 条底层事实数量及 ID 集合 hash。独立 artifact 仍保存全部 366 个 Evidence ID 和 artifact hash。
4. 行业输入：只保留每个报告序列的最新有限事实，不再把完整 SPY 历史或候选池重复塞入任务；每股 145–170 个允许 Evidence ID，并明确 `materialization_status=FROZEN` 与已物化证券。
5. 指令：明确禁止空查询；已冻结同行不得因旧候选缺口文字被重新视为未物化；技术任务直接读取预计算 artifact。

零模型准备命令：

```text
python3 -m product.runtime.cli prepare-multidimensional-research \
  --repo /Users/caihaoming/Documents/stock_agent \
  --handoff /private/tmp/stock-agent-multidimensional-repair-20260915-v26/materials-run/audit/portfolio-handoff.json \
  --gate /private/tmp/stock-agent-multidimensional-repair-20260915-v26/materials-run/research/peer-materialization/gate.json \
  --run-dir /private/tmp/stock-agent-multidimensional-repair-20260915-v27-prepared \
  --run-id host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f \
  --model gpt-5.6-terra \
  --peer-candidates /private/tmp/stock-agent-multidimensional-repair-20260915-v26/materials-run/research/peer-candidate-pool.json \
  --research-materials-run /private/tmp/stock-agent-multidimensional-repair-20260915-v26/materials-run
```

结果：`PREPARED`，19 个任务。`run_manifest.json` SHA-256 为 `4035811df2b99dc12619b214c1add091534b0f38c349b1877f207938b4ad1576`；`dispatch-index.json` 为 `f1e64a0720b6e776d475e2d8499054121fb7c1d3ae5048fe57b3fa19ff5b650a`。

当前插件缓存 `0.3.0+codex.20260915034340` 与源码中 plugin manifest、version manifest、runtime profile、market Agent、两个相关 Skill、launcher 和多维 stage 的 SHA-256 全部一致。此项只证明下一次宿主运行将加载当前实现，不证明模型内容已达标。

## v28–v31 定点运行与根因收敛

- v28 验证到正式研报正文配置失败必须保留为配置阻断，不能伪装为 `SOURCE_LIMITED`；该批不用于证明 P3/P4 内容。
- v29 完成资料准备与同行冻结，但正式阶段发现重复导入同行事实。随后改为复用已冻结同行，不重复采集或合并。
- v30 暴露宏观任务只有官方宏观事实、没有公司暴露事实，运行在形成合格 P4 样本前停止。
- v31 已加入公司事实，但 ALB 基本面模型输出污染 canonical Evidence ID，被严格 Evidence Closure 拒绝。该批同时暴露调度器把失败的 `SubagentStop` 错当依赖完成；修复后仅 `output_capture.status=SAVED` 满足依赖，失败任务只释放并发槽，依赖失败通过明确终态传播。

这些运行保留原始事件、stderr 和 process result，只用于根因及 fail-closed 证明，不作为最终内容样本。

## v32 GPT-5.6 Terra 完整多维批次

实际宿主入口：

```text
bash scripts/run-product-smoke.sh \
  --resume-multidimensional-run \
  /private/tmp/stock-agent-multidimensional-repair-20260915-v32-prepared \
  /private/tmp/stock-agent-multidimensional-repair-20260915-v32-host-launch
```

- 运行 ID：`host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f`
- 模型：`gpt-5.6-terra`
- 执行：19 个独立 Specialist invocation 全部有 `SubagentStart`、`SubagentStop` 和 `SAVED` 输出；父流程 `process_exit_code=0`、`stage_status=PASSED`、`source_integrity_unchanged=true`。
- 归集：19/19 报告通过结构、绑定与 Evidence Closure；24 个证券/能力覆盖项齐全，没有 failed task。
- 下游消费：确定性命令 `check-multidimensional-consumption` 返回 `CONSUMABLE`，解析 claims、Evidence、assumptions、calculations、gaps、research relationships 和 observation conditions；`downstream_models_started=[]`、`complete_portfolio_decision=false`。
- 行业内容：ALB–DD、MRVL–ALAB、WOLF–PLAB 均读取冻结双方事实。至少 ALB–DD 形成同季度收入与净利润实质比较；WOLF–PLAB 明确业务模式、期间和重组可比性，并区分宽泛行业背景与公司特定传导。因此 Task 4.3 已完成。
- 宏观内容：真实引用 10 年期美债收益率、CPI、失业率及三家公司 SEC 事实，比较 WOLF 与 ALB/MRVL 的融资条件敏感性并给出假设和反向条件；但没有消费 Gate 已有 SPY 日线，报告明确将市场状态列为缺口。因此不关闭 Task 5.3。
- 研报、所有权、期权：分别如实输出 `FAILED` 配置阻断或 `INSUFFICIENT_EVIDENCE`，没有将搜索线索、空快照或模型记忆包装为研究事实。

关键文件：

| 文件 | SHA-256 |
|---|---|
| `run_manifest.json` | `4d2dec18b153e326d75ef19651e87fb8929d9f84489ba1094b318639f6475efd` |
| `research/dispatch-index.json` | `895f679e6c74884c437cb0cda143450a38cf82c4965bbd06b086f8e40bceb2e3` |
| `invocation/process-result.json` | `a233f907c2896a1efb1c5b9187e83dce01b7ac36d41982059854a6eba63c9b82` |
| `invocation/subagent-events.jsonl` | `9c7b212ff28faa4fde2169e79294337a2ddb8f9bf4805f626c77f7eca269f101` |
| `research/holding-research-bundle.json` | `478c9a2e4a282612620dc956c9d286a250414f3196d400c73158e1583365c396` |
| `research/holding-research-bundle.md` | `849c044fe5e4c89d6d88d75af117833a9bfbf6cd8ef4f2fda2916f969063cd55` |
| `research/execution-proof.json` | `049ef84c474fe055911b20238a5281a45da05635f3a3eddbff405600396ee678` |
| `research/consumption-proof.json` | `9a288259c3af03af9b84b7fdc8f5e14da7723db8ce05044c90fe0ef30df9d1e5` |

## v32 后的 P4 最小修复

v32 内容复核确认，P4 缺失不是外部数据不可得，而是宏观任务没有消费已冻结的 SPY 序列。当前源码已做限定修复：

1. 新增 `market-state-calculation/1.0.0` 确定性计算，输出 SPY 20/60/252 日收益、波动、回撤、区间与量价状态，并锁定底层 Evidence ID 集合。
2. 共享宏观 dispatch packet 直接绑定该 artifact；动态 Schema 只允许引用本次 artifact。
3. 宏观指令要求用计算事实解释大盘风险状态，并至少形成一组差异化公司传导；禁止只说所有公司均受融资条件影响。
4. 为避免重跑 18 个未受影响的 Specialist，宿主入口增加单个无依赖维度的定点补证模式；它仍经过原 Agent、Skill、Hook、动态 Schema 和 Evidence Closure，只生成 `SINGLE_TASK_EVIDENCE`，明确不生成或冒充完整研究包。
5. 零模型 v33 已准备 19 项完整索引，但待执行入口只允许 `dimension_research_13`。SPY 市场状态包含 20 日收益 -1.747%、年化波动约 8.52%、最大回撤约 -2.58%；60 日收益 2.123%、年化波动约 11.79%、最大回撤约 -3.38%；252 日因只有 250 个交易日保持 `INSUFFICIENT_HISTORY`。底层 183 个 Evidence ID 以集合 hash 锁定。

v33 定点补证准备目录：`/private/tmp/stock-agent-multidimensional-repair-20260915-v33-macro-prepared`。

| 文件 | SHA-256 |
|---|---|
| `run_manifest.json` | `f9e7ae84d3e42ca33575655276940c9573a0b088bc27e6b9ad728fda927e83dc` |
| `research/dispatch-index.json` | `4756cbd2b8e669da29f6efb2e08efdd1c73f996a66b4b997767e59f0d7cfea5e` |
| `research/precomputed/1f70b0617491e512/market-state-calculation.json` | `0e5d4e65b2e95e63912ec283166c3aea6e87f0fa114acdbd501df6c007899eb7` |
| 宏观 dispatch packet | `441d0bb563c4654abe5e36c13345dc1a637ff4f9be2955007f748ede79aeaaac` |

首次 v33 定点执行真实启动了 `runtime_market_catalyst`，但旧 Stop Hook 仍按完整 19 项索引计算首波屏障，错误要求单任务入口同时启动三项任务，导致已形成的结构化输出被 `SubagentStopBlocked` 拒绝。该批 `process-result.json` 明确为 `MULTIDIMENSIONAL_TARGET_OUTPUT_INVALID`，只作为 fail-closed 与根因证据，不作为内容样本。

根因修复只增加定点任务作用域：宿主 launcher 向 Hook 传递唯一 `STOCK_AGENT_RESEARCH_TASK_NAME`；Hook 对其他任务派发 fail-closed，并将定点并发和 Stop 屏障限制为 1。完整批次仍使用原 19 项索引与原并发规则。聚焦的 launcher/Hook 测试 35/35 通过。

## v34 GPT-5.6 Terra 宏观定点补证

实际宿主入口：

```text
bash scripts/run-product-smoke.sh \
  --resume-multidimensional-task \
  /private/tmp/stock-agent-multidimensional-repair-20260915-v34-macro-prepared \
  dimension_research_13 \
  /private/tmp/stock-agent-multidimensional-repair-20260915-v34-host-launch
```

- 运行 ID：`host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f`
- 子会话 ID：`01a0a54a-5422-7263-8b16-f8d49c3bff55`
- Agent / Skill / Model：`runtime_market_catalyst` / `macro-market-analysis` / `gpt-5.6-terra`
- 任务：`dimension_research_13` / `macro_market:shared`
- 执行：一项 `ALLOW`、一项 `SubagentStart`、一项带 `SAVED` 的 `SubagentStop`；父流程与定点执行证明均 `PASSED`，源码完整性未变化，没有启动下游模型。
- 内容：引用美国财政部 10 年期收益率、BLS CPI 与失业率；消费冻结的 SPY 20/60 日收益、波动与最大回撤计算；使用 SEC 公司事实区分 WOLF 与 ALB 的融资条件传导，列出显式假设、不能量化的公司宏观弹性、MRVL 未形成公司特定结论的限制，以及再融资与市场回撤的反向观察条件。
- 边界：本产物是 `SINGLE_TASK_EVIDENCE`，只关闭 Task 5.3，不替代 v32 完整 19 项研究包，不启动 Skeptic、CIO、Risk 或 Eval。

关键文件：

| 文件 | SHA-256 |
|---|---|
| `run_manifest.json` | `eba1ad64e596e331b8fe306a8ba882bc95e3f4fd7d3d7efee25d0279dd09e548` |
| `research/dispatch-index.json` | `30ea1d7bba056d250165e91b2088290fd8d06d237784fd11881b05489572e94e` |
| `research/precomputed/1f70b0617491e512/market-state-calculation.json` | `0e5d4e65b2e95e63912ec283166c3aea6e87f0fa114acdbd501df6c007899eb7` |
| `research/reports/1f70b0617491e512/dimension-report.json` | `15193f5b1c23d63edc55b0ba8f80718e061e3d4358206fac99fec00689f9c823` |
| `research/reports/1f70b0617491e512/dimension-report.md` | `27ea9fa57b112dca6ccc00e31d1ce8d21decc4b1739a2a1e427001f88c9458e8` |
| `research/task-execution-proof.json` | `a4b153221055006cd983d497d0ff5ed5dcd081b3b2089e7300c1835ea2dfe577` |
| `invocation/subagent-events.jsonl` | `4f6ff8a2feb3a33e31133197bed1aebe1207ad1a23f6b2543c5556f35a3d50b6` |
| `invocation/subagent-dispatches.jsonl` | `a7cbcbc029136fcecddd87188a1f95d99298b210a2ff71a26bc956f5d7fd3a05` |
| `invocation/process-result.json` | `a233f907c2896a1efb1c5b9187e83dce01b7ac36d41982059854a6eba63c9b82` |
| `invocation/environment-manifest.json` | `a170ad57c1b1a8caf3ddcfed3e95b91e3615a634e086539c1af1cf49202c2798` |

因此 Task 5.3 已有真实资料、真实 Terra 推理、结构化报告、中文同源渲染、Evidence/计算闭合和执行证明，可标记完成。

## 确定性验证

实际命令：

```text
TMPDIR=/private/tmp PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_multidimensional_research_contracts \
  tests.test_multidimensional_schedule \
  tests.test_research_materials_stage \
  tests.test_multidimensional_stage \
  tests.test_public_research \
  tests.test_peer_candidates \
  tests.test_live_macro \
  tests.test_live_options \
  tests.test_live_ownership \
  tests.test_technical_research \
  tests.test_portfolio_council_skill \
  tests.test_product_config -v
```

最新受影响测试结果：98/98 PASS；其中定点入口与 Hook 任务作用域的最终聚焦集合 35/35 PASS。覆盖 Schema、Evidence closure、PIT、来源状态、只读 MCP 绑定、准备/正式权限分离、同行物化、技术计算/图表、SPY 市场状态计算、并发依赖、单项失败隔离、Skill/Agent 配置和版本锁。

补充聚焦命令运行 63 项，结果 63/63 PASS；用于复核 launcher、输入压缩、终态缺失隔离和版本配置。

OpenSpec：

```text
openspec validate expand-free-data-holding-research --strict
```

结果：PASS。

## P7 canonical 交接包（当前收尾快照）

本节是 Task 8.1–8.3 的当前证据；它取代早期“直接把 v32 bundle 当作最终交接包”的结论。组装过程为确定性重验，没有启动产品 LLM、Skeptic、CIO、Risk、Eval 或完整 Gate。

实际命令：

```text
PYTHONDONTWRITEBYTECODE=1 python3 scripts/council-dev.py \
  assemble-canonical-holding-research \
  --repo /Users/caihaoming/Documents/stock_agent \
  --base-run /private/tmp/stock-agent-multidimensional-repair-20260915-v32-prepared \
  --company-research-run /private/tmp/stock-agent-common-stock-wolf-freshstart-v4-20260914/run \
  --supplement-run /private/tmp/stock-agent-multidimensional-repair-20260915-v34-macro-prepared \
  --supplement-run /private/tmp/stock-agent-multidimensional-repair-20260915-v37-ownership-prepared \
  --output-dir /private/tmp/stock-agent-canonical-handoff-20260915-v4

PYTHONDONTWRITEBYTECODE=1 python3 scripts/council-dev.py \
  check-multidimensional-consumption \
  --repo /Users/caihaoming/Documents/stock_agent \
  --run-dir /private/tmp/stock-agent-canonical-handoff-20260915-v4
```

输入与绑定：

- 基础运行：`host-common-stock-925bc3c9-3362-4d19-b825-bdca2e5c2a4f`；decision cutoff 为 `2026-09-15T03:22:26.059573Z`。
- 基础 manifest / Gate / bundle 文件 hash：`4d2dec18b153e326d75ef19651e87fb8929d9f84489ba1094b318639f6475efd` / `5c98c9c95bc88b22bbaf2353afc4a93383b139cd7832d3bc9d713d393facf6a7` / `478c9a2e4a282612620dc956c9d286a250414f3196d400c73158e1583365c396`。
- 公司研究来源 manifest / Gate 文件 hash：`3c61e22e89fa0fb19d26f718a37ab58e38b86714e95a9da3c09ae6aa43b40d3b` / `08181494c0ea84a65bcbe27fbb6a6dccbd8b6f38626d620acde60654b786d2d4`。ALB、MRVL、WOLF 三份 `EquityResearchReport` 均针对目标 Handoff、证券身份、截止时间和 canonical Gate 重新验证后导入。
- v34 宏观补证输入 manifest / Gate / task proof / report 文件 hash：`eba1ad64e596e331b8fe306a8ba882bc95e3f4fd7d3d7efee25d0279dd09e548` / `7f19a32f224a572958b7ee39319dfedebf4e1734ea6b97c7c63134b1a84c3dd6` / `a4b153221055006cd983d497d0ff5ed5dcd081b3b2089e7300c1835ea2dfe577` / `15193f5b1c23d63edc55b0ba8f80718e061e3d4358206fac99fec00689f9c823`。
- v37 所有权补证输入 manifest / Gate / task proof / report 文件 hash：`2eb8b76f3fc185b8490af9e976ebda5fd10c6ac4a25996a670f11cd721569fb2` / `7bf83477c6046f5c5195537a3b74442bb63b3bac050047a83fa75ef31500504b` / `5440c455057d8b4eff7fd08b642005e2de0b6917fc66262f54b56eca5994e36e` / `ec616be297bf916f5924b850936c766bbbbf9ab0a61725bf9a14fce5245cc5a1`。

输出与判断：

- canonical 目录：`/private/tmp/stock-agent-canonical-handoff-20260915-v4`。
- `run_manifest.json`：`0c0bec37d9ab4b6d59ae8b871ca9dc7463463c531643d609fa11c1538e9de5e5`。
- `evidence/gate.json`：`875c4dce57ba9858f13868f217e829b554fecd5d9d44ebf7e089d5ecbfc833d5`；所有 allowed Evidence 的 `source_id/as_of/retrieved_at` 缺失数为 0。
- `research/holding-research-bundle.json`：`e5ecb3336b06e053ea4c5a75e625e6f62c370c9ad881265662bc9e66da040b41`；内部 bundle hash 为 `41d453ac4771f1c8a5f1635acf04c3d9f48526e02c0d07117ac0d45409f40c09`。
- `research/holding-research-bundle.md`：`1d82a9973fdfc8601fd050965a9a25f6d823d658b919f2f5e776ea2cfee31353`。
- `research/canonical-package-proof.json`：`98429c3e4699686896e43c7fe11f4a389f5cd0b52d453f361baea93ea50cb91c`；内部 proof hash 为 `15a15941263f545ab9dc865c7b2ebfb0ce6d366983e6d1e32b777204d34b1791`。
- `research/consumption-proof.json`：`706384202f912c6dc3a4f4f2a22fa47a682c33a6b5ed0d853f640a6b0a2896d8`；内部 proof hash 为 `672ac2b33bc70e2eaa08c86a1c5f8942c61bbe7e30bfedb7215706ed956be1f8`。
- 结果：22 份报告、24 个证券/能力覆盖项、3 份已重新验证公司报告、28 个由既有报告 observation/invalidation 条件归集的待反证问题。`STRUCTURALLY_CONSUMABLE=PASS`，`DOWNSTREAM_READY=PASS`，`llm_calls=0`，`downstream_models_started=[]`，`complete_portfolio_decision=false`。
- v34 宏观报告因 `CouncilRequest` 输入绑定不同而排除；v37 所有权报告因 run、cutoff、输入绑定和 canonical Evidence 不一致而排除。两者仍是对应能力的真实执行证据，但未被包装为同一次用户研究。

实现快照已写入 canonical proof，覆盖 stage、CLI、bundle validator/renderer、v1.1 Schema、`portfolio-council` Skill 与版本清单；文件 hash 分别为 `f0ed08e74b42d34d82fce422ad6add75c1918ceda03a9474179bf61972806339`、`930c48f59479a2bb1944644e33fa58c26a6f199377cd572737362235cae372ae`、`f3983fac80be3f834845e097d8dbeab6d5686b68a87650db72d493f518a406c8`、`fd5bd0af3e58d0d6e9d7472314aee6b6fa104233285ba74193a6021a5876c937`、`9dc67e23a875382f21d15410d70d5b6f7ad0719983e8e9d5e2acedc166952836`、`c222ef7371fb569eb32a86acc36ce537a33d1fb95e2eef705ee6014ee12b25fa`、`cdc6abdc5d3cd6cb1c827fc6e3e71ce6bfd89c0159c7eca8537f4005a3802a03`。

当前收尾修改后的限定验证：58/58 PASS；OpenSpec strict validate PASS。只覆盖 canonical 契约、组装/消费接缝、Skill 与版本配置，不扩大为完整产品 Gate。

## Specs / Tasks 映射

### SEC 所有权接缝定点修复（旧独立复核之后）

- 根因：`parse_submissions` 已接受 SEC Forms 3/4/5 的 `xsl.../primary.xml`，但网络边界仍只允许 accession 目录下单层文件名，导致请求发出前返回 `SEC_ENDPOINT_REJECTED`。放宽该路径后又确认展示 URL 返回 HTML，不能直接交给 XML 解析器。
- 修复：解析器与网络边界共用 canonical `primaryDocument` 路径规则；所有权读取器只将已验证的 `xsl.../文件名` 映射到同一 CIK、同一 accession 目录下的原始 XML，并同时保存 submissions 展示 URL、原始 XML URL 和 resolution version。任意目录、二级目录、路径穿越、编码斜杠、query、fragment 与 accession 错绑继续 fail-closed。
- 聚焦确定性证据：最新复核覆盖 SEC、披露、所有权、财务事实、证券身份、Evidence Gate 和多维定点接缝共 148 项，146 PASS、2 项因当前环境未安装可选 live 日历/AkShare SDK 而跳过；两个跳过均与 SEC 所有权无关。OpenSpec strict validate 同时通过。
- 最小真实证据：`/private/tmp/stock-agent-sec-coverage-20260915-v1` 对确认 Handoff 中 ALB、MRVL、WOLF 执行 13/30 次有界请求；三股身份、submissions、companyfacts、最新公司披露与最新 Form 4 全部通过，各生成 1 条 ownership Evidence，provenance 3/3 完整。输入 manifest hash `92813c5afebd4f0c09d99eb91667e44de0c3cc3c9d3267af722c05e956977c78`，结果 hash `81228b2f7dee36ca72e08d59b10ee4781cda42564e5ff069658a5a2a64e74165`；详见 `expand-free-data-holding-research-sec-coverage.md`。缓存位于外置临时目录，不写入仓库。
- v37 补证：`/private/tmp/stock-agent-multidimensional-repair-20260915-v37-data` 中三条 ownership Evidence 全部通过 Gate，0 条 ownership 被排除；Gate hash `7bf83477c6046f5c5195537a3b74442bb63b3bac050047a83fa75ef31500504b`。`/private/tmp/stock-agent-multidimensional-repair-20260915-v37-ownership-prepared` 通过宿主定点入口执行 `dimension_research_14`，真实 `runtime_market_catalyst` / `ownership-disclosure` / `gpt-5.6-terra` 报告为 `SOURCE_LIMITED/PARTIAL`，报告 hash `456d1faf09c7b7abeefce2210432260aa9593b15a606e2535dd833ed8773330f`；执行证明 PASS、源码未变、没有下游模型或投资动作。
- 证明边界：v37 证明内部人单期研究样本可运行，不证明 13F 两期机构比较、内部人完整历史或 MRVL/WOLF 的 LLM 语义覆盖。Task 6.3 以部分可得路径关闭，不标记完整 `RESEARCH_VALIDATED`。

| 验收项 | 当前证据 | 状态 |
|---|---|---|
| 研究阶段承接持仓、角色边界；Task 1.4 | v13/v26 Terra 派发、入口接缝测试 | PASS |
| 有界并行、共享任务、依赖与失败隔离；Task 1.6 | 调度测试、真实事件、v26 缺终态隔离 | PASS |
| 技术结构；Task 2.4 | v13/v16 三份技术报告与计算/图表引用 | PASS |
| 基本面深化与事件；Task 3.4 | v13/v16 三份公司报告 | PASS |
| 研报 Agent 自动准备；Task 3R.1 | v26 资料 Agent、8 次搜索、4 次正文尝试、权限分离与工具事件 | PASS |
| 研报自动链路；Task 3R.4 | 搜索可用，正文因外置 key 缺失受限；实际证据与影响完整 | 受限分支完成，RESEARCH_VALIDATED=否 |
| 行业比较；Task 4.3 | v32 的 ALB–DD、MRVL–ALAB、WOLF–PLAB 实质比较、可比性和传导分析 | PASS |
| 宏观关联；Task 5.3 | v34 单任务 Terra 产物消费官方宏观、SPY 计算和 ALB/WOLF 公司事实，含差异化传导、假设、限制与反向观察条件 | PASS |
| 所有权；Task 6.3 | v37 的 ALB/MRVL/WOLF Form 4 真实 3/3 获取、解析与 Gate 准入；ALB Terra 定点报告解释交易类型、滞后与不可推断边界；13F/历史序列明确延期 | 受限分支完成；完整 RESEARCH_VALIDATED=否 |
| 期权；Task 7.3 | Yahoo 实际尝试和逐项影响已有结构化记录；用户已接受延期到 `capture-futu-client-research-data` | 受限分支完成；完整 RESEARCH_VALIDATED=否 |
| 研究包与下游消费；Task 8.1–8.2 | v4 canonical bundle/中文报告/provenance/consumption proof；导入三份公司报告，排除不兼容 v34/v37 补证 | PASS |
| 证据归集；Task 8.3 | 本记录、canonical proof 的完整输入/输出/实现 hash、58/58 限定测试、strict validate | PASS |
| 独立复核；Task 8.4 | `expand-free-data-holding-research-canonical-independent-review.md` 直接重算 v4、当前实现和 SEC 接缝 hash，并抽查 Design 第 5 节全部维度 | PASS，无阻断 |
| 人工完成批准；Task 8.5 | 尚未申请 | 未完成 |

## 剩余最小闭环与停止条件

当前不能宣称 Change 完成。研报正文、13F 两期机构比较与期权/资金真实快照已由用户接受延期到 `capture-futu-client-research-data`，但这些能力不得标记为 `RESEARCH_VALIDATED`。当前独立复核结论为 `TASK_8.4_REVIEW: PASS`，记录 SHA-256 为 `268dc43a453827a982a090dbc0599692770968e789a30169e204c62a5234dc6f`。剩余最小闭环只有 Task 8.5 人工完成批准。

不需要运行完整 Gate、Regression、Replay、Calibration 或 Ablation，也不再增加产品模型批次。Task 8.5 在人工批准前保持未完成；批准前不归档、提交或推送。
