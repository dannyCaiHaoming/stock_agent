## 当前设计

当前仅执行[Proposal的非成功需求处置](proposal.md)；D7保留已完成第9节的依据，不再授权新的裁剪、交接或研究。原五项义务按D8归属，当前状态仅见[Tasks](tasks.md#当前状态)。

### D8. 五项未完成义务与非成功实体归档建议

| 原未完成项 | 保留义务及明确承接位置 | 停止或另行保留部分 |
| --- | --- | --- |
| 6.1 准备与授权 | 新Change [Design D9](../simplify-repository-for-claude-native-product/design.md#d9-原51的固定验收节点规划不启动运行)及Tasks 5.1.1承接Claude就地加载、当前模型映射、原样本、绑定、权限和有界运行授权核对 | 外置源码候选/新包/重复安装准备停止；旧opus映射只属于其历史阶段，不硬套当前配置；Codex/OpenCode准备另按host-backlog授权 |
| 6.3 Claude原生实际组合 | 新Tasks 5.1.1–5.1.4承接专业白名单、Skeptic独立首轮、任务授权/来源/PIT/计算、合法报告及完整精确读取、同一主线程CIO与原fixture Risk、独立MRVL Market | 不另开旧Change独立窗口，不以静态修补或其他宿主报告抵充；原失败保留 |
| 7.1 原稿内容核对 | 新Tasks 5.1.5承接上述Claude原稿核心依据、期间/单位、方向/幅度、重要反证和限制，业务/执行/内容分列 | Codex/OpenCode原稿内容继续在[host-backlog](host-backlog.md)待后续；完整八维、ALB质量与非ALB泛化不由迁移认证 |
| 7.2 映射与人工完成 | 新Tasks 6.1结合已完成2.x/3.x/4.x的实际消费者/测试/历史保真依据，承接有限Claude结果、遗留披露及一次人工完成批准 | 旧Change不再另行复制同链路验收或以第9节完成补勾原7.2；其他宿主后续独立完成条件仍保留 |
| 8.1 主规格/归档/发布 | 新Tasks 6.2只在其必要验收和人工完成批准后同步**新Change**契约、成功归档及限定发布，原审阅/敏感/共享hunk门禁保留 | 旧八delta全量同步路线停止；旧实体仅按下述非成功处置另批，不以新Change成功回签原8.1或自动触发旧发布 |

本表不取消五项全部义务，也不把原未完成任务改成完成。原Specs保持历史原件；接替方的现行契约才是新迁移实施依据。其他宿主的原6.2/6.4及内容义务已在host-backlog保留，非本次新增完成前置。

**实体归档的单一建议（尚未授权执行）**：另获用户对“非成功实体归档、跳过旧主规格同步、保留未完成勾选及历史链接”的明确批准后，使用现有 `openspec archive simplify-agent-package-for-native-hosts --skip-specs --yes`，保留默认校验，不使用`--no-validate`。本机OpenSpec 1.12.0的help和archive实现已核对：`--skip-specs`跳过主规格更新，未完成任务可经显式确认/`--yes`继续，实际动作是移动整个Change目录到日期归档目录；没有据此认定存在“superseded”成功状态。执行前须确定当日目的地并检查迁址链接：非原始规划/说明与外部入链按批准范围修正相对路径，原运行记录中的历史路径/字节不改，原始证据随目录完整保留；工具本身不负责Markdown链接重写。无法保留可追溯性则停止实体归档，不先移动再补证。本轮不执行命令、不移动/删除原件，也不请求或执行Git发布；后续非成功归档的Git处置须明确另批，不借成功归档发布委托自动推送。

### D7. 旧 Change 的限定精简与并行边界（2026-10-09）

以下D7保留第9节当时的决策与执行措辞，仅作历史依据；当前处置及禁止继续实施以本页D8和Tasks当前状态为准。

本节维护限定精简的稳定决策与具体责任；目标/授权见[Proposal](proposal.md)，唯一执行清单及结果见[Tasks第9节](tasks.md#9-限定精简已完成记录)。D1–D6及原Migration Plan是停止路线的历史设计，不重新执行。

#### D7.1 精简判断与责任分区

审计确认偏移主要来自把外置源码候选/反复安装、多宿主排障、完整研究前置和重复进度/hash清单变成日常控制面，不是所有JSON/Markdown或业务抽离均无价值。授权、Gate/PIT、来源、数学、精确提交/完整读取、历史与隐私保持；原生宿主仍负责模型与专业执行。采用残留驱动裁剪，不重新实施整份D5矩阵。

| 具体候选/职责 | 当前消费者与处置理由 | 覆盖、写入归属与绑定 | 验证依据 |
| --- | --- | --- | --- |
| `product/runtime/nested_codex.py::launch_nested_codex`；五个研究Stage的`launch_*`、`common_stock_stage.py::_run_bounded_process_group`、`predecision_cio_stage.py::_run_cio_process` | 当前函数体只明确拒绝旧正常执行，不创建模型进程/运行目录；保留公开入口的失败行为，不再有可裁的正常执行体 | 原5.1与接替3.2已覆盖；共享源码，本节只读，不重复计作新删除 | 当前AST函数体及`tests/test_native_entry_retirement.py`的直接API/CLI/无隐藏回退负例 |
| `product/runtime/codex_hook_recorder.py::handle_hook_event`、`_handle_eval_dispatch`、`_capture_eval_output`；`nested_codex.py::build_verified_nested_codex_command` | 普通研究与混合评分flag在I/O前拒绝；现存Hook仅处理`dev_eval`。`common_stock_eval.py::launch_common_stock_eval`及CLI`launch-common-stock-eval`仍实际消费评分命令与锁，不是正常研究后端 | 接替3.2负责；共享显式维护保留，本节不运行或修改Eval | 读取分支、CLI/调用者及`test_native_entry_retirement.py`、`test_nested_codex_launcher.py`；不能按Hook/nested名称整删 |
| `product/runtime/entry_policy.py::reject_legacy_entry`；`environment_preflight.py`探针拒绝壳；`scripts/run-product-smoke.sh` | CLI和`council-dev.py`先行拒绝旧正常模型/沙箱命令；两个旧探针API由`test_development_environment.py`验证副作用前拒绝。Shell只保留显式冻结Replay和Tiger只读入口，正常阶段串联已不存在 | 接替3.2及既有退役覆盖；共享实现保留，不启动维护/券商。`environment_preflight.py`同名旧检查当前无项目调用，不据此删除其兼容模块 | 定点调用搜索、读取Shell与拒绝体；`test_native_entry_retirement.py`及环境拒绝负例 |
| `multidimensional_stage.py::read_multidimensional_task_state`；`tests/test_multidimensional_task_state.py`、`test_single_stock_input.py` | 当前生产源码未找到状态函数调用，两个测试仍验证冻结事件只读投影/hash/独立单股身份；MCP状态工具已退役。读取既有事件不派发/等待/推进状态，保留历史检查，不因正常路径不调用而整删 | 接替3.2负责生命周期工具退役；共享历史兼容保留 | 函数读锁/只读体、MCP拒绝及可信/篡改历史fixture；测试提供历史Start/Stop，不由业务保存伪造 |
| 各Stage的`build_*_dispatch_packet`；`independent_skeptic_stage.py::_skeptic_task_prompt`；`predecision_cio_stage.py::build_predecision_cio_prompt` | `multidimensional_references.py`、`fixture_mcp.py`消费业务包；Skeptic历史准备/恢复及CIO旧锁重验仍消费历史Prompt，后者在原读取器比对`prompt.txt`。旧父调度Prompt已裁，不把所有含dispatch/prompt的函数当控制器 | 接替3.2已处理正常控制；共享引用/历史职责保留，不改变冻结算法 | 精确调用搜索、CIO锁读取分支及对应历史/引用负例 |
| `calculation_handoff.py`、`monetary.py`；`research_submission.py`、Stage、`fixture_mcp.py`、`product/tools/evidence.py`调用 | 实际业务消费者已从Hook改用计算/金额模块；授权、PIT、来源、单位、引用和提交仍有业务用途，不是新增Agent架构 | 接替3.1与旧工具抽离已覆盖；共享业务保留 | 当前导入闭包；复用[接替验收记录](../simplify-repository-for-claude-native-product/acceptance.md#对应确定性检查及原失败)中的受影响检查，不宣称本节重跑全部业务 |
| `product/tools/package_content.py::export_package/prepare_claude_workspace/main`及导出/就地测试 | `main`明确区分`--target`可选分发和`--in-place`当前就地入口；导出仍有实际CLI/测试用途，不能因其不再是本地前置而删除 | 接替2.1/4.2负责；文件在任务资源绑定内，本节不改生成器/配置/派生发现或重签任务 | 当前CLI分支及`test_native_package_export.py`、`test_native_product_workspace.py`用途；不执行安装/刷新 |
| `product/tools/research.py`、`research_connection.py`、`report_submission.py`及`product/mcp/research.py` | 准备/路由/查询/计算/提交/精确读取，不派发模型或维护RUNNING/WAITING生命周期；业务范围/凭据与两稿限制仍必需 | 旧2.x/3.6及接替2.2已覆盖；全部tools、Schema、角色/Skill、MCP、版本与Risk均受`resource_bindings.py`绑定，任何共享写入需明确交接 | 当前职责/调用搜索及既有授权、分页、提交读取证据；不以文件数或新增LOC判冗余 |
| `tests/test_specialist_dispatch.py`、`test_specialist_start_context.py`、`test_codex_runtime.py`、`test_research_terminal_projection.py` | 现存断言分别保护旧正常拒绝、历史输入/回执/漂移、显式评分二进制锁，以及报告→网页的业务/作者/内容分列；不是一组可整体删除的控制专属测试 | 接替3.2/4.1已收敛；相关实现及测试共享，本节不重复改动 | 读取实际测试而非只看名称；业务/历史/隐私负例保留 |
| 本旧Change的`proposal.md`、`design.md`、`tasks.md` | 当前目标/授权、稳定责任、任务进度各归一处；历史原件只保留已有链接，不再逐轮生成状态/hash副本 | **本节唯一已确认可独占写入范围**；不属于产品任务资源绑定 | 三文件差异、原1–8节状态/历史正文、122份其他旧文件不变及本地链接/格式 |

本表依据第9节apply后的当前源码、CLI、实际测试及接替当前Tasks核对；接替3.1/3.2/4.x已覆盖，5.1真实验收仍未完成，其最新窗口停止不转成本节任务或授权。旧D5/D6重点候选中未发现未被覆盖且可独占等价裁剪的真实控制执行体；本节代码/测试删除为零。没有确认必须在本节修补、却因共享交接未完成而隐去的缺口。进一步改变历史API、可选导出或原生加载须先由接替责任方确认具体函数/hunk与稳定来源；不因其会话idle或窗口已关闭推定已交接。

#### D7.2 共享写入必须交接

- 接替目录及产品源码/Skills/角色/Schema、配置/发现、版本和相关脚本/测试只读；不同文件/hunk不等于安全。`resource_bindings.py`实际绑定全部tools/Schema及角色、Skill、MCP、版本、Risk等资源，写入可能导致RESOURCE_DRIFT。
- 共享修改须先明确函数/hunk责任、稳定来源和准备/运行不受影响的交接。会话idle或窗口关闭不等于交接；本节不关闭窗口、杀进程/重连、改模型/预算、删除资源锁、重签任务或刷新连接，也不让另一任务停机、重排或让出预算。
- 确认必需而未交接的项保持未完成，只暂停依赖项；无独占缺口时零代码改动是有效结论。上表没有本节必需的未交接项，进一步共享裁剪由原责任方另行确认。

#### D7.3 当前记录归一，原件保持

三规划各自职责见Proposal；原1–8节勾选、历史授权/失败及辅助MD、原报告/JSON/日志/锁保持原路径和字节，历史正文折叠而不删改。需要核对证据时沿已有链接读相应原件，不逐轮复制全文/hash表，也不新建索引、结果文件、候选、证据数据库、清理脚本或快照平台。定点hash仅防误改，不是OS保护或加载证明；物理删除/移动任何原件均不在本轮，另提非原始可再生项也须列具体路径、消费者、恢复方式和影响后另批。

#### D7.4 执行与收口

按[Tasks第9节](tasks.md#9-限定精简已完成记录)顺序验证后勾选，检查命令/范围/结果只记在该节；不恢复原五项。等价裁剪保留公开退役拒绝、实际历史/维护与全部业务负例；需要新增行为或改契约/加载/运行的候选须额外规划批准。第9节必需共享缺口不能用“列为交接”替代完成；闭合后仅报告限定精简完成待人工确认，原迁移处置及八份delta归属另批，不与接替重复同步。

<details>
<summary>原迁移设计 D1–D6、风险与迁移计划（历史；按需展开）</summary>

## Context

动机与范围见 [proposal.md](proposal.md)。本设计是跨模块迁移，涉及调用方身份、独立输入和历史兼容，不能按纯目录重命名处理。

### 初始规划授权与现场（历史快照；后续明确授权见Tasks）

- `source_id`: `user-priority:native-agent-package:20261005`
- `as_of`: `2026-10-05`
- `retrieved_at`: `2026-10-05`
- 用户明确本需求优先，其他需求完成本项后再调整；本次仅创建规划，尚无 apply、安装或模型预算。
- 当前工作分支是 `main`，已有并行 dirty 内容，不清理、stash 或整文件覆盖；其他活跃 Change 不修改、不勾选、不归档。配置加载对齐已由用户声明完成且不再列为活跃项，不重开。
- 自有产品源在 `product/`；外部 OpenSpec/Skill 只读，私人账本、账户配置与原模型转录不用于本次公开盘点或分发。

### 2026-10-06 安装前接缝补验授权

用户在只读核对后明确选择“MRVL＋补齐接缝”：MRVL既有公开冻结资料作为三宿主候选，保留原SOURCE_LIMITED/BLOCKED_CONFIGURATION及缺正文范围；允许在本Change已批准的D5/D6内继续代码接缝修复和聚焦确定性验证，仍不联网取数、不实际安装产品包、不运行产品模型、不覆盖用户配置或原备份。具体补验是从common_stock_data逐函数拆出同行所需的raw-cache闭包校验和补充事实合并，旧调用者共享同一函数及错误类型；完整导出测试显式包含操作方prepare/material入口并排除并行broker Schema。不得用动态import或减少声明范围掩盖旧控制依赖，不新增模型后端、Provider、Agent或主观判断。6.1安装/模型预算及真实验收未完成，补验不提前勾6.x或回签旧证据。

### 已观察到的职责混合

- `nested_codex.py:332` 构造 `codex exec`、MCP、Hook、状态目录和输出 Schema；`launch_nested_codex` 再创建模型子进程。
- `run-product-smoke.sh:334–367` 在单股链中依次启动资料、Company、多维、Skeptic、CIO，完整路径声明五次宿主父调用；并非只提供一次测试命令。
- `common_stock_stage.py:1676`、多维/反证阶段 Prompt 指导原生委派，但阶段本身仍由新的宿主进程承载；存在业务准备与启动控制叠加。
- `codex_hook_recorder.py` 同时负责派发校验、上下文交付、提交捕获、局部纠正、父停止门禁和状态来源；正常报告接受与特定事件绑定。
- `research_submission.py:875` 已有写前任务凭据检查、精确回执和原稿保护，但 `resolve`/`mark_accepted` 依赖旧 Stop 记录。源码明确 bearer 不是实际 MCP caller authentication，不能把去 Hook 理解为仅保留 task_name 就足够。
- `fixture_mcp.py` 已有事实查询、计算、报告读取/提交能力，也混有生命周期快照。现有业务能力优先抽离复用，不另建相同数据工具。
- `tests/test_nested_codex_launcher.py` 固定旧命令/Hook/目录形状；`test_native_execution_proof.py` 混合历史证据读取和执行事件验证。大量语义/权限/计算测试也导入旧控制模块，不能按文件名一刀切删除。

只读发现中一次 Python 子进程无法找到 shell 中的 `rg`；后续直接用 Python 文件扫描完成依赖盘点，没有改源码、安装依赖或运行测试。以下是规划证据，不是实施或研究 PASS。

## Goals / Non-Goals

**Goals:**
- 让正常产品路径只包含共享研究内容、宿主原生执行和确定性业务工具，彻底解除对项目创建的宿主模型进程依赖。
- 在三个宿主各自原生配置中表达同一组现有职责与权限，不抽象成通用 executor/adapter framework。
- 将业务身份、实际工具收据、原生执行观察和内容裁定分开，既不伪证也不因没有 Codex 日志误判合法原生报告。
- 保留既有输入、资产覆盖、金融/PIT/引用/隐私/历史读取，降低控制代码与相关测试的长期维护量。

**Non-Goals:**
- 不新增 Agent 职责、Provider、市场、ETF/期权研究、账户决策或买卖建议能力；已实现 fixture 风险契约不放宽，真实研究仍 `RESEARCH_SYNTHESIS`/Risk NOT_RUN。
- 不实施暂停的证据质量 v3、列表刷新、交接节费、历史建议或 Tiger API 实机验收；发现这些问题只保留限制，不趁迁移补做。
- 不统一三宿主的全部功能、模型、Hook、会话 ID、usage、审批界面或日志格式，不承诺外部执行永不慢。
- 不建设新评委、mock Agent 调度平台、常驻服务、后台刷新、全仓快照前置或用户配置管理器。
- 不修改历史数据、Schema、包、失败证据、转录、数据库或生产晋升指针，不自动启动专项评估。
- 不为本 Change 补齐研究来源、增加 Fed 离线正文/新文档类型/材料准备入口或治理整体投资研究质量；三宿主最小合法切片验收与完整公开股票八维研究分开，后者的业务依赖及成功条件不改。

## Decisions

### D1. 当前宿主是执行者，不是 Python 调度的后端

共享 `portfolio-council` 维护产品输入、研究依赖、阶段停止、反证方法和综合职责。当前主线程使用该宿主的原生委派/等待/结果回收；Python 只准备和验证业务对象，不保存或驱动通用模型任务生命周期。

保留“先有合格 Company/多维/独立反证，再显式综合”的业务依赖，不保留 Shell/Python 的五个父进程串联。业务 request/run/任务标识仍用于证券、cutoff、允许集、报告及修订绑定，不再等同于必须创建一个宿主进程。调用数由实际授权与宿主观察约束，不能按旧五父模型路径推算新成本。

未选方案：给 Codex/Claude/OpenCode 各写 executor，然后统一派发、等待与事件。这会重建同一层控制系统，禁止采用。把全部校验放入 Prompt 同样不采用。

### D2. 一份正文，三份薄的原生配置

保留 `product/skills/` 为共享自有方法源；新增 `product/agents/` 的四份职责正文，来源为现有 Company、Market、Skeptic 和 CIO 定义。正文包含研究职责、Skills、工具需求和结构化返回，不包含 `fork_turns`、`wait_agent` 参数、Codex Hook 键或 CLI 命令。

`product/hosts/{codex,claude-code,opencode}/` 仅容纳原生模板及安装/能力说明。Codex 使用其 TOML，Claude Code/OpenCode 使用各自 Markdown/frontmatter/配置；CIO是当前主线程角色，不增加 CIO 专家调用。发布期可做最小正文展开/复制与只读一致性检查，不做运行期事件转换、自动宿主检测或多平台 DSL。不能产生三份独立编辑的研究方法。

安装从明确批准的包源导出到用户指定位置，沿用现有洁净分发与 `.private` 排除；当前 `.claude/` 及用户级配置不是可覆盖目标。前三个宿主的发现目录不同，不能只建立一个目录就声称都能加载。模型由宿主及用户选择，旧锁和评分身份保持原样；缺实际模型观测不由字符串补证。

2026-10-05 只读官方依据：
- [Codex Skills](https://learn.chatgpt.com/docs/build-skills)：共享 `SKILL.md`，Codex 发现 `.agents/skills`，OpenAI 专属扩展另存。
- [Codex Agents](https://learn.chatgpt.com/docs/agent-configuration/subagents)：原生 TOML 与宿主委派；文档不能替代实际上下文/权限观察。
- [Claude Code Skills](https://code.claude.com/docs/en/skills) 与 [Subagents](https://code.claude.com/docs/en/sub-agents)：原生 `.claude` 内容、角色工具面；插件部分权限字段可能被忽略，Skill 的 allowed-tools 也不等同硬白名单。
- [OpenCode Skills](https://opencode.ai/docs/skills/) 与 [Agents](https://opencode.ai/docs/agents/)：支持共享 Skill 位置，角色/任务权限独立；公开文档没有充分说明首轮历史继承范围，不能先宣称隔离。

这些是目标配置依据，不证明本机三个版本实际支持；apply 后只读核验已安装目标版本和对应参数，不自动安装、升级、切换模型或改全局安全设置。

### D2.1 Claude Code桌面入口的私有连接绑定补齐（2026-10-07）

用户明确要求在当前Claude Code桌面端继续开发调试并回复“继续”。独立CLI认证失败仅阻断该次CLI尝试，不是桌面开发或原生研究的前置；不再启动独立模型CLI、要求CLI登录或迁移桌面认证。沿用D2/D3的薄配置、业务授权及私密排除范围，补齐桌面项目直接发现的接线：

- `product/mcp/research.py`增加可选`--connection-env-file`，仅与既有`--connection-env-prefix`结合使用。从操作方已经批准的仓库外私有JSON读取当前角色的一对CONNECTION/TOKEN，复用既有私有目录/文件校验、请求/Gate/角色重验，不加载其他键到进程环境。文件模式、路径、缺字段/错误角色失败时脱敏拒绝；显式文件失败不得回退环境。原环境绑定与旧单任务接口不变。
- `product/tools/package_content.py`在Claude导出中接受显式服务名→私有连接环境文件绝对路径映射，仅为指定服务派生`.mcp.json`，去除未绑定的环境插值并添加业务MCP的文件参数。导出器不读取或复制私有文件；该映射不是Agent调度、宿主状态或多平台DSL。其他宿主和未指定映射的旧导出保持原行为。
- 桌面研究仍通过项目`.claude/agents`、`.claude/skills`、`.mcp.json`及原生权限发现，用户已有开发/全局配置不改。MCP原生准入、同名服务优先级、主线程只读权限和角色实际工具面必须在目标桌面产品会话观察；不能仅凭本地stdio/文件生成判加载PASS。任务交付凭据仍在私有packet，不写源码或公开记录。
- 先以实际stdio正负例及洁净导出验证无环境注入时的连接、写前拒绝、秘密不回显、不复制及旧路径恢复。新源码资源绑定需要新业务任务，不能用旧任务或旧安装回签。既有安装保留，新的桌面安装采用精确源，实际产品模型窗口另按有效授权核对，不沿用已停止/过期CLI窗口。

### D2.2 Claude主线程指引必须随包加载，不把可选隔离当必选（2026-10-08）

用户在worktree派发失败后明确要求检查原因、调整需求并修复。实际失败调用显式传入`isolation=worktree`和`model=opus`；前者触发非Git产品副本的worktree创建错误，后者偏离角色已有的`model: inherit`。2026-10-08只读官方Subagents文档说明普通subagent从主会话当前目录启动，worktree为可选隔离，调用级model优先于角色定义。展示类型中的联合值不等于实际JSON Schema的required集合，不能仅因未展示本地枚举或可省略标记推定宿主强制worktree；当前桌面实际接受省略参数尚未运行验证，仍单列UNKNOWN。

沿D2的薄宿主配置边界，在`product/hosts/claude-code/main-thread.md`维护短的原生操作指引，Claude导出时将其原字节拼入根`CLAUDE.md`，位于产品规则之后、CIO共享正文之前。指引只要求使用已加载专业角色，未授权额外隔离/换模时省略调用级isolation/model，以角色的inherit定义及宿主实际配置为准；不把worktree、remote、Git初始化、hook或新模型进程作为普通研究前置。真实缺字段拒绝和签名冲突原样报告，不自动补参数、重派或续期。

新增指引必须在精确审阅清单内，缺失或hash漂移在创建新导出目录前拒绝；不在运行时生成参数、调用Agent、读取宿主私有数据库或修改旧安装。其他宿主入口保持原字节，公共Skill和四角色正文不混入Claude参数。确定性检查只证明指引→导出根入口的交付、缺源/漂移拒绝和旧路径不变，不证明主线程遵从、原生参数接受或研究执行。旧失败原记录保留；后续安装及真实窗口仍按有效授权执行，当前Claude验收、其他宿主遗留义务和最终人工完成标准按D4.1处理。

### D2.3 Company调用端使用原生fork Skill固定角色，不让模型再选择派发参数（2026-10-08）

用户明确要求“查清楚为什么还会传错参数，把调用端问题修好”。指定产品会话的两次原始Agent tool_use均已带有worktree/opus；其2026-10-07两份原生prompt_snapshot中Agent input_schema的required只有description/prompt，可选字段无default。Skill input_schema则只允许skill/args且additionalProperties=false。因此“工具要求填写这两个字段”已被排除；两次错误字段在原生调用记录层已存在，但echoWireToolInputs=false，未取得Provider wire输入或上游转换实现，不将其进一步定性为已证实的模型/桥接缺陷。D2.2指引交付和真实加载成立，未阻止误参，不能继续靠同样提示重跑。

沿D2允许的原生配置与安装映射修复这个接缝：

- 新增`product/hosts/claude-code/skills/company-native/SKILL.md`，仅用宿主原生frontmatter的`context: fork`、`agent: runtime_company_analyst`固定现有专业角色，`background: false`让本次Company切片由宿主等待结果，`user-invocable: false`将它作为主线程内部入口。正文只交付`$ARGUMENTS`中的完整本次任务和授权边界，不复制研究方法、正文或生成模型参数，不新增专业职责。
- 本入口不设置model/isolation/permissionMode/allowed-tools/hooks。角色沿用原`model: inherit`、共享角色正文、五Skill与精确业务工具；宿主执行自己的创建/等待/审批。不修改宿主二进制、认证、权限、全局配置，不新增Python派发器、参数改写Hook、SDK、子CLI、重试或生命周期平台。
- 主线程的Company调用改为原生Skill(skill=company-native,args=本次问题、cutoff、精确任务授权、预算和停止点)，不再为Company构造Agent调用。缺入口/角色、原生拒绝或研究失败就停止，不回退同一误参路径、不自动重派或续期。其余角色仍按原有入口，CIO仍为显式综合时的主线程。
- 导出只把精确审阅的该Claude源原字节映射到`.claude/skills/company-native/SKILL.md`；缺源/hash漂移/与共享Skill同名冲突在目标创建前拒绝。Codex/OpenCode不安装这个宿主入口，旧安装不修改，专业定义和共享研究方法不变。不要把Skill的context fork与Agent(subagent_type=fork)继承父历史混为一谈；本次仅Company，不据官方说明宣称Skeptic实际隔离已验证。
- 官方Skills文档说明context fork Skill内容作为任务prompt、自定义agent决定system prompt/model/tools/permissions，不继承主对话历史；这是配置依据，不是本机2.1.289执行证明。确定性测试验证真实捕获Schema、原生frontmatter/角色绑定、精确导出、拒绝/恢复及其他宿主不变，不模拟Agent或启动模型。原生入口发现、角色/五Skill/工具权限、实际模型、回执和报告内容仍须在另获有效窗口的产品会话观察，6.x/7.x/8.1保持未完成。

脱敏证据仅保留工具Schema、参数键及技术枚举、时间/id/hash，不保存prompt、凭据、完整metadata或原始会话。原失败记录按原时点保留，当前发现另记增量，不无痕把旧UNKNOWN改成PASS。

### D2.4 Company项目角色显式引用已有MCP连接（2026-10-08）

用户在新窗口确认请求后明确授权继续完成Change及所有授权。本次原生Skill只有skill/args，实际发现成功；03:20:40Z宿主在创建作者前返回`would be spawned with zero tools`，11项Company工具均被列为unrecognized。指定原生快照此前注册过这11个精确名称，因此不是已证实的拼写错误；快照早于本轮，不能证明本次子任务工具池、父连接继承或宿主内部实现。原始失败保留，业务query/计算/提交/报告均0，失败窗口停止。

沿D2允许的项目原生配置作最小修补候选：只给Claude Company项目角色增加`mcpServers`字符串引用`company`，显式复用项目中已有连接；不内联服务器定义、不复制连接或任务凭据，不增加服务/Provider/工具，不换模型或使用通配白名单。原11项tools、五Skill、共享正文、company-native入口和其他宿主保持不变。官方Subagents文档支持字符串复用父连接，但不是本机版本已执行证明；插件忽略mcpServers，不能将项目目录安装的这个候选描述为插件同等支持。

确定性检查覆盖精确服务引用/源映射、11个名称与捕获原生工具目录相符、准备及通用工具不进入白名单、其他角色/宿主不变和缺源/漂移拒绝。实际原生解析、作者创建、模型/五Skill/工具拒绝及业务报告另留证，静态检查不得关闭6.3或内容门禁，其他宿主未验收义务按D4.1列为遗留。停止后的原窗口不利用剩余额度重派；任何后续实际验证必须属于用户已批准的有界执行计划，无新后端、自动重试或续期。

### D2.5 同类原生入口修复覆盖已有Market/Skeptic（2026-10-08）

本次真实验收中，Skeptic的Agent调用同样显式传入worktree/opus并在作者创建前失败，未实际尝试省略参数。按用户重申继续完成及最小修复授权，将D2.3的既有原生绑定结构复用于两个现有角色：新增`market-native`、`skeptic-native`薄Skill，分别固定`runtime_market_catalyst`、`runtime_skeptic`；不增加职责或共享研究方法。主线程只传skill/args，不回退Agent。两个项目角色显式引用各自已有MCP连接，精确工具、Skills、inherit和首轮无正向读取保持。

导出仅增加两个精确源到Claude发现目录的映射；缺源/漂移/共享同名目录冲突写前拒绝，Codex/OpenCode不安装，旧包不变。D2.3/D2.4中“仅Company、其他角色不变”是当时修复范围，不约束本增量，但其旧证据仍只证明当时版本。原生Skill的独立任务prompt不是复制父历史的通用fork；Skeptic实际首轮输入隔离、子工具池和模型必须重新观察，配置或文档不能替代。模型配置与转录元数据冲突继续明示，不改宿主或桥接字符串来补证。

共享角色正文同时说明：有原生Skill加载工具时实际加载所需Skill，宿主预加载则核对其实际来源；仅写“应用”或主线程加载不证明专业加载。每位作者使用本角色工具，不照抄CIO前缀；当前有界验收规定首错停止时，不再调用后续工具或提交，不由项目新增监控/停止器。此增量及D3.4.1归入6.1准备与6.2–6.4验收，不增加任务数量或放宽门禁。

### D3. 提交和查询复用业务边界，不伪装旧生命周期

2026-10-05实施发现单连接固定任务目录会使同角色的多证券/多能力原生任务继承同一连接，要求反复手动改环境或重连。用户已明确选择“允许调整并继续”，批准更新本Change的Specs、Design、Tasks并实施下述业务路由；这不增加安装、来源/账户、模型预算或最终发布授权。

连接改为绑定一个已验证研究请求/Gate和角色范围。任务准备边界为各原生任务生成精确`task_ref`及任务能力凭据；query/calculate/submit/read按这对引用定位服务端已经授权的任务，并重验请求/Gate/角色。引用不是caller identity，凭据只限制数据/提交能力；actual host/model/author未知仍UNVERIFIED。连接的公共上下文不能列出其他角色凭据、正向正文或私人账户字段。

实现只在既有业务工具/MCP增加请求范围内的任务查找与写前授权，不记录RUNNING/WAITING等宿主状态、不设派发队列、timer、重试或后台进程，不驱动原生Agent。原生主线程负责依赖/委派与结果回收；业务准备和依赖报告校验仍属于确定性工具。历史单任务工具接口不原地扩权，原稿和查询收据继续按原任务绑定读取。

三个宿主的薄模板绑定相同请求范围及各自角色，而不是一只股票/一个capability的任务目录。验证必须覆盖同连接任务A/B的交替和并发业务调用、A凭据+B引用拒绝、跨请求/角色拒绝、失败不占另一任务名额、Skeptic无正向读取及三模板与实际stdio参数一致。先前3.2–3.5和4.1证据仅证明原单任务切片，不证明本次新路由；新增3.6单独完成后才能据此接通4.2。

优先把现有 Gate 查询、计算、报告读取及 `research_submission` 校验/装配/保存抽出为宿主中立的确定性调用。建议新边界为 `product/tools/research.py` 与 `product/mcp/research.py`；这是少量业务函数/stdio transport，不是 executor、注册框架或新的研究后端。尽量复用报告研究字段与已有 Schema；只有旧技术信封确实强制 Codex 字段时才引入显式原生信封版本，不原地改旧 Schema。

最小业务流程：
1. 获授权的准备工具从合法单股请求或确认 Handoff 建立任务范围，绑定问题、证券、Gate/cutoff、角色、允许资料/计算和输出契约，不调用模型。
2. 原生角色经受限 MCP 获取本任务目录/事实/计算。服务端按可信任务和每次授权拒绝跨任务或越权，不以 LLM 提供的 agent/run 字符串证明调用方。
3. 原作者提交研究字段与明确引用/计算选择，工具验证结构、来源、实际查询、精确对象、计算、权限及修订上限，然后产生不可变短回执；失败不覆盖已保存成果。
4. 当前主线程从回执读已验证正式产物，业务归集只组合引用与覆盖，不能裁决观点。综合时继续记录实际 read/query 与作者选择。

任务能力凭据可以防误路由，不能证明是哪一个原生 Agent 调用。宿主角色的实际工具权限和隔离必须另行可证；无法保证当前用途要求时停止该能力，而非降低旧信任要求。可保存的草稿/业务有效结果与“执行身份验证通过的报告”必须清楚分列；不能把 UNKNOWN 送进要求已验证执行的旧消费者。新消费者必须显式识别新信封与证明范围，不把原生产 Codex 记录补出来。

局部纠正沿原作者、精确原稿回执和原次数上限；通过工具返回定位错误完成，不依赖 Stop 阻塞/自动重启。原稿内容与引用仍由模型选择，程序不修改研究语义。

### D3.1 原生任务的小型私有授权交付（2026-10-08）

实际桌面尝试中，132,912字节完整任务授权整读超限，模型随后误用了旧任务，资源漂移检查正确拒绝。用户明确授权使用新的小型授权继续Company，并允许检查需求、修复接缝。沿用D3的任务准备/确定性序列化边界，`product.tools.prepare task`增加可选`--agent-grant-output`：完整操作方授权输出保持原格式，另向已批准的源码外私有路径写入精确task_ref/task_token及role/capability/security_id/cutoff/task_hash、source_id/as_of/retrieved_at；不交付完整task、事实ID列表、资源hash表、正文、依赖报告或连接/准备凭据。专业角色经原有context/catalog/query获取业务资料，不把短packet当实际作者或权限生效证明。

两个输出位置须在创建任务前验证为源码外、绝对路径、私有目录、无symlink且不存在；同路径、公开目录、已有文件或非法位置拒绝，不创建任务、不覆盖旧授权。写入复用0600/O_EXCL/O_NOFOLLOW，不通过打印回传秘密，不新增交付服务或运行控制器。未传新选项时旧输出保持原样。当前已绑定桌面安装与旧task不就地改动；新生产者需进入后续明确审阅的新安装/新任务，不能以开发测试回签当前原生执行。

### D3.2 大型任务上下文的精确分页（2026-10-08）

正确桌面task的原生research_context实际返回119,722字符并被宿主响应上限拦截；只读字段量测确认其中allowed_evidence_ids为109,479字符、1398项，输出Schema为8128字符。不是缺研究资料、权限不足或资源漂移。沿用现有目录分页边界，context增加显式evidence_offset/evidence_limit（默认32、最大64），返回本页原始ID、完整总数及next_evidence_offset；不截断JSON、不丢弃服务端允许集，不将目录当实际查询。内部计算事实列表仅返回数量，计算和其血缘仍通过已有calculations接口获取。每一页仍先重验凭据、输入/Gate/资源绑定，错误页参数在业务写入前拒绝。小任务原ID列表不变；原生MCP声明精确参数，主线程和专业角色不必整读全部事实ID即可取得权限与完整输出契约，再按目录/query自主选择事实。验证大型合成输入分页无遗漏/重复、真实stdio响应和越权/漂移拒绝；不启动模型或放宽门禁，也不就地修改当前绑定的安装或重签旧task。

### D3.3 原生SEC结构化金额的确定性计算接缝（2026-10-08）

OpenCode唯一获准Company作者已实际查询SEC财务事实；四次ratio把包含amount/unit/period的value对象交给只读Decimal(str(value))的既有工具，全部INVALID_NUMERIC_EVIDENCE。一次结构化USD金额换算也因只支持正文正则而失败；另一次将就业人数交给金额换算属于作者选错资料，必须继续拒绝。原生窗口已停止，原失败、8次查询、0成功计算/提交及pending状态保留，不把开发修复回签为报告或宿主PASS。

沿D3/D5的确定性金融计算职责，在共享EvidenceTools增加默认关闭的SEC结构化金额读取开关，仅原生ResearchTools启用；旧调用者默认行为、历史hash和冻结Gate保持原样。只接受已有research-supplement-fact/1.1.0、financial_history、sec_financial_fact和SEC来源的合法有限amount及期间元数据，不任意搜索对象中的数字。ratio仅接受同证券、同accession/taxonomy/unit/context_type及相同起止期间的两项；不选证据、重述、累计/单季或自动对齐期间。monetary_scale仅接受USD并复用one→目标数量级换算，税前/税后未知仍UNSPECIFIED；结构化percent_change未实现则明确拒绝。回执保留精确选中ID、value.amount路径、来源三字段、单位、期间和原事实hash，计算hash仍绑定原事实。凭据/PIT/资源/允许集先验、成功保存及catalog/提交选择边界不变，不添加公式/自填操作数或Agent控制。

以合成同型事实验证真实准备→MCP calculate→保存/catalog及选择消费；涵盖原生允许/旧默认拒绝、错token/跨证券/未来/漂移、任意对象/非有限金额/不同币种或期间/零分母失败不留成功记录，原件不改。开发测试不调用原冻结任务、不启动来源或模型、不修改已安装包，不续期OpenCode总截止；当前Claude的首轮隔离、正文和内容门禁保留，其他宿主义务按D4.1列为遗留。

### D3.4 原生query的完整事实字节分页（2026-10-08）

新获批OpenCode Company窗口首次query选择32项，数量未违反64 ID上限，但按原调用与Gate重建完整响应为99,085 UTF-8字节，超过65,536；工具正确返回NATIVE_RESEARCH_RESPONSE_TOO_LARGE。目录32 ID页不是事实query的字节预算。作者首错后仍继续两批查询，开发方观察后关闭本地窗口；保留2/3任务、2查询收据、0计算/提交/报告以及原失败，不把业务修复变为重开窗口或补造首错停止证据。用户要求继续完成Change、所有授权同意，修复限于已授权确定性查询交付，不新增模型窗口。

在既有ResearchTools.query/MCP参数边界增加可选offset/limit。默认从0开始、最多64项；未指定页参数且全量能装入原65,536字节时保持原响应。大响应自动返回按模型原选择顺序、在该字节预算内的最长完整事实前缀；显式页请求也返回total/offset/next_offset（末页为null），后续由原生作者自主调用，不自动query下一页。字节预算包含实际JSON页信封，使用既有序列化方式准确计量；不能只按ID数量估计、扩大上限、截断value/来源或跳过过大的事实。单项与页信封仍超限时保留原错误。offset必须是范围内整数，limit为1–64整数，bool/越界/重复ID等写成功收据前拒绝。

每次先按原边界重验任务/Gate/PIT/资源及全部请求ID，再进行机械分页。原事实内容、单位、期间、来源三字段和hash不变；result_hash只绑定返回页。原请求参数用于input_hash，成功query收据的evidence_ids从实际返回的可信事实提取，而非整个请求列表；既有提交消费边界据该收据拒绝未返回页的引用。没有成功页不产生工具收据或报告名额。EvidenceTools旧查询、Gate/旧安装/任务/报告、SEC运算与其他工具不扩权；context与MCP描述同时说明页与字节上限，不把目录当读取。

零模型检查覆盖合成32项大事实经真实准备→stdio→多页无遗漏/重复→实际查询收据→未读后页提交拒绝及全部读取后合法保存/精确回读；核对UTF-8准确边界、完整单事实、请求/结果hash、显式小页/末页、小请求原格式、未知/跨任务/排除ID位于未返回页仍先验拒绝、非法页参数/单事实超限/PIT/资源/凭据失败不写。真实窗口仅复用已有私有失败做字节定位，不用原任务跑开发探针；聚焦检查不宣称原生作者复发预防、完整三宿主或内容通过。

### D3.4.1 已有计算目录的有界交付（2026-10-08）

本次OpenCode的两次calculations输出各被宿主截断3,537,664字节。直接路径是statistics_catalog为每个metric重复完整evidence_fact_ids，而ResearchTools.calculations一次返回全部对象。只修既有业务工具的运输：默认目录按offset/limit（默认32、最大64）返回精确k引用、原数值/单位/方法/产物绑定；长血缘仅返回原ID列表的数量/hash及明确不完整标记。需要逐项核对时，用同一工具的calculation_ref和evidence_offset/evidence_limit（默认32、最大64）显式读取精确输入ID页，原顺序/完整ID保持，末页null。目录不等于原始事实query，不开放TECHNICAL_STRUCTURE的原始事实集。

每个目录/血缘页均包含真实来源三字段、总数及下一偏移，完整JSON响应上限65,536 UTF-8字节；选择最长完整前缀，不截断指标或单ID、不自动翻页/选metric。空目录合法；非法页参数、未知/跨任务引用、单项仍超限、权限/Gate/PIT/资源或precomputed文件/hash漂移先验拒绝。计算目录仍只读取已准备/实际成功计算，不产生新运算或新增持久化副作用。

内部calculation_catalog及statistics_catalog完整对象、精确k绑定、磁盘校验与提交时可信完整血缘展开保持，不用目录摘要重建正式计算。小型不带分页参数的原响应能装入预算时保持原格式；显式分页或大型响应使用有界格式并如实标明已返回血缘范围。MCP真实Schema和context同步说明参数，不能仅靠Prompt宣称可用。确定性检查用已有技术数学夹具生成真实任务，验证大血缘目录/精确页/真实stdio/完整提交展开，及越权、非法页、漂移、单项超限无写入；不调用原冻结任务作开发探针，不改旧候选或用零模型通过代替原生消费与内容裁定。

连带回读检查发现：合成长血缘报告完整响应960,948字节；既有公开MRVL统计的1518个ID列表本身130,548字节，正式报告仍在research.calculations与calculation_support保留完整血缘。前者是确定性测量、后者是只读规模测量，不虚构新的原生回读失败。为避免只修目录、提交后仍交付无界响应，在已有research_read_submission的MCP边界复用完整回执读取再机械切页；Python内部read_submission、报告原稿/hash、归档及依赖消费者仍取得完整对象，不能将页送进内部业务验证。

小报告未传页参数时保持原完整对象；大型或显式offset/limit返回稳定canonical JSON字符串片段，offset/total/next_offset按Unicode字符计数（默认及最大8192字符），完整页信封仍不超过65,536 UTF-8字节。页绑定精确draft_ref、report_id、原report_hash、完整序列化payload_hash及原来源三字段，明确fragment不是完整报告；读取者须按同一回执显式继续并拼接全部片段，未读末页不宣称完整回读。每页先重验原授权、资源、稿件/报告hash，非法参数/跨任务/漂移无写入；不自动拼接/翻页、摘要/删血缘、改语义或新增分片服务。真实stdio检查多页无损重建与hash、UTF-8及错误/恢复，沿本增量6.x验证，不增加任务或模型额度。

### D4. 只记录实际可得证据，不建设通用执行证明协议

保留三类独立结论：
- **业务有效性**：服务端请求、授权、实际 query/read/calculate、回执、Schema/PIT/引用/hash/保存与覆盖。
- **宿主观察**：实际发现来源、角色委派、独立输入、工具可见与拒绝、当前主线程综合及模型信息；用各宿主真实可得材料记录，不翻译成 Codex JSONL，不搜索私人会话库。
- **内容裁定**：核心主张支持、重要反证取舍、期间单位、已核实/未知与阶段边界，由用户或明确授权复核者判定。

缺任何一类不能由另一类推导 PASS。能力支持说明是短静态表，不是运行状态 Schema/服务；普通研究工具不因为缺旧 CLI 二进制失败。版本锁要求严格的旧维护或晋升不能拿 UNKNOWN 通关。

2026-10-08较早按用户明确的缩减方向，本 Change 的验收对象收敛为原生 Agent Package，不再要求三次完整公开股票八维研究。当时方案为三个宿主各自验证最小合法阶段组合（当前Claude优先/其他宿主遗留的完成前置以D4.1为准）：优先复用既有版本化 fixture 的 Company / 独立 Skeptic / 主线程 CIO 链路，另用既有 MRVL 冻结公开资料的 TECHNICAL_STRUCTURE 切片验证 Market。两类输入分别绑定请求、Gate、任务及报告，不能互作依赖或将 fixture 动作能力授予真实输入；不新增 fixture、能力、Schema、材料来源或编排入口。完整 RESEARCH_SYNTHESIS 仍要求原六项正向能力及独立 Skeptic，不能用这组切片绕过。

每个切片仍需实际原生加载、受限工具、合法提交及精确读取；独立首轮不得继承正向历史/报告，CIO仍由明确综合阶段的当前主线程承担。内容核对仅裁定这些实际原报告的依据、期间/单位、反证、输入性质和限制，不认证未运行的完整股票研究。旧失败、预算偏差、已停止窗口及业务/宿主/内容裁定保持原时点；新口径不回签成功。未落盘的 Fed 接缝方向撤回，不新增 D3.5/2.7。

### D4.1 当前先验收Claude Code，并兼容用户批准的CC Switch映射（2026-10-08）

用户明确要求Claude Code先跑通，Codex/OpenCode留作遗留，并确认`opus`经CC Switch映射到`gpt-6.1-sol`。当前Change完成门禁仅要求Claude的既有fixture Company/独立Skeptic/主线程CIO与独立MRVL技术Market切片；原6.2/6.4及其他两宿主内容义务在[遗留清单](host-backlog.md)保持未完成，不删除模板/实现、不回签旧失败、不自动恢复。D4和Migration Plan中较早的三宿主验收前置由本增量收敛，完整产品研究、安全、最终人工完成批准和发布边界不变。

沿现有角色`model: inherit`与无model覆盖的薄原生Skill使用宿主当前路由；不新增Python模型检查器、CC Switch Client、API/SDK或路由层。薄指引与验收记录分别说明宿主选择/别名、用户批准的映射目标、真实转录可观察模型及其来源。当前`claude-opus-5`桌面声明/`opus`别名和`gpt-6.1-sol`转录可由用户明确映射解释，不再仅按字符串不同判冲突；用户声明不是读取CC Switch配置的证明，转录不是Provider wire证明，主/子观察分别保留，未知不伪造。未经批准目标、无已知映射或实际不可用仍按窗口条件停止；不自动改模或让模型填技术身份，不改旧报告的UNVERIFIED。

新候选只覆盖已审阅的Claude指引/说明，不复制dirty树、全局配置、CC Switch数据库或凭据。复用既有精确导出/verify_export、prepare connection/task、小型授权及stdio正负例；既有模板/导出结构测试保护inherit和无派发覆盖，不靠文字断言证明映射运行成功。一次新Claude窗口按批准计划最多5原生任务/30分钟，先跨turn加载，再由现有三个原生Skill及产品主线程执行，首错/未授权模型/隔离不可证/源码旧产物变化/截止即停，不恢复旧窗口或重派。实际业务、宿主与内容仍分列，最终批准另行处理。

### D4.2 实际Skill来源拒绝与原生新会话加载边界（2026-10-08）

第二次窗口经用户AskUserQuestion明确批准后，原生消息已实际投递，新cwd/CLAUDE.md和主线程gpt-6.1-sol元数据均被官方导出核实；14:00:20.959Z实际调用portfolio-council，14:00:20.985Z注入正文的Base directory仍为旧minimal-slice包。旧/新该Skill正文hash相同，但角色、工具连接及安装整体来源不能由单份正文等价推导，因此按首错停止，未读小包或派作者，不放宽门禁。内部缓存原因未证，不把它说成所有Claude版本必然行为；原始Skill工具短回执为Launching，Base directory来自另注入的isMeta正文。

薄安装/主线程说明不再把同一会话切目录并结束turn视为完整重载保证。新候选从其精确目录新建原生产品会话，再分别核对实际Skill/角色/MCP来源；不清空或删除原会话，不改全局配置、宿主安装、安全模式、模型或认证，不写项目加载器、不用路径别名/另一Skill绕过。已有窗口关闭；新会话及新窗口须对应明确授权，零模型说明修复和候选准备不自动启动模型。仍复用原精确导出/prepare/stdio与29项模板/导出检查，不新增研究职责、后端或测试框架。

### D5. 混合模块按函数职责迁移，不整目录搬运

规范冲突已在本次 delta 明确处理：原生主线程/Smoke/模型选择、任务完成与报告有效分离、研究MCP、单股/多维旧Hook包装及旧控制接口退役。完整fixture的业务Risk约束保留，但正常原生调用不再绑定Codex命令；发布级四fixture稳定性、专项评分/Replay等旧严格维护不属于本Change自动运行范围。应用时还需按这些明确作用域核对保留主规格，不能把旧Codex技术要求悄悄带回正常入口，或借作用域删除业务义务。

| 当前文件/边界 | 保留/拆出 | 当前正常路径退役内容 | 迁移后消费者与主要检查 |
| --- | --- | --- | --- |
| `product/skills/portfolio-council/SKILL.md`、专业 Skills | 研究依赖、方法、覆盖/停止点、输出与安全边界 | CLI 命令、特定 Hook/状态工具作为必要调用说明 | 三宿主主线程/角色；正文一致、方法/工具可达与实际内容核对 |
| `product/.codex/agents/runtime_{company_analyst,market_catalyst,skeptic,cio}.toml` | 四职责正文、方法依赖、任务工具要求 | 正文中的 launcher/Hook 专属技术包与固定厂商依赖 | `product/agents/` 正文及三宿主原生模板；旧源先保留可回退 |
| `common_stock_data.py`、`live_input.py`、`single_stock_input.py`、`research_input.py` | 证券/输入核实、允许来源准备、Gate/来源/时点 | 无；不重做来源层 | 准备工具、现有采集测试；未授权不运行 Provider |
| `common_stock_stage.py` | `assemble_common_stock_semantic_draft`、引用检查、报告包保存/严格复用及 coverage | `build_common_stock_stage_prompt` 的宿主派发细节、`_run_bounded_process_group`、`launch_common_stock_stage` | 原生提交/读取调用拆出的纯业务函数；原派发事件不成为新保存前提 |
| `multidimensional_stage.py` | 资料/依赖/计算与报告装配、`check_multidimensional_bundle_consumable`、确定性归集 | 父协调 Prompt、`read_multidimensional_task_state` 的 Hook 生命周期投影、`launch_multidimensional_stage` | 原生角色/主线程消费固定业务依赖；单项失败和全维覆盖接缝 |
| `research_materials_stage.py` | 文档来源/实际获取审计、选择装配、`materialize_selected_peers` 及只读准备验证 | 原父调度 Prompt 与 `launch_research_materials_stage` | 原生 Company/Market 的明确准备任务；资料工具不继承正式研究权限 |
| `independent_skeptic_stage.py` | `scope_evidence_ids`、`validate_first_pass_input`、合法报告/交接包检查、中文渲染 | 父调度 Prompt、Hook 状态投影、`launch_skeptic_phase` | 原生独立角色及业务查询/提交；正向污染、跨任务、未查询引用拒绝 |
| `predecision_cio_stage.py` | 来源目录、业务 request/目标/Gate 检查、实际报告读/query和引用核对、确定性 finalizer | `_run_cio_process`、`launch_predecision_cio_run`、新报告的进程结果格式要求 | 当前主线程和纯业务检查；旧包读取器独立按版本保留 |
| `research_submission.py`、`local_revision.py` | 写前授权、选择装配、精确回执、不可变稿/有限修订/错误反馈 | 新业务提交经 `resolve` 的 Stop 消息解析和接受所需 Hook 路径 | 原生提交业务边界；错误凭据不占额度、旧稿不变、两稿上限 |
| `fixture_mcp.py`、`product/mcp/`、`launch_fixture_mcp.sh` | Gate query、受限 calculate、文档/报告 read 和业务提交；现有 stdio实现可复用 | 新原生正常工具面的 CLI 运行身份实参、生命周期控制工具和 launcher 依赖 | 宿主中立受限 MCP；真实 tools/list/调用/拒绝与身份装配 |
| `cio_handoff.py`、`multidimensional_references.py`、`hashing.py`、`schema_validation.py` | 精确选择、无损引用/计算展开、完整报告读取、hash/完整 Schema 校验 | 仅依赖特定宿主输出事件的包装部分 | 原生提交与历史读取；引用/数值/单位/PIT负例 |
| `invocation.py`、`run_package.py` | 必需业务任务范围、原稿/报告身份、Risk适用边界和现有历史读取 | 新研究创建 Codex Start/Stop 包、父执行器驱动、执行与研究身份混为一套 | 新最小技术信封仅承载业务身份；不制造通用会话状态协议 |
| `nested_codex.py`、`codex_runtime.py`、`codex_hook_recorder.py`、`environment_preflight.py` | 确有历史读取消费者需要的校验函数；将业务部分先拆出 | 日常模型启动、CLI测量门禁、Hook控制、探针/状态重建 | 旧维护或历史读取隔离；正常原生入口依赖检查必须不触达其执行代码 |
| `execution_proof.py`、`native_trace.py`、`release_gate.py` | 冻结历史证明读取与本用途必需的业务验证 | 新原生报告必须具备 Codex事件才能有效的要求 | 历史消费者与当前原生观察分列；不绕过旧晋升门禁 |
| `product/runtime/cli.py`、`scripts/council-dev.py`、`scripts/run-product-smoke.sh` | 确定性数据/报告/历史读取命令，Tiger 已批准只读入口及显式旧维护定位 | 正常研究创建宿主模型进程、多个父阶段串联及退役调用回退 | 旧正常模型命令给退役说明，用户日常请求改用当前宿主；不放开 Tiger 底层真实入口 |
| `research_memory.py`、`product/council/` 的数学/契约、`product/risk/` | 现有共享存储、checkpoint、数据数学与已实现硬风险 | 无；不新增 Memory Agent 或主观评分规则 | 业务工具及现有纯数学/Memory/Risk测试 |
| `product/web/` 的报告读取、`product/trading_journal/`、两个独立交易 Skills、`product/broker/` | 原生/旧报告可读、独立复盘与私人隔离；必要新报告格式读取 | 不认领 Tiger 并行 API 实现或实机验收，不合并两账本 | 旧/新报告渲染与既有交易隐私/复制测试；仅合成数据 |
| `model-routing.json`、`runtime-profile.json`、`version-manifest.json`、包清单 | 公共业务资源单一批准来源及旧冻结锁 | 新正常产品固定为 Codex CLI/gpt身份，平台私有字段混进公共方法 | 原生宿主模型选择与短配置映射；评分/旧维护锁不动 |
| 根/产品 `AGENTS.md`、`PRODUCT.md`、`README.md`、环境/运行手册 | 中文、安全、开发/产品分离与历史操作依据 | 正常产品只能走宿主 CLI launcher 的长期描述 | 原生使用和显式旧维护分别说明，当前优先级只放本 Change |

矩阵是已定位职责，不授权整文件变更。尤其 `product/runtime/cli.py`、MCP、版本和 web 含未归档的其他需求：apply 前逐 hunk 对照当前现场，不能安全分离的项明确停止。不存在的建议新路径标为拟新增，不宣称已实现。

### D6. 测试清单随职责收敛，不按数量删除

- **退役候选（先确认历史读取消费者）**：`test_nested_codex_launcher.py` 的命令/目录/Hook装配用例，`test_specialist_dispatch.py`/`test_specialist_start_context.py` 的新运行专属接线，`test_codex_runtime.py` 的普通研究二进制测量，`test_multidimensional_task_state.py`/`test_research_terminal_projection.py` 的旧父状态控制。历史完整性用例保留在历史读取侧。
- **混合迁移**：`test_research_submission.py`、`test_bounded_research_submission.py`、`test_submission_protocol_admission.py`、`test_task_bound_research_tools.py`、`test_common_stock_semantic_handoff.py`、`test_skeptic_semantic_handoff.py`、`test_material_semantic_handoff.py`、`test_predecision_cio_stage.py`、`test_cio_handoff.py`、`test_research_local_revision_handoffs.py`：把身份、权限、引用、计算、修订、保存和读取用例接到真实业务生产者/消费者；仅移除被替代生命周期断言。
- **保留聚焦回归**：严格Schema/hash/PIT、`test_calculation_handoff.py`、实际数据与证券输入、数学、Memory、旧Artifact/中文、交易隐私和copy排除、只读券商安全。通过既有零模型夹具测试非法输入和失败不覆盖，不建 fake Agent流程来证明原生执行。
- **新增最小原生检查**：共享正文/三宿主配置解析和来源链接、受限 stdio 工具正负例、准备→真实业务 submit/read→归集/综合校验→中文的合成接缝；检查正常路径无宿主启动/API模型调用依赖。静态检查必须考虑历史读取明确豁免，不能通过删业务规则凑零命中。

替换或删除前说明每组测试保护哪条业务要求、它被何处替代；测试总数/LOC下降不是完成阈值。尚未实际跑任何上述检查。

## Risks / Trade-offs

- [三宿主的权限和上下文并不等价] → 逐宿主真实观察角色、工具拒绝和首轮；文档或提示不能代替。OpenCode首轮继承、Codex通用文件工具限制是具体核验项，无法证明则阻断，不新造宿主或放宽权限。
- [从Hook拆出时丢掉真实身份和引用门禁] → 服务端先重验授权/任务范围，再装配精确对象；实际作者身份单列，UNKNOWN不能进入要求严格身份的旧消费者；拒绝路径不占名额。
- [跨宿主正文复制后发生漂移] → 只维护一份权威正文，发布期展开映射并检查来源，不做可编辑的三套方法或运行期生成器。
- [保留历史反而把旧框架带回正常路径] → 历史只读代码不得启动模型；维护入口独立显式授权，正常依赖检查/帮助和配置不得回退。
- [新原生平台可访问源码/私人数据] → 原生角色配置配合服务端数据范围，实测写入/越权拒绝；配置与事后hash不冒称OS强制全进程只读，无法满足最低安全条件的能力不发布。
- [大量dirty被误认为本次重构范围] → 逐 hunk 分离、不整目录暂存或替换；暂停需求现场保留，敏感或归属不明停止相关发布。
- [把瘦身当研究质量修复] → 核对最小合法切片的实际依据、反证及限制，不要求为迁移补齐研究来源，不回签旧ALB FAIL或宣称暂停37项内容修复完成；正式完整研究仍按原业务成功条件验证。
- [缺某宿主环境造成最后验收阻断] → 当前按D4.1验收Claude，Codex/OpenCode的实际环境、安装和预算缺口保留为遗留；不得因缺环境自行标PASS，未获授权不付费试错。

## Migration Plan

1. **边界批准**：先评审本四类规划；显式apply后锁定相关旧内容/差异归属，记录具体受影响函数与测试，不制作通用全仓快照前置。任何受影响真实运行必须自然结束后再切换源码。
2. **业务抽离**：先接通受限准备/query/calculate/submit/read及确定性保存，真实生产者消费者正负例通过；历史读取保持原版本。此时旧运行尚未退役，不宣称架构完成。
3. **共享内容与薄配置**：抽取四角色正文、对齐共享Skill和三个原生模板/安装说明，配套版本来源及新技术信封；不修改用户全局配置，不设置新模型默认。
4. **原生切片与完整路径替换**：当前宿主原生 Company→独立Skeptic→主线程CIO的最小切片先打通，再把资料准备、Market和现有多维/持仓停止点接到相同业务边界。切片不证明完整八维/多资产能力，但完整业务输入/输出和依赖路径必须实际实现。
5. **控制与测试退役**：替换消费者后移除正常CLI/Hook/状态路径，旧公开模型命令明确退役；只保留确有用途的历史读者及隔离维护引用，不永久维护两套正常入口。完成职责映射、受影响回归和规则文档对齐。
6. **当前Claude的有限真实验收**：按D4.1仅新建Claude精确候选，复用已有fixture与MRVL技术切片覆盖四职责，记录宿主选择、用户批准CC Switch映射、主子实际观察、权限/独立输入、任务计数与完整业务读取。一次新窗口最多5原生任务/30分钟，首错即停；Codex/OpenCode原生及内容验收移入遗留清单保持未完成，不自动启动。完整公开股票研究依赖及历史证据不放宽。
7. **切片内容及收尾**：核对Claude实际原报告的核心依据、期间/单位、重要反证、限制与输入性质，分列业务、宿主执行和内容；明确其他两宿主遗留以及未运行的完整研究/真实账户建议/晋升。交付保留/拆出/删除及测试变动映射，人工完成批准后才同步主规格、归档和限定Git发布，不自动恢复其他需求或遗留宿主。

回退以新安装/业务入口尚未完成时保留的批准旧版本为依据，保留原产物；若需要恢复旧模型执行，必须由用户明确批准对应旧入口、版本和预算，不能静默回退。退役完成后，旧产物通过只读版本消费者继续可读，不为回退保留隐藏正常执行分支。

## Open Questions

这些是具体环境观察项，不改变既定架构/范围：
- 本机/用户可提供的三个宿主版本及实际安装位置；官方新格式与已安装版本不一致时使用该版本已验证原生格式或报告环境阻断，不能改写公共方法或安装升级。
- 三宿主实际可提供的模型/作者/加载观测范围；用各自真实证据，不设计统一事件协议。严格用途缺必要证明保持未验证。
- 混合历史模块在移除launch/Hook后尚有哪些真实只读导入；按已定位调用者做精确依赖闭包，不恢复执行器作为兼容捷径。

</details>
