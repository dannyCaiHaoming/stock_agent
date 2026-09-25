# Macro/Market 输入消减实施验证

本记录描述当前 Change 的确定性检查、宿主真实运行和独立只读复核；不把宿主阶段 `PASSED` 等同于全部维度完成或候选晋升。

## 确定性结果

- `python3 -m unittest tests.test_multidimensional_stage tests.test_independent_skeptic_stage tests.test_predecision_cio_stage -q`：最终 93 项通过。聚焦用例覆盖正向/反证阶段隔离、审计原件或重算 hash 后的视图不一致、官方来源无数据集明细、零 Evidence 失败、筛选为空、同名多 `plane`、多标的及时间越界。
- 同一 MRVL Gate、preparation、Handoff 已在 `/private/tmp/simplify-macro-market-final.aztaIV/run` 准备新正向 run；Macro、Market 的新 packet 均通过实际 dispatch-index packet hash 与完整审计绑定校验，未改变 Evidence Catalog 或允许 ID。隔离变量字节对比见 [基线](simplify-macro-market-runtime-inputs-baseline.md)。
- 聚焦的汇总测试先加载新视图 packet，再用同 run、同 cutoff 的合法 gap 报告走现有 canonical holding research package，验证 `DOWNSTREAM_READY`。另复用已合法绑定的旧 MRVL 正反研究包，在 `/private/tmp/simplify-macro-market-final.aztaIV/cio-input-check` 通过 `prepare_predecision_cio_run` 与 `validate_predecision_cio_run`；`report-catalog.json` 包含 `MACRO_CONTEXT`、`MARKET_STATE`，共 10 个角色。该 CIO 检查验证下游契约，来源报告为旧合法样本，不声称新模型报告已经产生。
- 原正向历史 packet 经 `build_multidimensional_dispatch_packet` 读取并核对原 index hash；新 packet 经同入口核验视图绑定。独立反证同名能力仍使用原覆盖对象及原任务说明。

## 宿主真实运行与环境修复

- 使用既有宿主脚本启动本次 MRVL 多维研究：`/private/tmp/simplify-macro-market-host.wm640U/run` 成功准备 8 个任务，但模型启动前 Codex 配置解析失败，`invocation/codex-events.jsonl` 为 0 字节，终态为 `MULTIDIMENSIONAL_CODEX_PROCESS_FAILED`。
- 失败原因见该 run 的 `invocation/codex-stderr.log`：Homebrew `codex-cli 0.153.4` 在 `--strict-config` 下不识别用户配置字段 `mcp_servers.node_repl.type`。对失败 run 用 ChatGPT App 自带 `codex-cli 0.155.0-alpha.16.3` 进行单任务宿主重试，仍因同一字段在模型启动前失败；重试原始 stderr 保留在 `invocation/retries/1a22b8ec0032b016/attempt-1/codex-stderr.log`。
- 使用仅位于 `/private/tmp/simplify-macro-market-codex-home.OgTklC` 的隔离 `CODEX_HOME`，保留 `--strict-config`，仅让宿主 CLI 读取最小配置及既有认证文件的符号链接；未修改用户全局 `~/.codex/config.toml`。在原失败 run 上尝试定向重试时，模型已能启动，但原 run 因启动前失败而没有重试收尾所需的基础产物，终态为 `MULTIDIMENSIONAL_RETRY_BASE_ARTIFACT_MISSING`。该重试不是验收依据。
- 随后从同一冻结 Gate/Handoff 在独立目录 `/private/tmp/simplify-macro-market-host-fixed.qGnrxM/run` 经 `scripts/run-product-smoke.sh` 全新运行。宿主阶段 `PASSED`、进程退出码 0；8 个正向维度任务中 7 个保存，`technical_structure` 因 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 失败。`MACRO_CONTEXT` 与 `MARKET_STATE` 均为 `SAVED`，并被最终 `holding-research-bundle.json` 引用。公司研究未形成报告，技术结构失败均不由本次覆盖视图投影直接触发；不能用该阶段 `PASSED` 宣称所有维度完整。
- Macro 报告：`research/reports/a0e2fce005f99c4c/dimension-report.json`，`LOW_CONFIDENCE`/`PARTIAL`。报告引用冻结的利率、CPI/PPI、就业、零售和 MRVL SEC 证据，解释利率/通胀及经济活动对 MRVL 数据中心、通信业务的条件性传导，列出官方历史 vintage、政策正文、客户资本开支与量化敏感度缺口，并给出反向观察条件。
- Market 报告：`research/reports/0b590aa786213fe5/dimension-report.json`，`SOURCE_LIMITED`/`PARTIAL`。报告引用冻结的利率预期和大盘期权统计，明确广泛市场日线、广度、板块、跨资产、信用和新闻资料缺失，不将其外推为 MRVL 资金方向；对 MRVL 的折现率/风险偏好传导保持假设性质，并列出可推翻条件。
- `invocation/codex-events.jsonl` 的父轮次使用量为 `input_tokens=400443`、`cached_input_tokens=355328`、`output_tokens=1432`。目标子任务的 input/cache 用量为 `UNAVAILABLE`：本次 run 中含用量的原生事件只有父轮次 `turn.completed`，`subagent-events.jsonl` 没有用量字段。不能把父轮次总量归因于 Macro/Market，也不能用 packet 字节下降推断 token 节约。
- `events/mcp/events.jsonl` 提供逐 invocation 的实际工具结果记录：Macro 有 2 次 `fixture_evidence.query`，分别返回 8 和 5 个 Evidence ID；Market 有 1 次，返回 40 个。该记录支持“观察到的工具结果次数/ID”，但没有完整模型内部阅读顺序，不能称为所有可能查询的全量计数。Macro/Market 报告 `claims.evidence_refs` 分别引用 9/4 个不同 Evidence ID，可从报告回溯到 Gate。

## 待独立复核的质量风险

- 本次 Macro 报告把 2026-07 零售销售环比 `-0.54%` 作为近期活动例子，却未提及本次 Gate 中可用的更新 2026-08 `+1.24%`（`ev-research-supplement-06fd0d851849d5d2e720045ba542ae1266601c4b51b032de0425b5ee74c4139d`；其 ID 仍在 Macro 允许列表和 packet `evidence_catalog` 中）。`events/mcp/events.jsonl` 的两次 Macro 查询包含旧值 ID `ev-research-supplement-7e3cdd945faea730931b54f541b76767129054cb41c064923f47bd01c254a545`，均未包含更新 ID；前者的 `actual=-0.0054`，后者的 `actual=0.0124`、`previous=-0.0054`，观察期分别为 2026-07 和 2026-08。故可定位为本次模型实际查询选择遗漏更新观察，而非 Gate/允许列表/目录投影删除；模型为何未选中它仍无法由当前事件证明。旧 MRVL 报告曾提及 `+1.24%`，但使用不同的 source bundle/cutoff，不能当作严格同输入 A/B。当前不标记内容验收通过。
- Market 的主要来源缺口与旧样本一致，不能凭有限报告补齐原本没有的市场日线或信用数据。后续只读复核应结合两份报告和冻结 Evidence 检查重要信息保留、来源边界及输出质量；如确认有实质回退，再做最小修正并重验。

## 修正过程中的未通过尝试（不作最终验收依据）

- 正向 Macro packet 增加“描述当前状态先核对同一指标的最新可用观察”说明；Market 和独立反证的任务说明不变。多维正向 launcher 沿用 CIO 使用的 `--ignore-user-config`，同时保留 `--strict-config`、产品 `-C` 和显式 fixture MCP。聚焦测试 34 项通过；这证明命令组装和 packet 边界，不证明真实加载。
- 新运行 `/private/tmp/simplify-macro-market-acceptance.8fKSde/run` 使用同一冻结 Gate/Handoff，未设置临时 `CODEX_HOME`，其 `invocation/environment-manifest.json` 记录了上述启动参数。但 CLI 在模型启动前报 `failed to initialize in-process app-server client: Operation not permitted (os error 1)`；`codex-events.jsonl` 为 0 字节、退出码 1、终态 `MULTIDIMENSIONAL_CODEX_PROCESS_FAILED`，源码完整性未变。故 3.2 的真实加载及 3.3 的修正后报告验证尚未完成，不能拿旧成功运行或新准备产物替代。
- 用户在 macOS Terminal 运行 `/private/tmp/simplify-macro-market-terminal-20260925/run` 后，Codex 进程退出码 0、事件文件非空，但宿主阶段终态是 `MULTIDIMENSIONAL_EXECUTION_EVENTS_MISSING`。`codex-stderr.log` 记录 `unknown agent_type 'runtime_market_catalyst'`，`subagent-dispatches.jsonl` 只有一次有效派发，`subagent-events.jsonl` 未生成。首次派发缺少 `agent_type` 被 PreToolUse Hook 拦截，随后带正确类型的派发被 CLI 拒绝。这证明 `--ignore-user-config` 在该宿主 CLI 上隔离用户配置时，也未自动注册产品专家 Agent；仅依赖 `-C product` 不足以证明专家配置加载。
- 针对此故障，正向 launcher 现在从 `product/.codex/config.toml` 读取本次 dispatch 所需的专家定义，并用原配置描述与绝对 agent TOML 路径显式传入 CLI，保留原 `agents.max_threads`、严格校验和 fixture MCP；未修改独立反证启动路径。聚焦测试核对两名专家路径和参数组装。其真实加载证明见下节修复后的宿主样本，而非仅凭命令文本推断。
- 原成功运行 `run_manifest.json` 的 `company_research_import_hash=null`，8 个任务中没有独立 `COMPANY_RESEARCH`，因此该覆盖缺口来自前序公司报告未导入。技术结构在原成功运行中因 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 失败；本次变更限定 Macro/Market packet，技术结构的 `instruction` 与原冻结 run 一致，未见其失败由覆盖视图直接引起。两项非目标缺口继续单列，不把宿主 `PASSED` 写成全部维度完成。

## 修复后的宿主验收样本

- `/private/tmp/simplify-macro-market-terminal-20260925-v2/run` 使用相同冻结 Gate/Handoff、显式 `gpt-5.6-terra` 和既有 `scripts/run-product-smoke.sh`；用户提供的宿主命令未显式设置临时 `CODEX_HOME`。`invocation/environment-manifest.json` 同时记录 `--ignore-user-config`、`--strict-config`、产品目录 `-C`、显式只读 fixture MCP 及从产品配置读出的两名专家 TOML；全局用户配置未修改。实际 `SubagentStart/Stop`、`events/mcp/events.jsonl` 查询和报告 `execution` 绑定证明专家/工具/Skill 已加载，配置存在本身不作为证明。进程退出码 0、非超时、源码前后完整性一致、宿主阶段 `PASSED`。
- Macro、Market 分别在 `research/reports/a0e2fce005f99c4c/dimension-report.json` 与 `research/reports/0b590aa786213fe5/dimension-report.json` 成功保存，并由同一 `research/holding-research-bundle.json` 引用；两项任务的进程结果均为 `SAVED`。Macro 为 `LOW_CONFIDENCE/PARTIAL`，Market 为 `SOURCE_LIMITED/PARTIAL`。8 个分派任务保存 7 个，技术结构仍因 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 失败，未将阶段 `PASSED` 解释为全部研究完成。
- 新 Macro 的一次 `fixture_evidence.query` 返回 10 个 Evidence ID，其中含 2026-08 零售销售 `ev-research-supplement-06fd0d851849d5d2e720045ba542ae1266601c4b51b032de0425b5ee74c4139d`。报告的事实 Claim 明确写出 `actual=+1.24%`、`previous=-0.54%`，与 Gate 中相应观察期和值一致；不再把前值当作当前零售活动。还引用更新的 2026-09-17 利率观察，区分二级供应商当前快照与不可证明的历史 vintage，并给出 MRVL 传导假设和推翻条件。Market 的一次查询返回 36 个 Evidence ID；报告保留 FedWatch/期权统计的代理边界，以及日线、宽度、板块、跨资产和信用缺口。
- 当前新旧 packet 用同一 `jq -c` 序列化口径对比：Macro 从 308,892 字节降至 228,721，Market 从 184,671 降至 64,750；计量包含换行且只用于同口径差异，不与基线中无换行的精确字节数混用。新运行父轮次 `input_tokens=573668`、`cached_input_tokens=510464`、`output_tokens=1551`；逐子任务 token/cache 仍为 `UNAVAILABLE`，不能将父轮次总量或 packet 字节差称为实际 token 节省。
- 新 run 的 `run_manifest.json` 中 `company_research_import_hash=null`，公司报告未作为前序导入；技术结构任务输入说明与原冻结样本一致、失败码仍相同。两项维持非目标缺口分类。本次 Macro/Market 内容缺失已在真实产物中修正。

## 独立复核与验收结论

- 独立 Reviewer 只读检查最终差异、规格场景、聚焦测试、v2 宿主事件、Gate、packet、两份报告和最终研究包，未修改代码或启动额外产品/模型运行；结论为 **CHANGE_REVIEW: PASS**，仅针对本 Change 的 Macro/Market 输入消减。Reviewer 重算 coverage、Gate、packet、报告和 bundle 的 canonical hash 与内嵌值/索引一致，并确认真实 `SubagentStart/Stop`、只读工具查询、来源约束、重要信息保留及反向条件。
- 两份报告的 Claim 引用均属于各自实际查询返回的 Evidence ID。Market 摘要中的期权比率区间 `0.70–0.88` 上沿可追至已查询的 2026-09-10 观察 `0.8757`，但报告仅单列引用 2026-09-17/18 两项较新观测；这是非阻断的表达/可追溯性改进点，后续报告编辑可明确区间上沿出处，不为本 Change 扩建规则或重跑模型。
- 剩余非目标缺口为公司研究前序未导入与技术结构 `DIMENSION_REPORT_CLAIM_UNGROUNDED`（本次 7/8 保存）。逐子任务 token/cache 仍不可得，故本 Change 只证明 packet 字节下降、真实研究正常运行及内容未见重大退化，不宣称实际 token 成本下降。独立 PASS 不是用户完成批准；同步、归档、提交和推送仍待用户明确批准。
- 收尾校验：上述 93 项测试通过；`openspec validate simplify-macro-market-runtime-inputs --strict` 通过；`git diff --check` 无错误。
