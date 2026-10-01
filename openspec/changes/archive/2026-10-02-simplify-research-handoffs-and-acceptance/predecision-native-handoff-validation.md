# 新真实正反包补验 predecision CIO

## 范围与实际状态

对应 Task6.5、H09/H16及已批准的新输入范围。只验证现有交接入口，不恢复暂停八维 Change，不证明原八维同批验收或候选晋升。旧缺失正反包仍缺失，旧原件、版本锁、事实和截止点未改写。

当前公司研究与五项核心正向研究已真实执行；独立反证 attempt6 运行合法完成，CIO 宿主入口、终态检查和最终独立内容复核通过，Task6.5已完成。行业无已冻结同行事实，技术以合法预计算为依据，其他报告保留低置信度和来源限制；不表示完整八维内容或当前账户研究达标。

## 本轮来源与产物

- 冻结资料来源：`/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/eight-dimension-rebuild-20260928/data-v2`；来源 run_id 为 `eight-dimension-rebuild-20260928-v2`。
- 来源 Handoff：同一根目录下 `eight-dimension-v4-acceptance.8iWZu9/run/audit/portfolio-handoff.json`。
- 新执行根目录：`/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-source-20261001.W1HHJs`。
- 新执行 run_id：`host-multidimensional-1beb18f3-fc9b-43e6-ad14-05077235f9ab`。
- 模型：`gpt-6-luna`。仅来源研究截止点，不输出当前账户或交易建议。

实际调用共同使用以下宿主环境（仅记录本次本机依赖，产品源码未写死这些路径）：

```sh
export PATH='/private/tmp/stock-agent-schema-ZEXpH8/venv/bin:'"$PATH"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=/private/tmp
```

### 公司研究

实际宿主命令：

```sh
bash scripts/run-product-smoke.sh --stage independent-counter-thesis-research --core-forward-only \
  --handoff '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/eight-dimension-rebuild-20260928/eight-dimension-v4-acceptance.8iWZu9/run/audit/portfolio-handoff.json' \
  --gate '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/eight-dimension-rebuild-20260928/data-v2/gate.json' \
  --data-preparation '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/eight-dimension-rebuild-20260928/data-v2/data-preparation.json' \
  --source-bundle '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/eight-dimension-rebuild-20260928/data-v2/source-bundle.json' \
  --model gpt-6-luna \
  '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-source-20261001.W1HHJs'
```

Company 成功后，宿主组合命令因下阶段相对采集路径错误退出1；不得称该组合命令完整成功。Company 的真实父进程退出0，子会话 `01a0f54c-0045-7b40-a6ef-64ea898d1952`，首稿 `SAVED`，无需修订。产物在 `company-run/research/reports/US_COMMON_STOCK_MRVL/equity-research.{json,md}`，原始事件/提示/进程证明在 `company-run/invocation/`。正式 output hash：`34719a1f419ae3637ca81120f32755f062be70d8435d1ea0fef4455ab7c85967`。

### 五项核心正向

修复后使用现有确定性准备函数创建 `run/`（无模型），传入已完成 Company、新执行 Gate、`core_forward_only=True`、`stage=INDEPENDENT_COUNTER_THESIS_RESEARCH`，然后实际恢复宿主入口：

```sh
bash scripts/run-product-smoke.sh --resume-multidimensional-run \
  '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-source-20261001.W1HHJs/run' \
  '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-core-20261001.RAsnom'
```

退出0，完成5/5。`run/research/holding-research-bundle.{json,md}`、`execution-proof.json`及 `run/invocation/` 保存底层证据。仅执行技术、基本面事件、行业、宏观、市场，Company通过真实报告导入构成第六项核心覆盖；未派发研报、所有权或期权任务。进程完整性前后相同。报告状态分别为 `LOW_CONFIDENCE`、`LOW_CONFIDENCE`、`INSUFFICIENT_EVIDENCE`、`LOW_CONFIDENCE`、`SOURCE_LIMITED`，不是完整内容能力验收。

### 独立反证

第一次宿主调用仅准备失败：旧调用工厂误要求本次 Luna 与 fixture Terra 候选模型相等，未启动模型。其三份原始输入/schema/prompt已可恢复迁存在 `run/research/skeptic-preparation-failed-model-lock/`，未修改内容。

修复并完成114项聚焦测试后，实际重新调用同源入口：

```sh
bash scripts/run-product-smoke.sh --launch-independent-skeptic-run \
  '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-source-20261001.W1HHJs/run' \
  '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-skeptic-20261001.bEn1hH'
```

真实子会话 `01a0f563-3c59-7dd2-a203-8252ec60f546`，已执行7次非空查询；事件在 `run/invocation/skeptic/subagent-events.jsonl` 与 `run/events/mcp/events.jsonl`。该轮在2400秒超时，宿主返回7，原进程退出124，`failure_code=COUNTER_STAGE_TIMEOUT`，`stage_status=PARTIAL`，`source_integrity_unchanged=true`。无 SubagentStop 和反证报告；包内 `counter_theses[0]` 为 `NOT_RESEARCHED/MISSING`，不得输入 CIO。失败包 hash 为 `0c058b29608b8e4056eb4f0ad94ee863b7a797727b6da6be28753eec74d4976f`，原 proof hash 为 `02f38f3077e41c406907ec68a17d70b3f4ecdba04f35069f9f40d3269860944f`。

#### FIRST_DIVERGENCE / ROOT_CAUSE

首次相关异常是子任务协调控制，不是 Evidence ID、数据包 hash 或模型连接拒绝。SubagentStart 的子 turn 为 `01a0f563-3c96-7fd2-bec2-66e6c99e6610`；原 PreToolUse 记录中后续同 turn 的 `wait_agent`、`list_agents` 仍携带父 session `01a0f563-1d36-7643-98b8-5c2235bd8495`。旧 Hook 仅按 session 判断活跃任务，在02:57:30指导其长等待，在03:07:45拒绝 list 后再次要求等待；子 turn随后在03:07:47、03:17:49、03:27:52重复等待，始终无 Stop。

确定性根因：子 Agent 与父线程共享原 Hook session 表达，协调控制没有区分实际执行者，导致子任务等待自身终态。最小修复只在现有 Hook 中核验可信 Start 的 parent/turn/role/DELIVERED/context/hash，为研究子任务拒绝协调调用并明确返回研究；父线程等待及不得干预活跃任务规则保留。未知/损坏 Start 不获得豁免，不修改来源或投资判断。现有 `--resume-independent-skeptic-run` 用于修复后的定点恢复；原40分钟失败保持，不重新执行公司/核心正向。

## 聚焦验证与修复映射

### 定点恢复2–4：保留失败、不扩大上游重跑

均使用 `bash scripts/run-product-smoke.sh --resume-independent-skeptic-run '<新执行根>/run' '<新的外置目录>'`，原 Company/核心正向报告未重跑。

| 恢复轮次 | 实际执行与首次差异 | 最小修复或结果 |
|---|---|---|
| attempt2 | 子会话 `01a0f591-a869-7630-ad0f-c3da58d76cf0`；无查询，报告声明 `COUNTER_INVOCATION_UNKNOWN`；包 `b8603ad795d9d19afb567b809ff76642253d5baef986261287f234dd320c9e12`，PARTIAL | 父环境的 attempt index 未进入 MCP server 环境；统一 launcher 的实际 MCP config.env 显式绑定已验证 index，不回退旧任务 |
| attempt3 | 子会话 `01a0f599-0ec8-7bc0-ad25-750bcd8f5207`；实际查询成功；confidence 字符串拒绝后只修为0.1，scope仍缺原 security_id；包 `0bcc6ce2a5edcdf0a422e0f023216458c0ab253d1bc1136163d9aab98be3b0b3`，PARTIAL | 提示区分本系统 Agent 结论与 Gate 允许的第三方原始来源，明确 scope 标识及数值 confidence；模型自报隔离违规不冒称系统实测违规 |
| attempt4 | 子会话 `01a0f5a6-b507-7e20-afd1-275650fc77f8`；三条具体反证和实际查询形成，但 scope 对象、assumptions 的 id 键违反 Schema；一次修订只修后者，第二次 `SCHEMA_TYPE_INVALID`，EXHAUSTED；包 `ed646a1998d3d0ad92c1d2d6442003a2a9c3d25e904163bd1bd16fcf14cd9e10`，PARTIAL | 下一新任务提示补充 scope 字符串和 assumption_id 示例；不改原稿、不追加同稿第三次修订、不放宽 Schema |
| attempt5 | 子会话 `01a0f5ad-e479-7391-8ec6-0f4c1f9f5fdf`；首稿结构 SAVED，output `e088c74501ff8ff4f8244d5f0c8d97b683ba2a033b840eb4e7df57148d342619`，但只发起空列表 query、报告无反证，包 `fd558e2fdaf6e3c84bc553f3b14750fe9110d0f51849004b6e286ac7a92b239b`，PARTIAL | 实际投影顶层及 agent_input 均有3864个允许引用，独立重建424678字节与Start hash一致；生成侧未缺失，没有实证截断。新提示明确两处清单位置，不去已省略的 invocation 查找，空 query 不是发现接口 |

原始进程、Start/Stop/Blocked和stderr位于 `run/invocation/skeptic/attempt-{2,3,4}/`；原始稿及一次 patch 位于 `run/research/raw-drafts/`。宿主返回7，即使内层退出0也不表示合法终态。新增 attempt2/3/4 各1父1子，均计入实际消耗。

- Hook角色恢复后198项相关测试通过；实际 attempt2 的子协调调用正确拒绝，没有再次自等待。
- MCP选定任务绑定后118项相关测试通过；独立读取实际 attempt2 index 构建 MCP 环境可成功绑定，但该确定性检查不是模型执行。
- 来源隔离与confidence提示修订后117项相关测试通过。后续 scope/assumption 键的提示修订另保留执行结果；组间重叠，不相加。
- scope/assumption 示例修订后同组117项通过（23.909秒）；清单位置说明后 `tests.test_predecision_source_preparation tests.test_skeptic_semantic_handoff` 31项通过（33.944秒）。两次 OpenSpec strict 及 diff 检查通过，Reviewer只读增量复核通过，未替其运行测试。

### 反证 attempt6 合法完成

宿主恢复命令同上，仅新建输出目录，使用新的 attempt6；退出0、`stage_status=PASSED`、未超时、源码完整性不变。子会话 `01a0f5b6-c7c6-7b02-8188-2c35f40ae8b2`（04:26:35–04:33:16 UTC），真实 `runtime_skeptic/gpt-6-luna`。首稿 `SAVED/NOT_REQUIRED`，未触发格式修订。

- 完整底层为7次非空 canonical query，另7条运输事件；此前运行中观察到的5次不是最终数量。正式稿引用7个真实 Evidence，供应商观点及会计基础限制保留。
- 两条公司特定反证：需求持续性/客户周期、成本投入与股东经济回报；有相反事实、两项显式假设、待补资料及可观察条件，非空泛风险清单。报告 `LOW_CONFIDENCE` 不代表完整估值、同行或交易建议。
- 正式 output 对象 hash：`40773b5e3155043905ff4efc71ea5caf232f29317bf5b2b74ca686c2ca6f3548`；原始草稿字节 hash：`33910bc323a88e1cf40d51aaf42465ce43d424d17da90e8df78c49917566aa80`。
- `research/skeptic/attempts/6/pre-decision-research-package.json` 包 hash：`30e3cd920f3190bbd8cb2d35ddab1f7c0624a6bb744f4531a91143af444ca09d`；文件字节 hash：`e6a0d2296a0bf5654a2d67451968d2817c3e5dfc84ea7d0fffc5070ae69cfce8`。状态 `DOWNSTREAM_READY` 仅为此阶段输入契约，不代表投资可执行。
- `execution-proof.json` proof hash：`8182db870f5d70312f26881d36259c6b8ccd4ca8b34879e8ab93082f3d0164a8`；文件字节 hash：`092a9decdc75b6f0fba8f8b4522b89eacf919e6ed3e50bf71414743aa8667ab9`。

独立内容复核发现：第二条反证、confidence_rationale 与 uncertainties[1] 将研发费用 +42.8% 错写为六个月。实际 Gate 对应期间是2026-05-03—08-01与2025-05-04—08-02，各91天；股权薪酬 +80.5% 才是各182天。错误存在于模型原稿，运输未改写。`DOWNSTREAM_READY` 仅表示结构/运行准入，不覆盖该内容错误。最终CIO未传播且明确比较限制，Reviewer判为本次交接的非阻断缺陷；原稿保持原样，不称已修复。

### predecision CIO 实际启动

```sh
bash scripts/run-product-smoke.sh --stage predecision-cio-synthesis \
  --source-run '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-cio-source-20261001.W1HHJs/run' \
  --target-security-id US:COMMON_STOCK:MRVL --requested-level RESEARCH_SYNTHESIS \
  --model gpt-6-luna \
  '/Users/caihaoming/Library/Application Support/StockAgent/acceptance-runs/handoff-predecision-cio-20261001.qyfjbF'
```

run_id：`predecision-cio-c0104027-65e0-4565-878c-41a5467d0e5b`；输出目录为上述路径的 `run/`。请求 `RESEARCH_SYNTHESIS`；只使用原截止点，不评估当前账户、不生成动作。Risk `NOT_RUN` 是本阶段合法边界，不能要求或冒称 Risk 已执行。

宿主退出0、`check-predecision-cio=PASSED`，实际终态 `COMPLETED_RESEARCH_SYNTHESIS`，未超时、源码完整性未变。主会话 `01a0f5be-2a80-7c42-a9fd-7532ca6fa766`，没有新派发子 Agent；原生 Stop 首稿 `SAVED`、无需修订。7次实际报告读取，获准七报告全被读取，模型选择其中六份作为论据；另1次 Evidence query取得10个事实，最终6个引用全部查询。运行身份、来源包 hash、consumed_reports、截止点与生成时间均由运行层装配，原始稿只含研究语义、短引用及报告选择。

| 实际产物 | 原文件字节 SHA-256 |
|---|---|
| `cio-research-synthesis.json` | `137c9a8bb8664bdf2e42a500ed0eca026eb14b60cd0c79e7d7a2a61e69e1281f` |
| `report.md` | `77505559face18cac071fb0832b5a93952966f909f5606f7f930458171888c2a` |
| `decision_trace.json` | `d08e20d4ff2714f4ecdceb1d8e56d1da13b94e90207e850f287bb9f2808765c0` |
| `invocation/final-message.json` | `f714a4b07b4cdbcf29e53ab5c39698c44d39a61ece348b4cea542f6900dae945` |
| `invocation/process-result.json` | `798a4dc9d3da281e64433ad4568374c2eac3dc820fae693d22895d780d647a88` |
| `invocation/codex-events.jsonl` | `f2e74b1b6c0950187346d4e0c97f6d0a2fb2d322850347263bde243bbd4d4583` |
| `invocation/codex-stderr.log` | `041c502e7f2c7f5d3382dc68f4e030633e38f108a3fe14d16d4eaecb3dcb6958` |

Trace 对象 hash 为 `1644e396dcfbea9b5e0e2d14b6d43d1a3c0231fc5be6267871d7155e7f2339e7`。Trace保存实际 Agent/Skill/产品指令文件 hash、阶段指令与提示 hash、模型、原生稿/事件/环境 hash、报告读取及事实查询关系。不会生成 `decision.json` 或 Risk veto，本阶段不是完整决策闭环。

内容初检：有7条事实、两条反证处置、业务前景/价格吸引力/账户适配分开、20/60/252交易日相反窗口及条件性宏观传导、观察和重评条件。CIO未传播研发“半年比较”，费用只作为待复核观察，不推断费用增速超过收入或股东回报恶化；但未明确改正上游原稿，原内容错误仍保留，最终内容判定由独立复核给出。

### 实际成本与残余效率问题

此调用等待超过半小时，未超时。stderr 在04:58:48 UTC明确出现远端 compaction stream断开及一次重试，最终正常完成；不能把所有等待归因于冗余、权限或LLM非确定性。原JSONL的 `turn.completed.usage` 可见输入14,253,226，缓存输入13,881,088（输入的子集，不相加），输出7,973、reasoning输出1,068（不再次相加）；非缓存输入算术差值372,138。不代表全链总消耗、账单费用或初始上下文大小。

实际 Prompt 176,745 bytes、输出 Schema 526,631 bytes、全集报告模型表示244,990 bytes。市场报告10项计算中的重复 input_evidence_refs 和 Schema两处同一7250ID enum造成机械膨胀；Reviewer只读确认其表示层去重属于原Task5.2范围。但本轮未实施、未真实加载新的表示，不能宣称已降低CIO token或新增完整优化完成。正式原件、元数据和当前运行不回写；不为追求效率数字新增基准或模型调用。

- 前一组252项受影响测试通过，新增原5项准备测试通过；组间有重叠，不相加为独立案例数。
- 来源采集路径修复后：`tests.test_predecision_source_preparation tests.test_independent_skeptic_stage tests.test_predecision_cio_stage`，112项通过。
- 独立路径复核修复后：`tests.test_predecision_source_preparation tests.test_host_proxy_scripts`，29项通过，含 Gate/preparation 符号链接拒绝、显式材料组合拒绝、自动同行池回填 core/default 对照。
- 模型接缝修复后，同上述来源/反证/CIO三模块，114项通过；涵盖 Luna 允许、未批准模型拒绝、fixture候选锁保持。
- 实际检查统一使用 `env PYTHONDONTWRITEBYTECODE=1 TMPDIR=/private/tmp /private/tmp/stock-agent-schema-ZEXpH8/venv/bin/python -B -m unittest <以上模块> -q`。
- `bash -n scripts/run-product-smoke.sh`、`git diff --check`通过；`openspec validate simplify-research-handoffs-and-acceptance --strict`通过。

没有启动全量 Gate、Regression、Calibration、Ablation、Execution Replay或Promotion；没有归档、提交、推送。Task6.7仍需最终人工批准。
