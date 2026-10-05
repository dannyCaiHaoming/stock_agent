# 实施证据：配置与产品加载对齐

当前收尾（2026-10-05）：用户已明确批准同步且归档；两份主规格同步并严格校验通过。归档及限定 Git 发布正在执行，回执见 [closeout-record.json](closeout-record.json)。真实模型总预算已用 3/3，本次不新增模型；原 Smoke 版本差异和 GUI 未验证状态保留。以下按阶段保存历史状态。

### 首阶段状态记录

状态：实现及本机安装验证完成；新桌面会话观察、真实产品 Smoke 和人工完成批准尚未完成。没有归档、提交或推送。本 Change 产品模型 invocation 为 0，真实账本写入为 0。

## 授权与差异边界

用户确认方案 A，并明确“按这个 Change 开始实施”；保留全局 Git 免审批规则。任务开始时保存受影响文件原文、所有已跟踪文件 hash 和工作区状态，核对MCP/指令实施阶段仅改变 16 个已跟踪文件；其他既有修改与未完成 Change 保留。

具体前后 hash、检查状态及本机证据目录见 [implementation-evidence.json](implementation-evidence.json)。安装逐文件来源、排除范围与 hash 见 [distribution-manifest.json](distribution-manifest.json)。本机维护的原始用户配置未进入项目。

## MCP/指令实施阶段的验证（方案 B 之前）

| 规格 | 变更及证据 | 结论 |
|---|---|---|
| 研究 MCP 按运行启用 | 插件两项默认禁用；共享宿主 builder 显式启用 fixture、禁用 live，并拒绝不同 run 绑定。桌面内置 0.160.0 引擎的有效配置读取证实覆盖禁用后 fixture=true、live=false | 配置合并通过；此读取不启动服务器或模型 |
| 合法工具与拒绝边界 | 实际本地 stdio initialize → tools/list → query 成功；错误 run 身份返回 INVOCATION_IDENTITY_MISMATCH，未授权 read_reports 被拒绝；缺解释器/缺 jsonschema 明确失败 | 合成 transport 通过，非真实产品 Smoke |
| 项目解释器 | `.venv` 使用 Python 3.13.10，安装原有基础依赖；版本镜像检查通过。薄入口缺依赖输出 DEVELOPMENT_DEPENDENCY_MISSING、实际解释器及 llm_calls=0；宿主说明明确选择项目环境 | 基础环境通过；未安装可选 live/券商依赖 |
| 入口与阶段政策 | 根/产品 AGENTS、CIO 角色、角色描述、插件介绍区分独立入口、研究综合和完整 fixture Council；保留原阶段能力与研究输出限制 | 文档/配置审阅通过，未以此宣称研究质量改善 |
| 限定配置维护 | 仅删除全局已移除 js_repl 项，解析比较证实其余值不变；Git 规则 hash 不变；当前无 Guardian thread_context | 当前配置读取无该弃用警告，历史警告根因未证实 |
| 洁净发布 | 基于已发布 HEAD fcb2cf1 与本次 7 项产品文件改动生成基线；排除未提交券商/Intake/Web 改动、所有未跟踪文件及私密状态；固定交易 overlay 保留 | 来源闭包与资源镜像通过 |
| 实际安装与隔离 | 通过原生 plugin add 安装，再用既有 verify_installed_source/只读 readiness 验证注册、缓存、恢复基线和固定合成哨兵 | VERIFIED；未执行真实交易记录读写 |

### 测试与修复

- 148 项综合确定性检查通过：产品配置、共享 launcher、开发入口、交易打包/隐私、普通股实际阶段命令、资料准备 transport、多维交付接缝。
- 增加不同批准基线使用同一交易 overlay 时的安装标识与恢复验证后，42 项打包/隐私检查再次通过；该组与前述综合检查有重叠，不相加宣称测试数。
- 初轮发现三项旧测试假设：系统临时路径未 resolve、仅测 shell 引号的样例缺少真实派发夹具、Eval 提示仍使用退役输出协议。分别修正测试路径、隔离被测字符串生成与派发职责、改用当前 native-draft fixture；不恢复旧产品协议、不放宽实际路径限制。
- 版本镜像、OpenSpec strict、shell 语法与 git diff --check 通过。配置/文档引用在受影响范围核对。

## 首次安装与恢复（已被下述 Luna 包替代）

实际插件版本：`0.3.0-config.5be7c1495ae5+trading-journal.a094a81cca11`。

分发与缓存共同 hash：`0a29eeb1c835d1b1e6c75a4f76c409da24a280b1cac7e6e1265452c1db5b1adc`。

Council Skill 为 3.8.0；交易记录与复盘保持原批准 1.4.0。273 个非交易 overlay 基线文件在既有打包过程中保持一致。新的基线版本前缀区别于旧包，未修改产品候选、历史运行锁或生产晋升指针。单股功能沿用既有人工批准的“有限、可追溯首版”范围，不将安装对齐描述为更充分的研究验收。

旧完整插件、旧注册和安装隔离凭据保存在本机证据目录，`.codex-local` 也保留 previous 包及相应 baseline。恢复时使用原完整包与原注册重新安装，恢复相应隔离凭据并经既有验证，不手改 hash，不覆盖真实私人文件。未做真实回滚切换；恢复路径已通过合成检查。

## 尚缺的验收与最小下一步

1. **新普通桌面会话**：实际安装清单和桌面引擎有效配置已证实两研究 MCP 禁用；当前会话可能保留开始时的旧 Skill 目录。需在新普通会话确认 Skills 可发现且两项不自动启动。尚无这份会话事件证据，任务 5.1 未勾选。
2. **真实 Smoke**：建议先使用已有 `normal-research.json` 冻结合成输入，经宿主 launcher 执行一次完整 fixture Council，最多 1 个父运行和 2 个专业子 Agent invocation，失败不重试；使用新候选默认模型 `gpt-6-luna`，不做实时证券数据采集或账本访问。若实际调用路径无法保证该上限，应在启动前报告具体缺口。授权前先做参数及绑定检查，不发送模型请求；需明确预算授权后才能执行。此前 Terra Smoke 建议撤回；若同时验证评分，还需一次评分父运行和一次 dev_eval 子 Agent，合计最多 5 次 invocation，需另行批准，当前未执行。此样本验证共享启动、Specialist、CIO、Hook/MCP 与 fixture Risk，不证明完整真实单股研究链已重新验收。其他研究阶段复用本次受影响的确定性 transport 检查，若证据映射显示仍缺真实覆盖，先列明具体路径和额外预算，不自行扩跑。
3. **完成批准**：上述缺口消除后提交验收记录，由用户明确完成批准，再按既有流程归档和限定提交/推送。本轮不声明研究语义 PASS 或 Promotion PASS。

## 方案 B：当前 Luna 配置与安装

用户明确选择 B，将所有新产品运行与评分默认统一为 `gpt-6-luna`。路由政策为 1.1.0，当前新候选为 `0.3.0-candidate.7-luna-default`。主开发会话模型、全局 Git 放行与权限保持原样；旧候选、历史包和生产晋升指针不变。新 Runtime Eval 输入 1.1.0 与聚焦 Eval 作业 1.2.0 冻结 grader_model，父/子真实事件、草稿装配、局部修订、结果和执行证明核对同一模型；新版本缺锁/错误模型拒绝。Calibration 新 grader 身份为 1.1.0，历史身份只读保留。已有 Regression 按当前候选请求和核对模型，Promotion 核对政策版本与候选声明，未执行真实 Regression 或 Promotion。

当前安装为 `0.3.0-luna.8244243dc36d+trading-journal.a094a81cca11`，源码与缓存共同 hash 为 `919ff0b4c1c6560c1dc9a8790017662a697f57a6bdfd0751b4752ba33366cf0e`。在前一洁净基线上仅叠加 8 项产品模型文件，逐项来源见 [luna-distribution-manifest.json](luna-distribution-manifest.json)。306 个批准文件已核对，既有交易 overlay 不变；注册、缓存、可恢复基线和既有合成哨兵验证为 VERIFIED。桌面引擎有效 MCP 清单仍为 fixture=false、live=false；这不是新普通会话启动事件证明。

- 89 项模型、评分/身份、历史只读及配置聚焦检查通过；最后补强锁/Hook 后 36 项复验通过。
- 60 项打包、隐私与模型消费者检查通过，包括按当前候选实际准备零 LLM Run 与候选身份拒绝。这些组有重叠，不相加为唯一测试总数。
- 17,841 个历史运行、结果与归档文件 hash 未变化；其他既有 dirty 文件及全局 Git 规则原 hash 保留。
- 较广 fixture 检查不是全部通过。初轮 333 项有 5 failures、49 errors；模型相关拒绝随后修复，另暴露缺少可选 exchange-calendars、macOS 临时路径别名及旧断言问题。未因此安装可选依赖或改写无关产品逻辑。
- 补查 Regression/Promotion 消费者的 50 项有 20 errors，均被旧确定性 CIO 合成器读取 `validated_reports` 阻断；该函数本轮未改，当前 CIO 输入已改用 report_catalog/交付视图。此问题保留为范围外缺口，不报告完整 Regression、Promotion 或总体测试 PASS；若要修复，应另行确认范围。

本 Change 真实产品/评分模型调用仍为 0，私人账本读写为 0。配置解析与安装验证已完成；任务 5.1、5.2、5.4 的新普通会话、真实有界 Luna Smoke/评分、人工完成批准/归档推送继续未完成。


## 2026-10-05：用户确认的 Regression 交接补修

阶段 B 的原始失败记录保留；本节记录随后获准的修复，不回写此前检查为 PASS。

| 规格/边界 | 实现与真实消费者证据 | 结果 |
|---|---|---|
| 当前报告交付 | `evals/regression/runner.py` 从冻结目录构造引用，通过实际本地 fixture MCP 读取报告并记录事件，提交 native 草稿；技术身份由既有 CIO finalizer 装配 | 原 `validated_reports` KeyError 已修复，Risk 与报告消费贯通 |
| 非法引用与身份拒绝 | 报告字节漂移、未知引用、遗漏读取、读取调用身份错误的反例 | 均拒绝，不生成决策；无证明补造 |
| 零模型评分边界 | 仓库 `runtime_eval.py` 的显式 contract-only 作业绑定 authenticity=false、fixture 来源、Regression trigger 和 valid-action-contract 审计记录；准备/完成/重验共用判断 | 五维 NOT_APPLICABLE，grader=deterministic-not-applicable、model=none；普通作业缺模型结果仍拒绝；契约作业启动模型或提交模型结果拒绝 |
| 聚焦与下游检查 | Regression 19 项全部通过；CIO/评分证明/局部修订门禁 68 项全部通过；新增 3 项贯通反例检查包含在 Regression 组内 | 不将有重叠组相加；真实 LLM 调用 0 |
| Promotion 扩展检查 | 组合 37 项＝Regression 19 + Promotion 18，4 errors；Promotion 14 项通过，包括正常证据图与既有失败分类 | 未标总体 PASS，未执行真实晋升 |
| 范围与历史保护 | 本轮仅 3 个已跟踪文件变化；其他 18,625 文件 hash 未变。Luna 分发源码、已安装缓存、恢复基线及全局 Git 规则 hash 未变 | 并行修改和历史产物保留；私人账本读写 0 |

Promotion 的四个错误为悬空证据、缺 Trace、未来证据/PIT 和 Risk lineage 破坏反例；均在 `evals/promotion/runtime_gate.py:292` 重验评分证明时收到 `EVAL_LOCAL_REVISION_INPUT_DRIFT`，未捕获为可审计 FAIL。底层拒绝仍成立。本轮没有修改该失败输出行为，已单独询问是否纳入；没有答复不视为授权。

安装验证继续覆盖阶段 B 的发布范围。本次开发 Regression 使用仓库评分工具，新 contract_only 接口未发布到产品插件；不能据此宣称仓库和安装版 runtime 全目录一致。未改模型默认，未重装插件，未读取私人数据；实际配置加载、真实有界 Luna Smoke/评分和人工完成批准/归档仍保留原缺口。

日志保存在既有本机证据目录：`regression-promotion-final.log`、`regression-eval-guards.log`、`regression-seam.log`、`promotion-new-failure.log`；受影响文件前后 hash 和检查来源/时间见 JSON 的 `phase_c`。


## 2026-10-05：用户确认的 Promotion 拒绝记录修复

阶段 C 四个原异常及其“待范围确认”是当时记录，保留原文。本节记录用户随后明确答复“是”后的限定修复；不回写原失败日志。

| 规格/边界 | 实现及消费者检查 | 结果 |
|---|---|---|
| 证明拒绝可审计 | `evals/promotion/runtime_gate.py` 保留 proof hash、实际执行重验及 Eval 身份匹配；捕获 ValueError/OSError 并记录 `PROMOTION_GRADER_PROOF_REJECTED:<eval_id>:<原错误>`，沿原硬门禁生成 FAIL | 原拒绝保留，JSON 与可读报告含原因，无证明补造或评分改写 |
| 原四个失败场景 | 悬空 Evidence、缺 Trace、未来 Evidence/PIT、Risk lineage 破坏 | 全部通过反例检查：相关门禁 FAIL、总结果 FAIL，结果文件和 FAIL 标记保存，无 PASS 标记 |
| 正常通过路径 | 现有有效合成证据图与源码不变性检查 | PASS 保持，未改变产品源码 |
| 证明自身非法 | 新增 hash 篡改、Eval 身份不匹配两反例 | 均拒绝并落盘 FAIL，报告含对应错误 |
| 聚焦测试 | 原四个失败反例及正常图共 5 项通过，295.280 秒；新增证明拒绝 1 项含 2 子案例通过，80.532 秒 | 本轮 6 项通过；复用阶段 C 19 项 Regression、68 项评分门禁及未受影响 Promotion 检查，不宣称重跑完整 suite |
| 范围保护 | 本轮只修改 Promotion 工具及其测试 2 个已跟踪文件，其他 18,626 个文件 hash 未变；Luna 分发源码/缓存/恢复基线与全局 Git 规则 hash 未变 | 未重装插件、未改模型默认或历史运行，真实私人账本读写 0 |

新测试初轮因两反例复用同一 gate_id 被唯一性门禁正确拦截；已改为独立 ID 后重跑通过。初始日志保留为 `promotion-proof-rejection-initial.log`，不改唯一性条件。最终日志为 `promotion-rejection-final.log` 与 `promotion-proof-rejection-final.log`，位于既有本机证据目录；完整前后 hash、来源与时间见 JSON 的 `phase_d`。

OpenSpec 严格校验及限定差异空白检查通过。真实模型调用仍为 0；这里只验证单元测试中的 Promotion 消费与失败输出，不宣称候选已晋升。真实产品 Smoke、加载观察及人工完成批准/归档仍是任务 5.1、5.2、5.4 的未完成项，未提交或推送。


## 2026-10-05：一次 Luna Smoke 授权及准备

用户明确授权一次真实 Luna Smoke，并人工接受 Guardian 弃用提示不再作为完成阻断；这不是新普通会话加载已验证，也不代表已核验 Codex bug 根因。按此前已拟定方案采用 normal fixture，最多 1 父 + 2 Specialist 共 3 invocation，失败计入预算，不重试，不执行评分/live/Replay/晋升。当前 prepare 已通过并冻结 gpt-6-luna 与真实性要求；运行目录为 `/private/tmp/config-luna-smoke-12a2067eba74454f/run`。

宿主 Terminal 自动操作被工具安全限制拒绝：`Computer Use is not allowed to use the app com.apple.Terminal for safety reasons`。未使用其他技术绕过限制，真实模型调用仍为 0。宿主命令已准备在 `/private/tmp/config-luna-smoke-12a2067eba74454f/launch-command.txt`，用户启动后继续核验原始模型/Skill/MCP/Hook、执行证明、Risk、Trace 与终态，5.2 保持未完成。运行授权、来源/时间和 manifest hash 见 JSON 的 phase_e 及本地 smoke-authorization.json。

用户随后明确授权以 shell 自动启动同一现有宿主脚本；保持原 run_id、模型及 3 invocation 上限、不重试。此前 Terminal GUI 限制记录保留；本次不再操作 GUI，也不改写启动后端。


## 2026-10-05：真实 Luna Smoke 执行结果

用户随后明确授权用 shell 自动处理，直接执行现有宿主脚本，同一运行仅启动一次；此前 GUI 拒绝及零调用记录保留为当时状态。运行 `config-luna-smoke-12a2067eba74454f` 耗时 133.707 秒，shell 和 Codex 退出码 0，原 process/check-run 结果 PASSED。真实 invocation 为 3（1 父 + 2 Specialist），已用完授权上限，无重试，不启动 dev_eval、Execution Replay 或 Promotion。

- Parent、Company Analyst 与 Skeptic 的实际模型均为 gpt-6-luna；两 Specialist 独立会话与并行派发通过原执行证明校验。
- AGENTS/Skill/资源加载及派发 guard 检查通过；两 Specialist 均实际 query，CIO 实际 read_reports 与 query，native 草稿由运行层装配。
- CIO 因资料不足输出 NO_TRADE / INSUFFICIENT_EVIDENCE，合法终态 SAFE_NO_TRADE；Risk APPROVED，报告消费、Evidence、Trace 和原生确定性产物检查通过。此状态不是运行失败，也不证明研究充分或投资质量通过。
- 运行前后受保护产品文件 hash 一致。原始 Prompt/事件只保留本地，项目仅记录最小摘要与完整 hash，无真实账本访问。
- 当前统计 input_tokens=723921、cached_tokens=661504、output_tokens=4072，来自现有父 turn.completed 计量；不推算未观察到的全链消耗或费用。

**具体限制：** 实际启动选择桌面内置 CLI 0.160.0，但 `product/version-manifest.json:4` 仍声明 codex-cli/0.153.4；`execution_proof.py` 的 ephemeral 分支沿用该声明。模型、生命周期及工具调用有真实事件，CLI 版本字段却不是独立测量。原产物不回写；本次 Smoke 启动与加载目标通过，不能据此宣称 CLI 锁准确、候选可晋升或新普通桌面会话已验证。该配置/证明差异保留为 OPEN，若修订新候选应使用新身份，不借用本次已耗尽模型预算重跑。

本地最小摘要：`/private/tmp/config-luna-smoke-12a2067eba74454f/smoke-summary.json`；原运行报告：`/private/tmp/config-luna-smoke-12a2067eba74454f/run/report.md`；最终确定性检查：`/private/tmp/config-luna-smoke-12a2067eba74454f/final-check.json`。JSON 的 phase_e.result 包含来源/时间、模型、budget、检查范围及底层文件 hash。任务 5.2 完成；5.1、5.4 保留未完成。


## 2026-10-05：新普通会话与 CLI 版本核验验收

用户已选择更新后续候选 CLI 锁为 0.160.0 并补启动前核验；保留原 Smoke 差异，不增加模型预算。以下结果对应当前两项请求，原历史段落和失败日志保持当时事实。

| 验收项 | 实际依据及结果 | 范围 |
|---|---|---|
| 新普通会话 Skills/MCP | 同一桌面内置 CLI 的新 app-server ephemeral thread/start 使用普通项目配置与已安装插件；skills/list 返回 15 个产品 Skills、零错误；mcpServerStatus/list 两研究服务均 disabled、工具数 0 | LOAD_VERIFIED；没有 turn/start。新普通引擎会话通过，桌面 GUI 因工具安全限制仍 UNVERIFIED |
| 后续候选版本锁 | 源码和洁净安装 manifest 的 candidate=0.3.0-candidate.8-cli160、codex_runtime=codex-cli/0.160.0 | 不升级系统 CLI；旧 candidate.7 与已完成运行锁不变 |
| 模型前 CLI 拒绝 | 实际桌面二进制 --version 核验为 0.160.0；实际终端默认 0.159.3 返回 CODEX_RUNTIME_VERSION_MISMATCH；本地正反例涵盖未知、缺失、失败与漂移记录 | 各当前宿主模型 launcher 共享核验包装，记录二进制/版本/锁来源/hash；失败不返回可启动模型的命令 |
| 新 ephemeral 证明 | 读取并绑定宿主测量记录及 hash，父/子 CLI 字段来自该记录；缺失、hash 漂移、跨 run 或不匹配拒绝 | 子 Agent 的来源是同一宿主进程内嵌 Runtime；未声称 Hook 独立提供 cli_version；历史已保存证明不改写 |
| 聚焦检查 | 核心 62、宿主阶段 8、隐私/打包 42 项通过；当前版本镜像与 OpenSpec 严格校验通过 | 全部零 LLM；不把重叠或扩展组相加，不报告完整 suite PASS |
| 洁净安装与隔离 | 仅此前已批准 Luna 基线增加 8 个 CLI Runtime 文件及候选/插件元数据；实际注册、源码/缓存身份一致，原交易 overlay 相同，合成隔离和恢复基线有效 | 未读取或写入真实账本；仓库开发 contract-only runtime_eval 补修仍未发布，不能称整目录相同 |
| 历史与范围保护 | 原 Smoke manifest 和全部已索引产物 hash 未变；本轮其他已跟踪文件和全局 Git 规则 hash 未变 | 不改原 Smoke、其他 Change 或开发选模/权限；无归档/提交/推送 |

安装版本：`0.3.0-cli160.cc2d13a850a6+trading-journal.a094a81cca11`；源码/缓存 hash=`806c7af6105b89d4f84a52162ef3de66d03fb7ae8813b5bf549472b42e19ab5a`，恢复基线 hash=`aa61b5a6ddefae7423c1b17f10de43af21537afd517159aee35a04891f041701`。新会话最小记录为 [normal-session-loading-observation.json](normal-session-loading-observation.json)，批准分发差异为 [cli160-distribution-manifest.json](cli160-distribution-manifest.json)。底层本机产物和检查 hash 见 JSON phase_f。

扩展 assurance 组 70 项中的一个旧检查失败：demo/runner.py:170 的合成 thesis/action/confidence 字面值被现有架构扫描器拒绝。此前批准的洁净基线产生完全相同拒绝，文件字节未变化；这是范围外既有问题，未顺手修复，未报告该组通过。初轮 fixture/路径/import 和误指定不存在测试模块的错误日志保留，最终相应聚焦检查已通过。

**验收结论：** 当前请求的新普通引擎会话加载与后续 CLI 锁/启动前核验通过。旧 candidate.7 的 Luna Smoke 仅复用未改变的研究模型/Skill/MCP 行为以及实际 0.160.0 引擎执行证据，原声明差异不消除；candidate.8 的新 CLI guard/测量证明由确定性检查验证，未宣称重新运行真实 Smoke。真实总调用仍 3/3，candidate.8 的真实 Smoke、Execution Replay、语义评分与 Promotion 均未执行。最后仅保留 5.4 人工完成批准后的归档/规格同步与限定提交推送。
