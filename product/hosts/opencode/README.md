# OpenCode 原生配置

原生`opencode.json`使用prompt文件引用共享正文；Company/Market/Skeptic是subagent，CIO是当前primary。导出时引用产品包自己的角色正文，不复制可独立编辑的另一套研究方法。共享Skills放`.agents/skills`，角色与MCP按本版本原生配置加载。

工具权限从`* = deny`开始，仅开放对应MCP前缀、角色所需Skill；CIO另允许调用三个原生专业任务。业务MCP绑定合法研究请求/Gate与角色，默认disabled；准入连接环境后才启用，各调用使用精确task_ref/task_token，不逐股票换配置。MCP的command只运行确定性stdio服务，不运行宿主或模型SDK；凭据来自私有环境/明确任务授权，不保存到可发布包，也不作为宿主作者认证。

公开文档没有充分说明该本机版本subagent的历史继承与首轮隔离保证；原生子会话存在、提示词拒绝或文件可解析都不能证明独立反证。实际验证缺少时，该能力BLOCKED，不以其他宿主结果代替、不自动运行或改权限。当前PATH只读版本观察为1.17.13，实际产品模型运行未验收。

官方依据：[Agents](https://opencode.ai/docs/agents/)、[Skills](https://opencode.ai/docs/skills/)、[MCP](https://opencode.ai/docs/mcp-servers/)。模型尊重用户原生选择，不固定厂商或宣称Prompt切换生效。
