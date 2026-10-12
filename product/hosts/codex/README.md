# Codex 原生配置

模板仅适用于用户显式准入的产品工作区，不覆盖仓库根开发配置。`config.toml` 注册原生Company/Market/Skeptic，CIO由当前主线程读取共享方法，不作为子Agent注册。导出时将四角色正文展开到角色文件，把产品工作区绝对路径替换为用户指定的安装目标。

- Skills安装至产品工作区`.agents/skills/`；角色配置沿原生`.codex/agents/`加载。
- `features.shell_tool=false`、只读sandbox、Web/App关闭及任务专属MCP白名单来自官方配置说明；目标版本必须实际支持，未支持不回退或关闭校验。
- 模板中的MCP默认disabled。用户需准入每个角色的研究请求/Gate连接及服务启用；目录使用`STOCK_AGENT_*_CONNECTION`、连接凭据使用`STOCK_AGENT_*_TOKEN`，仅留私有环境，不提交Git。每项业务调用传准备边界给定的精确task_ref/task_token，同一角色不需按股票改配置；服务不管理模型会话。
- 专业角色禁shell并不自动证明所有文件读取已隔离。实际原生工具面须证明无正向/私人文件读取和源码写入；若当前版本仍暴露不可受限的读工具，独立首轮标BLOCKED，不能仅靠提示词宣称安全。
- 本机PATH版本只读观察为0.159.3，模板尚无实际加载/模型证据，不声称与其他0.160.0安装等价，也不升级CLI。

`fixture-mcp.json`仅保存旧fixture/显式维护资源锁所需的原禁用模板，内容hash不变；它不是当前原生连接配置，不由宿主自动加载。产品根`.mcp.json`为本机派生配置，旧资源发现不读取它，也不以此证明当前加载。

官方依据：[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)、[原生Agent](https://learn.chatgpt.com/docs/agent-configuration/subagents)。普通使用在当前会话调用Skill，不运行自建模型launcher，不自动评分或Replay。
