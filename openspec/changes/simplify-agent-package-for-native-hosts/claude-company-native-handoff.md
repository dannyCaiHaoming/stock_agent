# Claude Code：Company 切片原生交接

- `source_id`: `claude-company-native-handoff:20261007`
- `as_of`: `2026-10-07T14:19:18.148887+00:00`
- `retrieved_at`: `2026-10-07T14:19:18.148887+00:00`

## 当前桌面入口

用户明确继续在Claude Code桌面开发调试。最新文件绑定及产品项目见[桌面准备结果](claude-desktop-readiness.md)：项目`.mcp.json`直接读取源码外私有连接，不依赖下方CLI启动参数或独立CLI登录。新桌面副本采用新任务资源绑定，旧安装/任务保持原样；46项确定性测试及strict通过，但实际角色/MCP、主线程权限、私有packet交付和有效模型窗口尚未核验，不能据stdio判原生PASS。下文CLI命令只保留为历史失败记录，不再作为当前入口，不重跑或动态重置窗口。

## 历史CLI实际停止结果

本页首次启动命令已按用户要求由开发方在可见Terminal执行，CLI因未登录在模型前停止，没有重试。当前原窗口为14:42:03Z—14:57:03Z，保守计1/3尝试、实际模型0；需用户完成CLI认证后明确恢复。下方启动命令保留为首次入口记录，不得重复执行并据其动态时间参数自动重置窗口。详见[认证停止记录](claude-company-native-auth-stop.md)。

## 已完成的准备

用户已选择“安装并验证Company”。新版项目位于：

`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/claude-code-current-20261007/product-workspace`

采用原270项批准来源，其中16项使用本Change已审阅新字节，包含9项AST不变的格式修改；并行`product/intake/__init__.py`仍采用原批准字节。300项导出文件的原集合及hash检查通过，三个旧安装均复验通过。产品文件0444、目录0555仅是权限设置，不是对同一用户进程的OS强制只读证明。

连接配置、任务授权、原生会话权限设置和任务交付文件仅在相邻`grants/`私有目录，目录0700、文件0600，不复制进产品源码或公开证据。复用已有Claude Company连接，新增独立`COMPANY_RESEARCH`任务；原私有授权文件和公开样本的所有既有字节保持不变。新任务使用新版业务资源绑定，不复用旧任务的过时绑定。连接配置只启用Company；不连接Market/Skeptic/CIO，不修改开发或全局配置。

新版业务stdio的initialize、tools/list、合法任务context通过；错误任务凭据与正式研究search均被拒绝。实际拒绝码分别为`NATIVE_RESEARCH_ACCESS_INVALID`和`NATIVE_MATERIAL_SOURCE_ACCESS_FORBIDDEN`。未替研究作者选择或query事实、执行计算或提交草稿。Task允许1398条公司事实，截止点仍为`2026-09-28T12:35:32.208143Z`。

41项操作方、研究归档、连接、宿主模板、包导出及旧入口退役检查通过（17.439秒）；strict通过。实际聚焦命令：

```bash
.venv/bin/python -B -m unittest tests.test_native_operator_preparation tests.test_native_research_history tests.test_native_research_connection tests.test_native_host_templates tests.test_native_package_export tests.test_native_entry_retirement
```

记录见[安装证据](claude-company-installation-evidence.json)和[业务准备证据](claude-company-stdio-evidence.json)。这些不是原生角色加载或内容PASS。

## 打开原生产品会话

当前开发会话没有研究角色/MCP，因此不能在此使用开发Agent替代。下面是用户直接打开Claude Code原生产品会话的命令，不是项目执行器，不由开发代码或SDK启动；不要在已运行的Claude模型会话里让Agent再执行它。

已只读核对本机CLI为2.1.291，帮助列出`--mcp-config`、`--strict-mcp-config`、`--restricted`、`--tools`、`--settings`等原生参数；`--append-system-prompt-file … --version`返回同一版本，但不据此声称实际任务加载成功。当前开发会话的app模型元数据为`claude-opus-5`，以下仅在新产品会话显式请求同一模型、high effort；实际主/子模型仍须原生核验，配置值不是Provider执行证明。

```bash
cd /Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/claude-code-current-20261007/product-workspace && /Users/caihaoming/.local/bin/claude --restricted --permission-mode manual --model claude-opus-5 --effort high --no-chrome --tools "Agent,Skill" --strict-mcp-config --mcp-config ../grants/company-mcp.json --settings ../grants/company-session-settings.json --append-system-prompt-file ../grants/company-handoff.md -- "执行已加载的私有Company切片任务。首次尝试UTC：$(date -u +%Y-%m-%dT%H:%M:%SZ)；硬截止UTC：$(date -u -v+15M +%Y-%m-%dT%H:%M:%SZ)。失败即停，不自动重试。"
```

本次安装使用原生私有`--mcp-config`覆盖配置，产品中的原始`.mcp.json`保持导出字节，避免在源码内写入秘密或放置凭据symlink。仅直接打开项目而不加载该私有配置，不能假定环境变量已存在。秘密通过原生文件参数加载，不作为命令行参数明文、不进入本交接记录。主线程内置工具仅请求Agent/Skill；额外原生权限配置拒绝源码/文件/命令/Web工具、prepare_task和来源search/fetch，并仅预批准Company委派及对应业务工具。配置是否实际生效需在新会话观察；发现未知角色、权限不符或模型不可核对即停止，不自动降级。

## 预算与停止点

- 最多3个原生任务／15分钟；从上面命令首次实际尝试计时，失败计入，不自动重试。正常计划是主线程1＋Company1，上限不要求用满。
- 零模型安装、任务准备和stdio检查不启动该研究窗口；截至上述证据时间，产品模型任务0、窗口未开始、报告0。
- 只运行冻结Gate的Company研究并取得精确提交回执/回读报告，停止于Company报告。禁止联网补采、完整八维、Skeptic、CIO、Risk、账户和交易能力。
- 无法证明必要角色、工具、模型或时间窗口时停止，保留真实失败，不用通用Agent、子CLI、API/SDK或额外任务兜底。
- 完成后保留原生回执和实际观察，私有转录不得直接发布。操作方可按已有确定性archive入口归档研究报告，但本次尚未执行该步骤。

## Change状态

保持17/24。6.1/6.3的Company准备切片推进不等于整个任务通过，三宿主完整实际验收、独立首轮、内容核对及最终人工完成批准仍未完成。未运行Runtime Eval/Execution Replay/Regression/Calibration/Ablation/Promotion，未同步主规格、开发Change归档、暂存、提交或推送。
