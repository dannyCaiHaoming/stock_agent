# Claude Code 续接：架构边界与安装诊断

- `source_id`: `claude-native-resumption-check:20261007`
- `as_of`: `2026-10-07T14:03:05.564233+00:00`
- `retrieved_at`: `2026-10-07T14:03:05.564233+00:00`

## 当前有效授权及新版准备结果

用户随后选择“安装并验证Company”：已按270项精确来源及16项已审阅覆盖，安装新版 `claude-code-current-20261007/product-workspace`，排除并行Intake字节并保留三个旧安装。原生私有MCP配置复用已有Company连接，新增独立Company任务；合法context及错误凭据/禁止来源调用的stdio检查通过，未替作者query事实、计算或写研究草稿。41项当前聚焦检查与strict通过。实际模型/来源/账户调用及报告仍为0，新3任务／15分钟窗口尚未开始，真实角色加载须用户打开对应原生产品会话后观察。具体命令、停止条件与证据见[Company原生交接](claude-company-native-handoff.md)。下文“本轮未安装/未新增预算”等句子保留为此前只读诊断时点，不覆盖此后授权和安装结果。

## 用户确认与本轮范围

用户明确要求项目运行在 Claude Code、Codex、OpenCode 等 Agent 软件底座上，不自行开发另一套 Agent 架构，并授权继续本 Change。沿用已批准实现范围；本轮读取获准外置安装、核对来源及连接配置、运行聚焦确定性检查并澄清文档。没有据此新增 Provider、注册外部服务、修改原安装/用户配置或开启产品模型任务。

宿主负责原生会话、模型执行、专业委派、等待与权限；项目只提供共享 Skills、角色正文和确定性业务工具。当前开发会话不替代产品会话，不能用开发 Agent 冒充研究角色，也不经 CLI/SDK 创建额外模型执行进程。

## OpenAlex 的实际职责

`product/mcp/live/public_research.py` 的既有 `OpenAlexResearchClient` 使用 OpenAlex Works 检索及 Content API 获取公开学术/技术文献正文；它不是模型或 Agent 服务，也不等同于券商股票研报库。代码的 `fetch` 在没有 API key 时返回 `PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED`。原生资料准备 `product/tools/materials.py` 复用此适配器，只有获准准备任务能够 search/fetch。

该配置仅影响具体资料准备，不是宿主安装、角色发现或独立冻结 Gate Company 研究的通用前置。MRVL 完整研究的真实资料依赖仍保留，不删除 material_inputs、不转换旧稿、不把已有宏观文本机械升级为新正文回执。本轮没有 OpenAlex 网络请求、凭据配置、注册、购买或来源替换。

已在 `product/hosts/README.md` 补充这一说明，没有修改来源实现或业务门禁。

## 外置安装的当前观察

已获目录访问：`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006`。

对各 `product-workspace/native-package-export.json` 运行现有 `verify_export`，三个原安装均通过原文件集合/hash校验：

| 宿主 | 原来源数 | 导出文件数 | 原导出 manifest SHA-256 |
| --- | --- | --- | --- |
| Claude Code | 270 | 300 | `572bc40ea1fa4ac1d22020c312ec0c25182c7bd419b7896364e96d7c22202130` |
| Codex | 270 | 300 | `6c477bff4e14ef2a235bea3f6bf2849ce14cc98a65904a7e7c2c5998346ab35f` |
| OpenCode | 270 | 296 | `aa37735a3730f235a9a5b5d153cba8df1bb26d941faa1431f881681c98b8038c` |

这只证明原安装完整，不证明当前源码已安装或宿主加载。

本轮说明修改之前，当前工作树与各原安装来源有16项字节差异：原12项实现/格式/说明增量、3项Codex角色transport修复，以及应排除的并行 `product/intake/__init__.py`。本轮又修改 `product/hosts/README.md`，这是额外的文档增量，不回签此前12项、v4候选或原安装证据。

Claude 产品项目的 `.claude/agents/` 有三个已展开角色，无 `{{ROLE_BODY}}` 残留；相应 Skills 已复制到 `.claude/skills/`。项目 `.mcp.json` 的四服务均指向现有解释器和本产品源码。其连接/token共8项环境变量在当前执行进程中未绑定；项目没有 settings/settings.local 配置。只能确认当前进程缺绑定，不能推断其他 GUI/终端或用户配置的状态。

既有私有环境文件存在，四个连接目录存在且各自 token 已配置。本轮仅核对键名、存在性和非空状态，没有将凭据值打印、复制或存入证据。原安装、私有授权及配置未修改，也未启动业务 MCP。

当前开发会话仍未提供三个研究角色和四个研究 MCP。文件展开/配置可读不是真实加载或权限隔离证明。

## 聚焦检查

实际命令：

```bash
.venv/bin/python -B -m unittest tests.test_native_host_templates tests.test_native_package_export tests.test_native_entry_retirement
```

结果：21项，4.613秒，退出码0，`OK`。覆盖共享角色/模板、洁净导出及旧正常模型入口退役，不是研究内容或宿主执行验收。

`openspec validate simplify-agent-package-for-native-hosts --strict` 通过。

当前读取的来源 hash：

| 文件 | SHA-256 |
| --- | --- |
| `product/hosts/README.md`（本轮说明增量） | `a98de6fd4b71e0002017746e23dfd97ce2603d3d7d52e100132d28424b720138` |
| `product/hosts/claude-code/README.md` | `d9dd88970533985092c24a6eb2b8b9b462d2b98e34b3a8b2b1a5e4c3b2fec7d7` |
| `product/hosts/claude-code/mcp.json` | `34c8eb65816ad926dcc85237d8b57e545431dbce3ce0fd97fe27d180fed9b1f1` |
| `product/mcp/live/public_research.py` | `ef88a920f206474644d014037c8b3ae8f4186279610e54b741a9ff4e18961407` |
| `product/tools/materials.py` | `55438c321bfed0aa2c3508e300d0215bca56161d4092b9a43ce12c96d44113dd` |

这些是本轮来源标识，不是生产版本锁或全进程只读证明。

## 续接条件与状态

下一步是所选 Claude 原生产品会话的版本对齐、现有私有连接环境绑定及实际角色/MCP发现，不是接入OpenAlex。原安装保持可恢复；新版导出/安装应采用明确精确来源，不覆盖旧安装、开发 `.claude` 或全局配置。真实加载须在对应原生产品会话核验，不用启动子CLI或模型SDK代替。

此前Codex预算的硬截止 `2026-10-07T09:40:24Z` 已早于本轮观察；其历史4/15、余11只是原次尝试记录，不自动把过期窗口移到本轮。Claude原尝试0/15且已停止，也不据余量自动重跑。后续真实执行按恢复时明确的宿主、阶段、预算及新时间窗口核对；本轮不消耗产品模型预算。

本轮产品模型0、来源网络0、账户0、报告提交0。三宿主实际执行、Skeptic独立首轮和内容裁定仍未完成。Change保持17/24，不勾6.x/7.x/8.1，不同步主规格、归档、暂存、提交或推送。Runtime Eval、Execution Replay、Regression、Calibration、Ablation、Promotion均未运行。
