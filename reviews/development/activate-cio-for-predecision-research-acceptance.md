# `activate-cio-for-predecision-research` 实施与验收记录

本记录仅针对当前 Change；正文按发生顺序保留各阶段证据及当时结论，最终收尾见文末。私人 Handoff、报告正文、模型事件和运行产物均保存在仓库外，不提交账户数值。

> 2026-09-25 范围更新：用户已清仓 MRVL，本 Change 现在只验收原研究截止点的非动作 `RESEARCH_SYNTHESIS`。下方建议分支段落是当时开发和失败证据，不再是当前交付要求；不能据此宣称 `PORTFOLIO_ADVICE` 已发布。当前入口退役、回归和新真实研究 Smoke 的结果见文末新增记录。

## 来源研究包只读核验

- 来源运行：`/private/tmp/activate-independent-skeptic-mrvl-20260924-v9/run`；来源 `run_id=host-common-stock-e23531ee-571d-44ee-b974-e5a426b36171`。
- `validate_forward_gate` 与 `validate_predecision_package` 均实际通过；来源 Gate hash：`30404964839f6184dc893c10ab607e62bb291e669b8bc52f469f252b69d7f9a8`；正向 bundle hash：`c5af616f85b860bd4de1b32c23ab00de02bbcf8d43a216716654fe07dde0f1cd`；交接包 hash：`104597b5956aef80ab9609dbf5a074e63df2f0a2a2f617ed49be085045360a26`。
- 截止 `2026-09-23T16:19:01.418151Z`，目标 `US:COMMON_STOCK:MRVL`，交接包 `DOWNSTREAM_READY`。正向目录有 9 份不同能力报告，Skeptic 1 份、状态 `LOW_CONFIDENCE/PASSED`，包含 3 个原始 challenge 标识。
- 正向 `RESEARCH_REPORT` 辅助维度为 `FAILED`：上游公开研报材料引用未形成有效 artifact，不能解释为“无研报反证”或“无风险”。核心 Company、Technical、Fundamental/Event、Industry、Macro、Market 满足现有来源门禁，但若实际 CIO 只作泛化复述仍不能通过内容验收。
- 完整建议上下文缺口：确认 Handoff 的账户与组合快照截至 2026-09-12，早于研究截止点超过 24 小时。历史检查当时还记录没有确认 Mandate；2026-09-25 契约已将 Mandate 改为可选，因此它不再是阻塞。该来源可用于当时的研究综合，不能据此完成真实完整组合建议。未修改或裁剪来源持仓。

## 确定性验证

- `python3 -m unittest -q tests.test_predecision_cio_stage`：17 项通过。覆盖独立目录冻结、禁止把新运行放进来源目录、版本化请求、来源未就绪及验证失败、旧账户及原始来源的时点、混合资产保留、Gate 内/外查询、跨运行拒绝、冻结报告篡改、整组合 Risk 输入、非动作研究综合、单目标动作边界、后置 Risk 否决及 Trace 篡改拒绝；还覆盖模型解码 Schema 的类型约束与最终引用须实际查询的提示。Risk 否决测试保留原始 `TRIM` 草案并交付 `SAFE_NO_TRADE`，不是模型实际验收。
- `python3 -m unittest -q tests.test_predecision_cio_stage tests.test_independent_skeptic_stage tests.test_multidimensional_stage tests.test_native_risk_runtime tests.test_risk tests.test_host_proxy_scripts tests.test_governance`：127 项通过；旧独立反证、多维研究、Risk 与宿主聚焦回归未发现本 Change 引起的失败。另 `bash -n scripts/run-product-smoke.sh`、`git diff --check` 与 `openspec validate activate-cio-for-predecision-research --strict` 通过。
- 扩大至 `test_live_cio_final_response` 和 `test_development_environment` 的 160 项检查未全通过：前者运行环境未安装项目可选 `exchange-calendars`，后者的既有 `SessionPathTests.test_smoke_modes_quote_paths_and_keep_deferred_proof_run_scoped` 构造缺少 `invocations/runtime_company_analyst.json` 的合成目录。两项均不能记为 PASS；未为本 Change 修改无关旧测试或安装全局依赖。

## 宿主真实模型尝试

宿主入口均使用 `scripts/run-product-smoke.sh --stage predecision-cio-synthesis` 和独立新目录；准备均判定请求 `PORTFOLIO_ADVICE`、实际 `RESEARCH_SYNTHESIS`，缺项为账户与组合时点及 Mandate。前三次按固定开发默认 `gpt-6-luna`；用户于本轮明确批准仅此次真实验收改用显式 `gpt-5.6-terra`，未修改默认模型。

| 运行目录 | 首个分歧 | 实际结果 |
| --- | --- | --- |
| `/private/tmp/activate-cio-mrvl-host-113TFh/run` | 当前桌面全局配置含该 CLI strict-config 不识别的 app-only MCP 字段 | 模型前失败，`FAILED_VALIDATION`；未产生 CIO 草案 |
| `/private/tmp/activate-cio-mrvl-host-ETMJVa/run` | 使用 CLI 支持的 `--ignore-user-config` 后，受当前开发沙箱阻止初始化本地 app-server client | 模型前失败，`FAILED_VALIDATION` |
| `/private/tmp/activate-cio-mrvl-host-q1Jg2u/run` | 在获准的宿主权限下成功进入 Codex CLI，但 ChatGPT 账号返回 HTTP 400：`gpt-6-luna` 不受该账号的 CLI 支持 | `turn.failed`，无模型研究输出、无 CIO Evidence 查询、无 Risk；`FAILED_VALIDATION` |
| `/private/tmp/activate-cio-mrvl-terra-jpnjxv/run` | Terra 可进入模型服务，但新阶段解码 Schema 固定值字段缺少 `type`，服务端返回 `invalid_json_schema` | 模型前失败，`FAILED_VALIDATION`；已修复并增加聚焦测试，旧证据不改写 |
| `/private/tmp/activate-cio-mrvl-terra-W9kIyM/run` | Terra 实际执行了 1 次 Gate 查询并生成结构化输出，但输出引用了 6 个 Evidence ID，仅查询其中 1 个 | finalizer 以 `CIO_EVIDENCE_NOT_QUERIED` 拒绝；已把所有最终引用均须先查询写入提示，未事后补造查询 |
| `/private/tmp/activate-cio-mrvl-terra-22F07B/run` | Terra 完成主线程回合，消费 9 份正向报告与 1 份 Skeptic 报告，1 次批量查询覆盖最终引用；未发生源码完整性漂移 | `COMPLETED_RESEARCH_SYNTHESIS`，只读 Trace `PASSED`；`risk_status=NOT_RUN`、无 `decision.json`，完整建议仍未验收 |
| `/private/tmp/activate-cio-mrvl-terra-GOk5Pm/run`（目标目录未执行） | 本次申请宿主运行时，权限审核明确拒绝：冻结研究包可能含私人账户／持仓，现有授权不足以确认可发送给 Terra | **未启动**，无新模型输出；不得绕过审核或计为验收通过 |
| `/private/tmp/activate-cio-mrvl-terra-QShuu9/run/run` | 用户随后明确授权本次 MRVL 冻结研究包用于 Terra 只读验收；修复后宿主入口重新运行 | 执行/结构 `COMPLETED_RESEARCH_SYNTHESIS`、Trace `PASSED`；独立内容复核 `FAIL`，见下文；Risk `NOT_RUN`、无 `decision.json` |
| `/private/tmp/activate-cio-mrvl-terra-gy9Dga/run/run` | 针对 QShuu9 的三项明确内容缺口收紧提示、保留旧产物，使用新 run_id 和目录重验 | `COMPLETED_RESEARCH_SYNTHESIS`、只读 Trace `PASSED`，一次 Gate 查询 16 个 Evidence ID；独立内容复核在**研究综合级别 PASS**，Risk `NOT_RUN`、无 `decision.json` |

失败运行只证明各自的首个分歧，不能把 prepare、进程启动或 `thread.started` 算作真实 CIO 消费。旧成功运行 `run_id=predecision-cio-cc948e3f-0f23-4d07-a3ed-d8c9581f81d1`，旧 Trace hash 为 `fd8714f878b746a206856d0106ee05b33a3015aa48bc154096ed6cd9fd3ef445`。报告表达审慎偏正面的近期经营判断，但以客户需求、利润转换、供应/贸易限制、替代和收购执行为主要失效条件；对 3 项 Skeptic challenge 逐项给出接受或部分接受及判断影响。该运行发生于下述修复前，只可作历史参考，不可冒充修复后的真实验收。

## 本轮修复及验收边界

- 修复后模型解码仍使用兼容的 Schema 投影，最终产物由原始权威 Schema 验证；提示明确要求最终引用的每个 Evidence ID 均已实际经冻结 Gate 查询。
- CIO prompt 显式交付本次锁定的 Portfolio Council Skill 和 runtime CIO Agent 协议全文；运行清单绑定两文件 hash 与 prompt hash，finalizer/trace 重验内容，避免仅以文件存在宣称已交付。该证明限于指令被提交给模型入口，不宣称能证明模型实际注意力。
- `generated_at` 改由宿主 finalizer 写入，保留模型原文 hash 并另记发布产物 hash；只读 Trace 校验生成时刻不早于宿主启动、研究截止点，也不晚于检查时刻。17 项阶段测试和 127 项聚焦回归通过，`bash -n`、`git diff --check`、OpenSpec strict 验证通过。
- 首次修复后 Terra 运行申请被权限审核拒绝，因此没有把前一轮运行的 Trace PASS 冒充为新验收；用户随后明确授权将该冻结研究包中可能包含的私人账户／持仓资料用于本次 Terra 只读验收，方启动下述新运行。
- 用户在本次会话中作出明确授权后，新外置运行完成：`run_id=predecision-cio-c404108a-75bb-4ec8-ab0d-6630010e2587`，Trace hash `235caa59a1820101e3f88835ac0df91ab85189369916a6a9e482d2a682f91b28`，宿主生成时刻 `2026-09-24T15:29:33.349204Z` 晚于启动时刻 `2026-09-24T15:27:25.927333Z`。模型主线程完成，Skill/Agent/产品指令与 prompt 的哈希绑定通过，最终引用均在冻结 Gate 查询集合中。仓库外报告路径为 `/private/tmp/activate-cio-mrvl-terra-QShuu9/run/run/report.md`。
- 独立内容复核判 `FAIL`：报告第 36 行比较现金与长期债务，却未在最终引用和 12 个查询 ID 中包含长期债务 Evidence `ev-sec-12ebb721...`；第 20、29 行把数据中心需求直接支撑利润转换写得过于确定，未尊重上游 `c9_mda_conflict` 对未消解 MD&A 定性叙述的限制；第 53 行的 Market 传导未用冻结的市场窗口与 MRVL 相对 SPY 表现，证券特异性不足。三项 Skeptic challenge 的取舍有具体影响，生成时间与非动作边界合格，但不能用结构 PASS 覆盖内容 FAIL。已针对性收紧 CIO 提示的原子事实双侧引用、事实/推断区分和 Market/Technical 传导要求；原运行保持原样，需新运行及再次独立复核。
- 新修正运行 `run_id=predecision-cio-d65d6120-6cbe-4e56-981f-890b2677383f`、Trace hash `2f1096649d79da74d2e3bbdab2c5b3b184dcc04479e87413f0bc59b101362790`，宿主生成时间 `2026-09-24T15:36:17.893448Z`。独立只读复核逐项核实现金/债务比较同时引用并查询相应 SEC Evidence、未消解 MD&A 的需求因果不再冒充事实，以及 SPY 正回报窗口和 MRVL 20/60 日相对表现的证券特定传导；六类研究问题和三项 Skeptic challenge 均有实质取舍、影响和重评条件，无编造目标价或数字阈值。因此**本轮研究综合内容 PASS**。这一结论仅覆盖研究级别，不等于完整建议、Risk 或 Change PASS，也不宣称原生 Skill 激活或源码 OS 级只读已获证明。
- 独立只读复核确认上述 Skill/Agent 证明属于“宿主把锁定指令交付给模型入口”，不是 Codex 原生 Skill 激活事件或模型注意力证明。复核发现旧启动方式以 `product` 为可写工作区、只比较前后源码 hash，不能证明运行期间源码只读。已将新阶段子进程的 `-C` 工作区移至仓库外 run 目录，并显式交付原产品 `AGENTS.md`；清单/Trace 拒绝 `-C` 回源码目录或将源码列为 `--add-dir`。这是命令与契约修复，仍须宿主实际权限验证，不能以配置本身冒充权限证明。

## 历史建议阶段未满足的完成条件（已退出本 Change）

1. MRVL 正反研究综合的宿主真实运行、Trace 和独立内容复核已在研究级别通过；完整建议仍未完成，不能勾选 4.3 或将阶段报告当作 `PORTFOLIO_ADVICE`。旧失败报告与事件原样保留。
2. 有同一研究时点的完整确认组合、现金后，真实建议草案必须经过同一快照的前后置 Risk；Mandate 已调整为可选，合法 `NO_TRADE` 可通过，但仅研究综合不能代替该项。
3. 受影响测试的既有环境/基线偏差需保留说明；独立只读复核实际差异与运行产物；人工同步归档批准。未执行 Runtime Eval、Execution Replay、回测、Promotion，也不声称盈利能力。

## 2026-09-25 可选用户约束修订（历史开发记录，已退出本 Change）

- 新合同不要求用户机械设定单股上限或最低现金比例。没有 Mandate 的合格完整账户可进入 `PORTFOLIO_ADVICE`；部分 Mandate 只使已明确提供的比例生效。已提供比例有来源/时点且必须合法，晚于研究截止点时明确报错；不以 100%/0% 或旧 fixture 的行业、换手、ADV 比例伪装用户确认。
- CIO 建议草案现需分别解释目标仓位与单目标动作导致的现金安排，列出未知个人适配条件。Python 以冻结总值及 10 bps 模拟成本算卖出金额、动作后现金区间，并拒绝不足以覆盖目标区间的 `maximum_notional`。后置 Risk 按成本后的最低现金校验用户现金下限；缺 ADV 作为可执行性提示，不作无来源的硬否决。报告区分账户事实、用户约束、CIO 判断、硬检查、流动性提示与个人未知。相关新产物版本为 advice draft `1.1.0`、Risk result `1.1.0`、predecision Risk policy `1.1.0`，Portfolio Council Skill 锁到 `3.6.0`。
- `python3 -m unittest tests.test_predecision_cio_stage tests.test_independent_skeptic_stage tests.test_multidimensional_stage tests.test_multidimensional_schedule tests.test_multidimensional_research_contracts tests.test_common_stock_research_contracts tests.test_risk tests.test_native_risk_runtime tests.test_live_host_entry tests.test_host_proxy_scripts tests.test_governance -q`：最终 259 项通过。`bash -n scripts/run-product-smoke.sh`、`git diff --check`、`openspec validate activate-cio-for-predecision-research --strict` 同轮通过。覆盖无/部分 Mandate、明确禁用动作、账户来源 24 小时与 PIT、未勾稽、HOLD 容差、金额现金守恒和 NO_TRADE null；这些是合成/确定性结果，不是模型建议验收。
- 扩大测试的既有偏差复现：`test_live_cio_final_response` 在运行环境缺 `exchange-calendars` 包元数据时无法进入测试场景；`test_development_environment` 的一个旧合成目录缺 `invocations/runtime_company_analyst.json`。这不是本次代码回归的证明，也未将失败计为通过；此 Change 不为上述无关路径安装全局依赖或修改合成 fixture。
- 上述均为确定性/合成验证，不是新的 MRVL 主线程 CIO 真实建议。旧来源 Handoff 截至 2026-09-12，研究 cutoff 是 2026-09-23，超出 24 小时；仍需新的完整确认账户输入和与其同一截止点的正反研究包。旧研究综合 PASS 可保留为历史研究级别证据，不能补齐真实建议、宿主源码权限证明或最终人工归档批准。
- 修订后的规格和差异经独立只读复核两轮检查。首轮指出已知个人条件丢失、未知条件空白、已知净值勾稽冲突、成本前后现金口径与 Mandate 时间顺序；随后又发现 HOLD 容差、Decimal 循环小数、账户事实来源与 broker 完整覆盖的 24 小时/PIT，以及 Risk API 缺 action 可绕过禁令。上述均按具体路径修复并补聚焦测试；二次复核未见新的确定性阻断。复核者未运行测试或模型，其结论不覆盖真实建议内容和宿主操作系统权限。

## 2026-09-25 收敛为 MRVL 非动作研究（当前收尾依据）

- 用户已选择只继续 MRVL 研究，不再要求本 Change 形成持仓建议。入口仅允许真实来源证券 ID `US:COMMON_STOCK:MRVL`、`RESEARCH_SYNTHESIS` 和原来源 cutoff；`PORTFOLIO_ADVICE`、当前时点快捷模式与 Mandate 在模型前明确拒绝。用户在需求讨论中表示曾清仓 MRVL，但系统未独立核验当前账户；模型 `account_fit` 契约固定为“当前账户适配未评估”，不得用历史 Handoff 证明现况。
- 已移除本新阶段 advice 专用 Risk 准备、动作草案/动态 Schema、决策发布和 Mandate Schema。宿主参数、直接 CLI、prepare、finalizer 和对已准备请求的校验均有拒绝边界；旧 advice 原始产物未改写，但当前 checker 不重新认证其 PASS。此前为 advice 修改的通用 `product/deterministic/policy.py` 和 `risk.py` 已恢复到本 Change 前语义，旧 fixture Council/Risk 不随本研究入口改动。
- 产品 CIO 指令、Skill、版本锁、宿主帮助、产品说明与运行手册已对齐；阶段资源锁新增实际模型命令构造与 Hook 记录代码。`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_predecision_cio_stage tests.test_independent_skeptic_stage tests.test_multidimensional_stage tests.test_multidimensional_schedule tests.test_multidimensional_research_contracts tests.test_common_stock_research_contracts tests.test_risk tests.test_native_risk_runtime tests.test_live_host_entry tests.test_host_proxy_scripts tests.test_governance -q`：249 项通过。旧 `test_live_cio_final_response` 扩大测试仍因当前 Python 未安装 `exchange-calendars` 而未进入断言，不计 PASS，也未改其实现或安装全局依赖。
- 本轮第一次宿主脚本尝试：`/private/tmp/activate-cio-mrvl-research-Tb3Mpo/run`，`run_id=predecision-cio-d606e57c-103d-4a64-8d63-fc48d2cf9c85`。来源验证与准备通过、请求/实际均为 `RESEARCH_SYNTHESIS`；模型进程因当前受限执行环境 `failed to initialize in-process app-server client: Operation not permitted` 失败，终态 `FAILED_VALIDATION`，没有新 CIO 内容或建议。未绕过沙箱、未把准备通过当成真实 Smoke。
- 对上述失败后的最新代码/指令，另做零模型真实来源准备：`/private/tmp/activate-cio-mrvl-prepare-gKRW3l/run`，`run_id=predecision-cio-prepare-20260925`，准备通过。它只证明来源包仍可供新研究级阶段冻结，不证明主线程模型消费、宿主源码权限或内容质量。需在获准的 macOS 宿主 Terminal 使用全新外置目录补跑一次真实研究级 Smoke，随后独立内容复核；未勾选任务 3.1–3.3，不能申请归档批准。
- 独立只读复核检查了建议入口、MRVL 目标/时点、非持仓说明、Schema/Trace、执行关键文件锁、旧 fixture Risk 差异与文档；最终未发现新的确定性代码阻断。复核未启动测试或模型，不把旧 `d65d...` 报告的内容 PASS 升级为本轮版本 PASS。当时唯一实质验收阻断是新宿主真实研究运行及其独立内容复核；当时任务 3.1–3.3 未勾选。后续状态见下一节。

## 2026-09-25 新宿主真实研究运行复核（当前证据）

- 用户提供新宿主目录 `/private/tmp/activate-cio-mrvl-host-VjA0aX/run`。`run_id=predecision-cio-298ab3e4-d4cc-4b42-b35e-35ea651ae7fb`，请求及实际交付均为 `RESEARCH_SYNTHESIS`，模型清单及主线程执行证明均为显式批准的 `gpt-5.6-terra`，进程退出码 0、`turn.completed`、终态 `COMPLETED_RESEARCH_SYNTHESIS`。本地只读重验 `check-predecision-cio` 为 `PASSED`，Trace hash `7ad64ed960b1adff67df3a17e5bf4411e44ea7884a04498d8240608f0c021d69`；不是只凭用户粘贴的结果判断。
- 新运行绑定原来源 `run_id=host-common-stock-e23531ee-571d-44ee-b974-e5a426b36171`、来源 package hash `104597b5956aef80ab9609dbf5a074e63df2f0a2a2f617ed49be085045360a26`，研究截止点 `2026-09-23T16:19:01.418151Z`；报告生成时间 `2026-09-25T03:25:40.696792Z`。运行清单锁定 `runtime_cio.toml`、Portfolio Council Skill、产品指令、请求/综合 Schema、阶段实现、模型命令构造、Hook 记录器与版本清单的实际 hash；环境清单另保存 prompt/解码 Schema hash。这证明所提交资源及版本，不等于原生 Skill 激活或模型注意力证明。
- 来源目录与新运行分离；新运行把 9 份正向维度/Company 报告及 1 份 Independent Skeptic 报告列入消费目录。Codex 事件显示一次 `fixture_runtime.query` 批量查询，MCP 只读事件记录 15 个 Gate Evidence ID，Trace `cio_query_count=1` 且引用闭包通过。报告对三项 Skeptic challenge 分别作 `ACCEPT`、`ACCEPT`、`PARTIALLY_ACCEPT`，说明对持续性置信度、供应/替代路径及收购兑现观察的影响；现金和长期债务均有 SEC 引用，MD&A 文本冲突未作为已验证需求因果，Market 段结合 SPY 与 MRVL 的 20/60 日相反相对表现。独立内容复核仍单列，不以这些结构与主开发抽查代替。
- 报告/结构产物声明 `complete_portfolio_decision=false`、`account_fit=当前账户适配未评估`、`risk_status=NOT_RUN`；无 `risk.json`、`decision.json` 或新阶段建议草案。报告明确用户曾告知 MRVL 清仓但现况未独立核验、来源截止点后的价格/账户未核验。旧来源 Handoff 只作来源身份，不作当前持仓证明。两条 CLI `item.error` 是启用 Hook trust bypass 的提示，不是模型或查询失败；后续有真实查询及 `turn.completed`。
- 宿主实际命令以外置运行目录作为 `-C` 与唯一 `--add-dir`，未把源码目录列为可写工作区；进程结果显示 `source_integrity_unchanged=true`。然而环境清单与前后 hash **不能证明运行期间操作系统层阻止了对源码的写入**，事件中也没有针对源码写操作被拒的实证。按任务 3.1 与既有环境文档的严格边界，宿主源码保护的实际权限证据仍缺；不得把本次完成状态或未改动 hash 冒充这项证明，也不因此自动重跑模型。
- 当前 worktree 上再次执行 `check-predecision-cio`、`openspec validate activate-cio-for-predecision-research --strict`、`git diff --check`、`bash -n scripts/run-product-smoke.sh` 均通过；受影响 `test_predecision_cio_stage`、`test_risk`、`test_native_risk_runtime`、`test_host_proxy_scripts` 共 47 项通过。未执行 Runtime Eval、Execution Replay、回测或 Promotion，不能记为其 PASS；不因本次验收提交、推送或归档。
- 独立只读复核对本次真实产物的**研究内容判 PASS**：逐项核对六类内容问题及三项 Skeptic challenge；现金与长期债务两侧均有来源和查询，MD&A 未消解冲突未被写成已验证因果，Macro/Market 传导区分条件推断并结合 SPY 与 MRVL 的 20/60 日相对表现；没有发现重大反证遗漏、目标价/概率等虚假精确性或交易动作。报告文件 SHA256 `5b45b3c5bdd6ec6d1bc215dd88cb36acc26191760009a3f3d7e72d84f3823ad3`，Trace 文件 SHA256 `e1eb44b110bfcd382e96b73772534ead1e2920d27c6295befba439b90eb461dd`。复核者未启动测试/模型；建议入口与旧 fixture 的判断沿用已审代码及主线程聚焦回归，源码 OS 级只读缺口仍按上一条保留。该结论不等于 Change 或 Promotion PASS。

## 2026-09-25 进程证明收尾与新版本验收

- 既有 `check-predecision-cio` 成功分支已补读取 `invocation/process-result.json`，核对同一 run_id、整数零退出码、布尔非超时、空失败原因、成功终态及布尔源码完整性保持；缺失或非法值拒绝 PASS。聚焦测试覆盖正常、文件/字段缺失、类型错误、失败及矛盾状态。`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_predecision_cio_stage tests.test_independent_skeptic_stage tests.test_multidimensional_stage tests.test_multidimensional_schedule tests.test_multidimensional_research_contracts tests.test_common_stock_research_contracts tests.test_risk tests.test_native_risk_runtime tests.test_live_host_entry tests.test_host_proxy_scripts tests.test_governance -q` 共 249 项通过；OpenSpec strict 与 `git diff --check` 通过。此变更修改锁定的阶段代码，旧 `298ab3e4...` 运行只保留当时的真实内容证据，不冒充新锁验收。
- 新版本第一次宿主运行 `/private/tmp/activate-cio-mrvl-process-proof-DOxYIr/run`，`run_id=predecision-cio-bb62b1b5-6ac0-4bd5-9923-0f6bb361f28d`。模型进程退出码 0，非超时，源码前后完整性保持；但 finalizer 以 `CIO_REPORT_REF_INVALID` 拒绝发布，终态 `FAILED_VALIDATION`。诊断定位模型在第二条 `key_facts.report_ids` 中把来源 Company 报告的长 ID 抄错。原始模型输出与失败产物保留，未修改或补写；这不是本轮新增进程结果检查器造成的失败，也不能计为成功 Smoke。
- 针对该明确错误，在既有动态模型解码 Schema 中把 `key_facts.report_ids` 和 `macro_market_transmission.report_ids` 限为本次验证目录的 report_id；对有 challenge 的 `challenge_dispositions.report_id` 同样限制。权威 finalizer 的身份/证据闭包仍保留。聚焦阶段测试通过；该调整再次改变锁定阶段代码，须在宿主用新运行、新 run_id 验证服务端解码兼容和真实内容，不自动复用失败输出。
- 新版本宿主运行 `/private/tmp/activate-cio-mrvl-enum-uvVgh3/run`，`run_id=predecision-cio-be5f3909-404e-4779-8907-5ffc803d8576`，显式模型 `gpt-5.6-terra`；实际主线程回合完成，一次只读 Gate 查询覆盖 13 个 Evidence ID。请求与实际均为 `RESEARCH_SYNTHESIS`，原截止点 `2026-09-23T16:19:01.418151Z`、宿主生成时间 `2026-09-25T03:54:11.944182Z`。服务端接受动态解码 Schema，finalizer 返回 `COMPLETED_RESEARCH_SYNTHESIS`，修复后的 `check-predecision-cio` 在宿主及本地只读重验均 `PASSED`；Trace hash `6c5b286a75577628061d79573486ac5af9689bf5f098b56c3fcabd0a56457868`。进程结果为整数零退出码、非超时、失败原因为 null、终态一致且 `source_integrity_unchanged=true`，其文件 SHA256 `4d0cc556804988492780860ee56155f211662e0865eb052e872c65645a8ba553`。
- 新运行以外置运行目录作为 `-C` 和唯一 `--add-dir`，原生沙箱为 `workspace-write`，环境清单的运行前受保护产品文件快照 hash 为 `8fd5abbb45b3f65b22bd7694fb2285a66ef8a814a7b748fa3c95878c2d1c55ab`；运行后完整性标记为一致。此为本 Change 的有限源码保护证据，**不证明全进程 OS 强制只读**，该项保持 `UNVERIFIED`。运行保留 10 份来源报告身份，三项反证均给出接受程度与判断影响；无 `decision.json`、`risk.json` 或 advice draft，Risk `NOT_RUN`。报告文件 SHA256 `b5f9ed65230d777e804c889c9ac54e63253e7db38fae92a09b84af22ca1caaa3`，Trace 文件 SHA256 `9b6639f1df401aafca4ca130c798d3e1fa6fa19a9eabd810065b24ea45895469`。报告第 32 行的受限历史价格/EPS 比值来自冻结 Company 报告已保存的确定性计算 `83.8371`，不是新增目标价。最终独立只读内容复核另列。

## 新版本独立复核与收尾判定

- 独立只读复核对 `predecision-cio-be5f3909-404e-4779-8907-5ffc803d8576` 判定：**研究内容 PASS；结构及进程结果按修订后的有限保证 PASS；未发现新阻断**。报告回答六类问题，三项 Skeptic challenge 分别给出接受程度、对判断的影响及重评条件；现金与长期债务分别有 SEC 证据且经 Gate 查询，未把 MD&A 未消解冲突写成已证实因果；Macro/Market 传导结合 MRVL 相对 SPY 的 20/60 日差异。来源截止点、生成时间、未知当前账户适配、`Risk=NOT_RUN` 和非动作边界均明确。复核者没有运行模型或测试。
- 进程结果文件的 run_id、零退出码、非超时、无失败原因、成功终态及完整性标记均与 Trace 一致；新增 checker 的缺失、类型、失败和身份矛盾负例已在确定性测试中覆盖。实际运行的 `-C` 和唯一 `--add-dir` 均在仓库外，运行前后受保护文件一致；**全进程 OS 强制只读依旧 `UNVERIFIED`**，未把这一缺口描述成证明或新增验收要求。此前失败的 `bb62b1b5...` 运行保留为失败证据，不计入本次 PASS。
- 非阻断呈现瑕疵：报告第 42 行照搬冻结 Yahoo SPY 浮点值的过长小数位，数值有来源但观感欠佳；不影响结论，不为此再跑模型。未运行 Runtime Eval、Execution Replay、回测或 Promotion，也不以本次研究级 PASS 宣称投资表现。
- 规划/实现/验收对照：仅 MRVL 原截止点的 `RESEARCH_SYNTHESIS`、新外置 run、来源包/Gate/报告版本锁、模型实际调用、结构/报告/Trace、进程结果闭环、advice 拒绝及旧 fixture Risk 保留均有对应代码与检查；未把来源资料缺口升级为新工程任务。最终 249 项受影响确定性测试通过；`openspec validate ... --strict`、`bash -n scripts/run-product-smoke.sh` 与 `git diff --check` 再次通过。此前扩大测试的可选依赖及旧 fixture 环境偏差维持原记录，不冒充全库测试 PASS。
- 拟发布范围已区分：CIO 专属阶段实现、两份 Schema、CLI、Agent/Skill 指令与版本清单、产品/运行文档、OpenSpec 和对应测试为本 Change；`product/runtime/model_routing.py` 的 `agent_development_test_model` 是 CIO 当前默认模型路径直接导入的必要共享依赖。`scripts/run-product-smoke.sh` 同时含 Tiger 与 Luna 改动，`product/AGENTS.md` 同时含 Tiger 改动，`tests/test_host_proxy_scripts.py` 同时含 Luna 测试；归档后提交须按 hunk/文件审阅并仅纳入 CIO 必需部分，不能整仓暂存。Tiger 代码、账本、配置及其 Change，Luna Change 的规划文件和非必要测试均留在工作区，不顺带归档。提交前仍须逐项检查敏感信息、完整性和最终实际暂存差异。
- 以上完成到“申请人工同步归档批准”状态；按开发流程，apply 授权、真实 Smoke PASS 与独立复核 PASS 均不能代替最终人工完成批准。批准前不执行主规格同步、归档、提交或推送。

## 2026-09-25 人工批准与归档

- 用户明确回复“批准同步且归档”。已按该批准把三份增量规格分别合并到原有 `advisory-decision-output`、`deterministic-portfolio-risk` 和 `portfolio-council-orchestration` 主规格，新增需求数分别为 8、3、6，保留各主规格原条款；逐项对照增量内容一致。`openspec validate --specs` 为 20 项通过、0 失败；本 Change 的严格校验与 249 项受影响确定性测试通过。
- 变更已移至 `openspec/changes/archive/2026-09-25-activate-cio-for-predecision-research/`。发布仅纳入已审阅 CIO 实现、规格、说明、验收及其必要共享模型路由依赖；完整私人运行仍留在仓库外。老虎证券和其他 Change 的实现、规划及私人账本不在本次范围，不能因共享文件同处工作树而被提交。
- 发布副本的血缘限制：真实运行清单锁定的 `product/AGENTS.md` hash 为 `49ff509281cc87f4443aeb01ca31cf39373eb9bef234ac598e132d3ae63e9482`，其中包含工作树尚未归档的 Tiger 安全措辞；本 Change 的暂存副本刻意排除该无关 hunk，hash 为 `e04719322afc6004e0b220f13ad44f3520201b4dde136b7259f47e22c3737737`。故仅从本次 Git 提交检出的资源**不能逐字重算该次真实运行的完整指令锁**；原始清单/hash 与仓库外运行产物保持不变，不能编造二者一致。宿主脚本同样仅暂存 CIO 片段，未纳入 Tiger 命令和其他研究阶段的 Luna 默认改动。该限制不改变已运行产物的当时验证结论，也不把未提交的其他 Change 作为 CIO 已发布能力。
