# Claude Code 原生产品配置

正常使用以当前仓库 `product/` 为唯一产品项目根，根目录保留开发职责；不先导出另一份源码，不切换到外置私有数据目录。首次/来源变化的准备、同请求多任务复用、保持MCP接线的显式刷新及实际加载条件，统一见[产品准备说明](../INSTALL.md)；不逐证券更新宿主配置或重复来源诊断。

## 配置来源与权限

- 方法在 `product/skills/`，职责在 `product/agents/`；本目录只提供原生注册模板。[主线程操作指引](main-thread.md)和共享 CIO 正文随产品规则展开到派生 `product/CLAUDE.md`。
- 三个专业角色分别由 [company-native](skills/company-native/SKILL.md)、[market-native](skills/market-native/SKILL.md)、[skeptic-native](skills/skeptic-native/SKILL.md) 固定绑定。原生 `context: fork` 提供独立任务 prompt，专业定义提供 tools、Skills 和 `model: inherit`；CIO 不注册为子 Agent。
- 角色仅用精确`tools`从父产品会话已启用的Company/Market/Skeptic连接取用业务工具，不在角色内重复指定`mcpServers`，不授通用Read/Bash/Write/Edit/Web/Agent或观察/准备工具。连接只在产品MCP配置中声明，不复制凭据或新增服务；此配置针对项目角色，不宣称插件同等支持。实际子工具过滤仍须按下文核对，不能由字段省略宣布通过。
- 默认就地准备不激活研究连接；Intake、交易记录和复盘不自动进入 Council。研究获授权后，仅显式启用必要角色连接，每次业务调用仍重验请求/Gate/task_ref/task_token；工具可见不代表授权，任务凭据不认证宿主作者。
- 业务代码与解释器显式绑定当前仓库和项目环境。私有连接文件、任务和产物在源码外；`.mcp.json` 只含本机接线，不发布凭据或机器路径。未知文件/来源漂移写前拒绝，已登记且未被用户改动的派生文件可显式刷新，不修改根开发 `.claude/` 或用户级配置。

## 模型与实际加载

专业角色保持 `model: inherit`，native Skill 不覆盖 model。用户已有 CC Switch 映射由宿主使用；宿主别名、批准目标与主/子实际观察分列，不因合法映射的名称不同判冲突。项目不读取 CC Switch 数据库、认证或完整环境，不改用户模型/代理、不实现路由后端，历史模型锁不改写。

实际来源、专业 Skills 预加载、工具池、模型和 Skeptic 首轮隔离须在获准产品任务中核对，不能由配置/stdio/hash或模型自报替代。来源冲突、入口不可用、工具池为空或隔离不可证时停止对应任务，不用通配工具、通用 Agent、另一个模型 CLI/SDK 或 Hook 兜底。源码只读、私人授权交付和阶段边界也须实际生效。

日常研究不需要 Git/worktree，不自动运行评分、Replay 或 Promotion。业务保存、宿主执行和内容裁定分别报告；静态准备状态为 `PREPARED_NOT_LOAD_VERIFIED`，不表示当前有限 Smoke 或其他宿主已验收。

官方配置依据：[Desktop](https://code.claude.com/docs/en/desktop)、[Subagents](https://code.claude.com/docs/en/sub-agents)、[Skills](https://code.claude.com/docs/en/skills)。
