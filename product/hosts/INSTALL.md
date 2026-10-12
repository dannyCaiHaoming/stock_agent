# 产品就地准备与可选导出

## 正常使用：唯一 `product/` 入口

仓库根用于开发，当前仓库 `product/` 是Claude原生产品项目根；用户始终在这里提供输入、选择阶段和批准模型/预算/停止点。获准外置目录只存连接、任务、凭据、冻结资料和不可变产物，不是另一份源码、Skill来源或需要切换的Claude项目。正常使用不复制Python/业务源码；Codex/OpenCode仅保留已有模板，未验收。

- 操作方沿既有确定性准备入口处理输入/Gate、角色连接及任务授权，不启动模型。首次或方法来源变化时显式准备薄发现；正常研究复用稳定角色MCP服务，新请求通过私有接入文件显式换绑，不逐股票生成宿主配置。
- 原生主线程使用有效的当前来源证据和精确任务授权开展获准阶段；必要准备后一次交付证券/问题/阶段/cutoff、小型授权、模型、依赖、产物和调用/时间预算及分类停止条件，不依赖开发线程在运行中逐步补参数或调用顺序。没有有效证据时处理对应缺口，不每次重做无研究诊断、整包导出或全量核对。
- 来源、连接或必要原生能力有问题时，停止真实依赖并保留独立成果；合法任务内可修订问题只沿同一原作者的一次机会，不靠新私有根、新长交付包、重派或另一模型后端推进。本说明不是运行授权，旧窗口不自动恢复。

## Claude Code：首次或来源变更时准备

在仓库根使用已有项目解释器，显式调用就地准备：

```bash
.venv/bin/python -B -m product.tools.package_content --source /path/to/stock_agent --host claude-code --in-place --reviewed-files /path/to/reviewed-discovery-hashes.json --python /path/to/stock_agent/.venv/bin/python
```

`--reviewed-files`是精确审阅的文件→SHA-256映射：产品规则、共享四职责、完整共享Skills及附件、Claude主线程/MCP/三角色/三native Skill模板，不是整份dirty工作树快照。解释器须明确存在，不自动安装依赖。工具只写 `product/CLAUDE.md`、`product/.claude/agents/`、`product/.claude/skills/`、`product/.mcp.json`及小型登记 `product/.claude/native-product.json`；方法确定性展开、附件链接原源，业务代码仍来自当前仓库，不启动服务或模型。

同名未知文件、源hash漂移、用户改动或symlink逃逸写前拒绝；已登记且未漂移的派生可按新精确来源显式刷新，不监听或清理未知文件。首次迁移旧 `.mcp.json`另传已审阅原hash `--migrate-mcp-sha256`，登记后不再用它。本机派生/接线不发布，根开发 `.claude/`、用户配置、私人账本和其他文件不改。

**未传连接映射时生成默认空MCP配置，不自动保留旧连接。** 研究已获授权且需要保持现有接线时，刷新命令须同时传入同一获准 `--claude-connection-files` 映射；生成器仍核对旧派生所有权/漂移。只改方法不换绑定，静态结果仍为 `PREPARED_NOT_LOAD_VERIFIED`，不证明宿主已采用新正文或Python接口。

## 私有连接、任务复用与实际加载

研究授权成立后，可给上述命令追加 `--claude-connection-files /path/to/approved-service-paths.json`。映射只含必要的 `company`、`market`、`skeptic`、`cio` 服务名及源码外私有连接JSON绝对路径，例如：

```json
{"company": "/获准私有父根/company-connections.json"}
```

就地准备只配置列出的角色，不读取连接秘密。固定配置中的 `--connection-env-file` 指向稳定的私有接入文件，按角色提供已准备的 `STOCK_AGENT_COMPANY_CONNECTION` / `STOCK_AGENT_COMPANY_TOKEN` 等字段。服务启动时验证一次，此后**每次业务调用和tools/list重新读取、验证所选角色绑定**；一次调用使用同一个完整快照，不把新任务套进旧请求。`STOCK_AGENT_COMPANY_EXPIRES_AT` 等可选字段是授权到期时间，按当前UTC检查，不是Evidence cutoff；新 `prepare bind` 必须填写，历史无该字段的文件保持原读取兼容。目录/文件仅当前用户可访问（通常0700/0600）、无symlink；真实凭据不得写进源码、命令正文或公开转录。文件缺失、错角色、过期或完整性错误脱敏拒绝，不回退缓存或继承环境。

新请求先沿原入口准备新的不可变连接及任务，再由操作方显式更新**同一个私有接入文件**。正常 Council 单股/研究流程由当前主线程在该请求/Gate连接匹配时调用 `research_prepare_task`；该工具不要求模型重复传连接凭据，服务端从私有接入文件验证当前绑定，返回精确任务授权供主线程委派。该工具不得出现在专业Agent工具清单。缺少匹配绑定时，必须先由操作方通过以下既有 `prepare bind` 明确批准；它不创建Agent/模型，不修改 `.mcp.json`，不修改旧连接/任务；按当前连接的角色只替换对应字段，保留其他角色。替换已有角色必须传原准备记录的精确connection_hash；缺失、错值、错误操作方凭据或并发占用拒绝，不猜当前绑定。更新采用私有锁和原子替换，旧授权到期不会自动续期。

```bash
.venv/bin/python -B -m product.tools.prepare bind --connection-root /获准私有目录/新请求/company --connection-access /获准私有目录/新请求/company/operator-grant.json --connection-env-file /获准私有目录/company-connections.json --expires-at "$AUTHORIZED_EXPIRES_AT" --expected-connection-hash "$PREVIOUS_CONNECTION_HASH"
```

示例变量须来自本次明确批准的带时区ISO-8601截止时间及原角色准备记录；首次绑定未存在的角色时省略 `--expected-connection-hash`。操作方持有连接凭据，专业仍只获精确task_ref/task_token。此模式仅承诺同一角色服务的顺序请求切换，不同时保留多个活动请求；换绑后旧任务立即拒绝，旧资料/报告仍保留供显式历史读取。

| 操作 | 使用已有边界 | 不需要或不能声称 |
| --- | --- | --- |
| 同一有效请求/Gate/角色新增获准证券或能力任务 | `prepare task`使用同一connection-root，为每项任务发放独立task_ref/task_token | 不逐证券换MCP配置、轮换连接或另开模型会话；任务仍逐调用验证 |
| 更新共享方法/薄发现 | 原生成器＋精确来源；保持连接时重新传同一获准映射 | 不复制源码，不把派生刷新当实际加载 |
| 新请求或Gate改变 | 在获准私有父根准备新连接/任务，`prepare bind`更新稳定接入文件的当前角色 | 不逐请求改MCP启动配置或重启；不覆盖旧连接/任务，不沿用旧运行授权；角色本身不能动态扩权 |
| 服务代码或首次接线改变后核对加载 | 一次使用当前宿主支持的服务重新加载动作，再按有效授权核对工具/业务调用 | 修改代码可能需重启以加载新版，但正常股票/任务切换不重启；纯进程环境绑定仍为旧静态兼容入口 |

同一服务复用不免除任务阶段、依赖或模型预算授权。活动服务在返回事实或产生副作用前逐调用验证私有接入文件、角色、连接、精确task_ref/task_token、请求/input/Gate/cutoff及资源；未被操作方合法换绑的新任务和已失效旧任务都拒绝。静态配置不证明生效，但无需先做四角色绑定巡检才允许合法业务调用。无可用加载能力时报告受影响服务和最小宿主条件，不杀进程、清空会话、改全局环境或用CLI/SDK兜底，不绕准入在错绑定上研究。

## 单股入口：没有冻结资料也可准备

Company的稳定私有文件模式新增主线程工具 `research_prepare_single_stock`，只接收symbol、可选question/cutoff。用户说“分析LITE”时主线程先调用它，不要求用户提供冻结资料。工具复用原 `collect_single_stock_research_data` / `collect_single_stock_snapshot`、身份校验、PIT Gate及 `freeze_latest_research_request`；公司准备不采集额外Macro/Market/期权上下文，不启动模型、多维资料Agent或旧Stage控制器。初次可只有操作方准备授权、尚无Company冻结连接；私有文件本身及宿主接线仍必须有效。

正常交互是：用户只输入LITE → 主线程调用准备工具 → 收到精确 `authorization_action.tool` → 调用标记 `_meta["anthropic/requiresUserInteraction"]=true` 的 `research_authorize_single_stock` → 用户在宿主完整审批界面批准 → 服务端复用既有 `authorize-single-stock` 逻辑并自动继续资料准备 → 主线程按next_tool准备Company任务并原生研究、完整回读。每次批准限定证券/问题、一次资料尝试、一次Company原生研究及原作者有限修订，按当前宿主模型inherit和明确截止；不含其他研究阶段或交易。用户无需执行CLI、制作Gate或提供内部路径。拒绝/取消时宿主不执行授权工具，主线程停止，不重试；到期、范围错配、旧ref重放或配置/来源/连接变化在服务端停止，不延长窗口。

原生门禁依据[Claude Code官方工具审批契约](https://code.claude.com/docs/en/mcp#require-approval-for-a-specific-tool)，从v2.1.214起支持：auto/bypass/acceptEdits及allow规则不能跳过该工具的真人完整审批，dontAsk拒绝。MCP初始化的clientInfo只作兼容性检查（当前接受claude-code及符合要求的版本），不是调用方身份认证。信任边界是本机受信原生宿主兑现这项契约及其私有stdio连接；伪造客户端、自动canUseTool SDK、自定义自动批准器不在支持范围，不能以版本声明认证真人。当前Desktop是否采用该实现须由实际宿主加载/审批观察确认，静态配置与合成测试不证明。单独的elicitation表单可被Elicitation/ElicitationResult Hook自动回答，本实现不把它或文字“同意”当可信批准；不新增Hook或修改权限模式。

安装方只需在**既有稳定私有Company接入文件**一次配置 `STOCK_AGENT_COMPANY_APPROVAL_CONFIG`，不是逐股票授权，也不是MCP参数。示例仅说明字段，不含实际秘密：

```json
{
  "STOCK_AGENT_COMPANY_APPROVAL_CONFIG": {
    "source_access_path": "/获准私有目录/source-access.json",
    "output_root": "/获准私有目录/research",
    "memory_root": "/获准私有目录/memory",
    "cache_root": "/获准私有目录/cache",
    "sec_user_agent": "仅本地配置的SEC联系身份",
    "authorization_seconds": 900
  }
}
```

目录/文件保持原0700/0600及无symlink边界；来源记录、来源hash和各Provider预算沿用原验证。900秒是此示例配置的批准窗口，服务端只接受1–3600秒，模型不能设置/续期；每次审批参数展示精确到期时间和来源请求额度。内部连接hash由本地已鉴权记录机械取得并锁定，不让模型猜；审批前后重验完整私有配置/源hash/连接，原子占用一次准备尝试，失败保留原采集证据。配置/旧绑定和SEC联系身份从不作为工具参数/结果；私有配置不进Git。缺配置返回NATIVE_SINGLE_STOCK_APPROVAL_CONFIGURATION_REQUIRED，未知/旧宿主返回NATIVE_SINGLE_STOCK_HOST_APPROVAL_UNSUPPORTED，不退回“用户执行CLI”或文字批准。

原 `prepare authorize-single-stock` CLI及已有显式本地授权保持维护兼容，但不是正常交互步骤，也不把旧纯资料授权升级为Company模型授权。成功返回FROZEN_COMPANY_BOUND及原next_tool，精确expected_request_hash/expected_gate_hash仍在任务创建前校验；新原生响应另含限定company_authorization供主线程自动续接。专业精确工具白名单没有授权/准备入口，caller_authentication仍为UNVERIFIED；不新增Agent、调度器或模型后端，不更改Market/Risk及完整多维资料要求。

新版服务和主线程指引需宿主一次加载；正常后续请求不逐证券改MCP配置或重启。本轮仅确定性验证，未设置真实私有配置、未启动真实研究或观察真人审批。

## 必要观察：按阶段取得，不循环诊断

| 时点 | 所需证据及取得方式 | 缺失处理 |
| --- | --- | --- |
| 专业委派前 | 当前产品来源、实际可见入口/角色/工具、有效阶段与模型/预算授权；同一有效上下文且正文未变的真实来源证据可复用 | 静态登记/hash、历史banner或孤立Re-invocation不证明本次来源；已知必要接口/隔离条件不可得则具体阻断，不新增窗口试探 |
| 每次正常业务调用 | 当前来源与阶段授权成立后，使用精确task_ref/task_token；服务端在事实/副作用前重验活动连接、角色、任务、请求/Gate/cutoff及资源 | 错配、PIT或完整性错误停止真实依赖，不改预期/凭据试错；不要求额外四角色巡检 |
| 明确授权的连接诊断 | 主线程按实际可见 `research_connection_context` 对必要角色各最多一次传准备的expected_connection_hash；不是正常任务前置 | 不先要求已有绑定证明；缺工具、错误或不匹配停止该诊断及受影响研究，不换hash/工具重试，不读连接token或借业务context/专业fork探测；未请求诊断的合法任务不因无观察工具失败 |
| 本次原生委派产生时 | 实际委派/返回、主子模型、角色/Skills/工具范围和Skeptic初始输入/隔离观察；取得时点按获准计划明确 | 不要求执行前已有本次执行事件；已有必要证据入口才作有界委派，真实材料缺失/不合格仍按原停点阻断，不能用配置/token/自报认证 |
| 业务交付与综合时 | 精确任务context及实际query/合法计算/submit/完整读取；合格依赖齐后同主线程CIO及适用原硬Risk，核对原稿内容 | 绑定、业务有效、原生执行和内容分列；目录不是消费，片段不是完整依赖，Risk否决不可覆盖，部分保存不表示全部完成 |

无研究来源诊断仅在明确诊断预算内使用实际可见共享非fork入口，不读凭据、不调用研究MCP、不派专业或担任CIO；多候选用正式可见作用域，不猜别名。获准的唯一裸名非fork入口可仅装载观察来源，不要求先证来源；旧内容/路径冲突保留并停止，不轮换名称重派。仅在宿主确有命令界面时使用其支持的Skill重扫，重扫不证明缓存清除/当前来源、不重置预算，不把内置命令交给Skill工具或普通消息试探。

绑定观察只证明本次连接匹配；实际返回进入获准私有记录，准备快照不改成实时证明。接口与专业委派的稳定字段/权限见 [主线程指引](claude-code/main-thread.md)。caller_authentication固定UNVERIFIED，Provider wire或精确费用未提供时单列，不补造，也不新增遥测/后端前置；必要模型和首轮隔离门禁不豁免。

三个专业角色保持 `model: inherit`，native Skill不覆盖model，用户已有CC Switch映射由宿主使用。分别记录宿主选择/别名、批准目标和主/子实际观察；合法映射不要求名称相同，未知不补造，未经批准目标不放行。项目不读取CC Switch数据库/认证、不改全局模型/代理，历史锁不重签。

独立Intake、交易记录和复盘不自动取得研究连接或CIO权限。专业仅获本角色业务工具，无通用文件/shell/Web/账户能力；Skeptic独立首轮不继承正向历史/报告，隔离不可证则阻断。主线程只有明确综合阶段才担任CIO，不自动进入后续研究、评分或Risk。

## 小型任务授权与完整读取

操作方使用已有确定性准备入口发放任务，小型授权不替代业务工具的任务/资料校验，也不认证实际宿主作者：

```bash
.venv/bin/python -B -m product.tools.prepare task --connection-root /获准私有目录/company --connection-access /获准私有目录/company/operator-grant.json --security-id US:COMMON_STOCK:MRVL --capability COMPANY_RESEARCH --grant-output /获准私有目录/company-task-grant.json --agent-grant-output /获准私有目录/company-agent-grant.json
```

`--agent-grant-output`仍仅写本任务task_ref/task_token、role/capability/security_id/decision_cutoff/task_hash及source_id/as_of/retrieved_at。两个输出须是源码外不同绝对路径、私有父目录已存在且无symlink、文件尚不存在；非法位置在创建任务前拒绝，0600文件不覆盖，秘密不打印。未传该选项时原完整授权格式不变。

需要现成转交参数时，操作方对明确既有任务运行开发侧准备脚本；产品主线程/专业不运行此脚本：

```bash
.venv/bin/python -I -B scripts/prepare-native-agent-grant.py --task-root /获准私有目录/company/tasks/精确task_ref --agent-grant /获准私有目录/company-agent-grant.json --output /获准私有目录/company-handoff-grant.json
```

脚本复用原agent_grant，重验精确task_ref/token、范围及资源锁，以同样私有create-only边界写增强小包：原平铺字段加`mcp_arguments`（精确双字段对象）及`specialist_args`（最小小包的JSON字符串）。自己的业务调用用双字段对象作顶层授权，再加工具业务参数；专业交付保持现成字符串不变，仅追加本次问题/预算/停止条件，不重建或猜token。它不复制完整task、允许事实ID集、资源表、正文、依赖报告或操作方凭据，不新建任务、不改旧task/hash、不派发模型或自动注入调用参数。原product/tools源码保持任务资源锁；漂移仍拒绝，不为刷新交付视图放宽锁。旧小包的精确平铺字段仍可消费。

主线程向对应专业任务交付精确小包，专业角色实际调用context/catalog/query并提交研究字段和明确选择，不从旧上下文猜授权。目录不等于实际取证，所有页面重验授权、Gate/PIT、资源和精确绑定，不自动翻页/重试，不猜引用或以摘要替代完整内容：

- `research_context`默认返回32个原始事实ID、allowed_evidence_total与next_evidence_offset；evidence_offset/evidence_limit显式分页，最大64，完整输出Schema不截断。完整允许集保留在服务端。
- `research_query`的小响应兼容；超过64KiB时按选择顺序返回完整事实页及total/offset/next_offset。每页先验证整组选择，收据只包含实际返回的事实；单事实仍超限时拒绝，不截断字段或跳过大事实。
- `research_calculations`大型目录按offset/limit返回不超过65,536 UTF-8字节的完整指标页，默认32、最大64，含精确k引用、原值/单位/方法及血缘数量/hash。核对完整输入ID时用calculation_ref和evidence_offset/evidence_limit继续next_evidence_offset；不混用目录分页参数，不把ID目录当原始事实query。提交仅交明确k选择，由服务端展开完整血缘。
- `research_read_submission`小报告原完整响应兼容；大型或显式offset/limit返回canonical JSON的report_json_fragment及total/offset/next_offset（Unicode字符计数，limit默认及最大8192），完整页不超过65,536 UTF-8字节。以同一draft_ref显式读至next_offset=null，按序无损拼接并核对完整payload_hash；原report_hash及来源三字段保留。最后一页不证明此前各页已读，片段不得作为完整依赖；内部完整对象与提交额度不变。

## 操作方零模型保存

已有有效提交后，操作方可将**明确选择的精确稿**保存到既有Research Memory并导出网页可读归档，不调用模型、不改研究判断或内容裁定：

```bash
.venv/bin/python -B -m product.tools.prepare archive --connection-root /获准私有目录/company --connection-access /获准私有目录/company/operator-grant.json --task-grant /获准私有目录/company-task-grant.json --draft-ref 精确有效提交回执 --memory-root /获准私有目录/memory --output-dir /获准私有目录/report-export
```

工具先验证请求、角色、任务能力与精确回执，不猜最后一稿。Memory/导出目标须在源码外、父目录私有已存在、互不重叠；导出目录必须新建，不覆盖旧归档或symlink。归档含冻结输入/Gate，保留私有；网页经已有 `--run-dir` 只展示验证通过的保存正文。结果仍为 `host_execution=UNVERIFIED`、`content_verdict=NOT_REVIEWED`；这不是开发Change归档/发布或Promotion入口。

## 可选分发与冻结历史

完整导出仅供明确分发用途，不是就地开发或验收前置：

```bash
.venv/bin/python -B -m product.tools.package_content --source /path/to/reviewed-source --target /path/to/new-native-package --host claude-code --reviewed-files /path/to/reviewed-file-hashes.json --python /path/to/approved-python
```

导出需要完整已审阅来源、精确hash及局部Python导入闭包，目标须全新；缺依赖/来源漂移/同名冲突写前拒绝，不覆盖旧安装或自动带入并行修改。`--host`仍支持已有codex/claude-code/opencode模板；它们的配置检查不证明实际宿主支持。只导出列出文件，不复制.private、凭据、会话库或旧正常模型控制器。独立交易/复盘模块保留，但导出不重签其私人写入隔离凭据。产物只标 `EXPORTED_NOT_INSTALLED`，不自动安装、授权或运行。

旧报告、原锁及失败记录按冻结版本只读，不改原件。显式Execution Replay仅在另获来源/版本/预算授权后运行冻结源码自己的入口；当前正常launcher/Hook继续拒绝，不作为加载失败的回退。维护步骤见 [运行手册](../../reviews/runtime/runtime-replay-eval-runbook.md)。
