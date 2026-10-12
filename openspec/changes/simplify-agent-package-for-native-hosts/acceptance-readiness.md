# 6.1 三宿主验收准备：ALB样本与候选安装清单

- `source_id`: `native-host-readonly-readiness:20261006`
- `as_of`: `2026-10-06`
- `retrieved_at`: `2026-10-06`
- 状态：**PREPARATION_ONLY / NOT_INSTALLED / MODEL_NOT_RUN**
- 顺序：Claude Code → Codex → OpenCode；本次只准备，不缩减三宿主目标。

## 1. 用户授权与边界

用户明确允许只读查找已有合格公开ALB冻结样本、核对包来源、提出新仓库外产品工作区与安装清单，Claude Code优先。未授权真实模型、联网补采、产品安装、覆盖当前配置、读取私人账本/会话/原始转录、归档或Git发布。所有检查只读取必要公开/业务来源；本报告和来源清单写入本Change，不写产品源码或运行原件。

6.1仍未完成：实际可读样本、安装目标批准、每宿主实际权限及模型/时间/调用预算尚未齐全。配置和AST闭包不认证实际加载/支持。

## 后续准备记录

用户后续已选择“MRVL＋补齐接缝”。本文件保留当时ALB查找/251项提案，不作为最新安装准入结论。当前102项确定性补验、270项来源清单及MRVL原限制见[preinstall-readiness.md](preinstall-readiness.md)；实际安装/产品模型仍待另行批准。早期目录工具的访问限制也已由[host-research-path-check.md](host-research-path-check.md)纠正，不能据本文件推定稳定资料丢失。

## 2. ALB冻结样本查找结果

### 已定位的公开记录

- 来源：归档的`2026-10-03-enable-single-stock-research-synthesis/implementation-evidence.md`以及项目内明确交付的`.codex-local/alb-report-cio6-20261003/README.md`。
- 标的：`US:COMMON_STOCK:ALB`，非持仓、无账户/动作的研究级综合。
- 原共同cutoff：`2026-10-02T02:51:27.261450Z`。
- 原来源run：`host-single-stock-c9e25b89-d968-479e-bdb3-49787aff8bc6`。
- 原source package hash：`3d086a375e927403a4e991877634aaa0a9c88b140eecbe025810e408af45d2fd`。
- 原第六稿run：`predecision-cio-433f5e1b-6ccc-4639-b66a-26f7f90471a8`。

### 现物读取范围与结果

| 对象 | 实际检查 | 结论 |
| --- | --- | --- |
| 归档明确指向的`/private/tmp/single-stock-alb-research-20261002-v1`（含run-v2） | 精确目录授权工具返回could not be resolved | 当前无法读取/验证；不据此断言文件已删除，也不绕过目录授权扫描整个tmp |
| 明确指向的`/private/tmp/stock-agent-alb-cio6-host.pl6vubq6` | 精确目录授权工具同样无法解析 | 当前不能验证原冻结副本；未读取原模型转录、proxy、stderr或凭据 |
| 项目内第六稿副本 | 只读README，hash报告字节，未修改 | SHA-256仍`29d84a4a6b34fba9c011467d9e27b51f6d51bafb9000a1f4d99c5e83afec9ca1`，与原交付说明一致；仅是报告副本，不能作为请求/Gate/正文/同行包 |

**样本结论：找到明确历史指针和原字节报告副本，但尚未定位可读、完整且可验证的冻结研究输入。** 不从报告或验收摘要重建事实、不猜引用、不复制旧query/read事件为本次证据、不把旧批准的有限内容范围扩为本Change的完整研究PASS。

### 待恢复原样本的最小文件范围

只需要明确来源包中的业务输入，不需要整个宿主目录：

1. 原版`SINGLE_STOCK_RESEARCH`请求及身份来源，能核对证券、request hash、cutoff和无账户字段。
2. 原冻结Gate及其实际允许事实、来源/时间/单位/hash；基准、Macro/Market资料不能靠上游报告猜取。
3. 实际取得并选择的`BODY_VERIFIED`正文、必要获取/选择收据和原准备血缘；截断正文/目录各自范围保留。
4. 已选择同行、实际物化manifest及同源事实/Gate绑定；不能只提供候选目录。
5. 明确文件清单/hash和必要版本说明。原Company/八维/Skeptic/CIO报告可用于历史对照或7.x内容核对，不自动升级为事实、不进入Skeptic首轮。

用户若有原包备份，只需提供**一个明确的公开业务冻结包目录**并准许读取，不必手工转换JSON/Gate。若只能恢复部分输入，记录缺失；没有原版时另行提出受限数据准备授权，本次不补采、不以合成fixture冒充公开ALB样本。

## 3. 候选包来源核对

当前仓库HEAD为`a23dc764b082591e3c47c8bb30e3569040bc18b8`，分支main，存在本Change及其他需求dirty内容，未暂存/提交/切分支。

### 精确来源提案

- 已有测试导出方式的只读来源闭包盘点为253项，发现其中包含3份并行Tiger broker Schema；因此不能直接把它当作洁净、已审阅安装包。
- 本次提案排除这3份并行Schema，增加确定性操作方`product/tools/prepare.py`，形成**251项精确文件/hash提案**，见`acceptance-proposed-source-list.json`。
- `product/intake/__init__.py`显式采用该HEAD批准基线，避免带入当前工作树的Tiger初始化；其余250项是待核对/批准的工作树候选，不把整dirty目录当授权来源。
- 静态Python导入闭包通过；未含nested_codex/codex_hook_recorder控制器、broker客户端、Tiger Intake、私人目录/会话/账本。hash核对无漂移；导出器既有常见密钥模式未命中，但这不替代完整敏感审阅。
- 提案来源清单的规范SHA-256：`95f86af4f64eeb26dd19aeb18f13d15017290575e802515693269ade86782bda`。这是本次待审来源身份，不是已批准版本锁、已导出内容hash或真实宿主加载证明。
- 已有527项/297项/18项证据按其原代码版本复用；本次没有启动产品模型、测试导出或真实安装。新增prepare.py来源项不被此前导出测试自动覆盖，安装前须显式核对完整候选的渲染/洁净闭包。

### 需明确保留的准备入口缺口

`material_preparation.py`/同行操作层不在现有已测试运行闭包内。静态核对其可选采集依赖链仍经common_stock_data/research_materials_stage/multidimensional_stage牵入旧Hook控制器，不能未经核对放入禁止旧控制器的原生包。

本次不修生产代码、不通过动态import隐藏闭包、不恢复旧launcher。若恢复的样本已包含合法冻结正文/同行材料，可按已实现的material_inputs边界消费，专业角色不运行采集器；若实际验收还需要原生资料准备/同行物化的完整安装，则需先把该具体接缝按Change现有目标补齐/验证后再批准安装，不能以251项静态闭包宣称所有准备能力已可安装。

## 4. 新外置工作区提案（均未创建）

建议根目录：`$HOME/Documents/stock-agent-native-acceptance/20261006`。它在源码仓库之外；这里只提出布局，没有读取/创建该目录或认证不存在冲突。

```text
<外置验收根>/
  source-reviewed/                 # 审阅后的精确基线+overlay；无私人状态
  sample-public-alb/               # 同一原版冻结公开输入，只读
  claude-code/
    product-workspace/            # 新CLAUDE.md/.claude/.mcp.json及业务源码
    artifacts/<new-request-id>/   # 业务报告/审计；不复用旧事件
    grants/                       # 本地私有连接/任务能力，0700/0600，不发布
  codex/
    product-workspace/            # 新AGENTS.md/.codex/.agents
    artifacts/<new-request-id>/
    grants/
  opencode/
    product-workspace/            # 新opencode.json/.agents
    artifacts/<new-request-id>/
    grants/
```

源码副本/输入的实际只读与允许产物目录权限须由对应宿主核对，配置/hash本身不证明OS全进程只读。业务报告、样本及grants不放在源码仓库或其他用户安装下；目标已存在/同名角色冲突/符号链接或来源漂移时停止，不覆盖、不删除旧安装。

## 5. 安装清单与顺序

| 项目 | Claude Code（第一） | Codex（第二） | OpenCode（第三） |
| --- | --- | --- | --- |
| 主线程产品规则 | 新根CLAUDE.md，由产品规则+共享CIO正文组成 | 新根AGENTS.md，同一产品规则/CIO正文 | 原生primary及同一共享CIO来源 |
| 专业角色 | 新项目.claude/agents三角色，正文机械展开 | 新.codex/agents TOML三角色 | 原生subagent声明引用同一正文 |
| Skill发现 | 新.claude/skills；保留原版本/正文 | 新.agents/skills | 新.agents/skills |
| MCP | 新项目.mcp.json，四角色请求/Gate连接；仅本地确定性stdio | 新.codex/config.toml中的四角色受限连接 | 新opencode.json受限连接 |
| 模型 | inherit；实际宿主选择及运行预算待确认 | 当前原生宿主实际选择，非旧CLI锁/厂商强制 | 当前原生宿主实际选择，缺观测不猜 |
| 工具权限 | 专业角色精确MCP工具、Skill预加载，无Read/Bash/Write/Edit/Web/Agent；主线程准备能力另隔离 | 禁通用shell/网络，专业角色不得得到准备能力 | default deny、精确角色工具及task/skill权限 |
| 待证边界 | 项目配置/角色实际发现、批准的MCP启用、main源码写入拒绝；Skeptic非fork且不继承正向 | 原生格式/工具限制是否实际生效、首轮隔离 | primary/subagent权限、首轮历史继承及工具隔离 |

共同保留：全部研究方法/Schema、确定性数据/数学/硬Risk、历史只读与独立交易内容；独立交易私人写入不因复制恢复，不附带原隔离凭据、账户资料或broker Client。

安装前需用户明确批准：外置根和精确包源、解释器/依赖范围、允许新增的项目配置/角色/Skills/MCP及同名冲突处理。**本次未导出/安装/注册/启用MCP、未改当前.claude或全局配置。** 解释器暂只提出使用已核对的项目.venv，不另安装运行环境；实际宿主能否访问该解释器仍待确认。

## 6. 当前准备结论与下一步

- 可交付：历史公开ALB资料定位、报告字节核对、251项待审来源/hash、并行内容排除、实际安装前缺口和三宿主具体布局/顺序。
- 阻断：完整可读的原冻结ALB输入尚未恢复；来源/工作区安装尚未批准；准备/同行操作的可安装边界尚待明确验证；每宿主模型/预算及实际权限/隔离未认证。
- 下一步最小用户输入：如有原冻结公开包备份，给出一个明确目录；没有时允许我另列受限数据准备方案。安装和产品模型仍分别请求授权，不自动执行。
- Change继续17/24，6.1只完成准备部分，6.2–6.4/7.x/8.1不勾选、不归档/提交/推送，其他Change现场保留。
