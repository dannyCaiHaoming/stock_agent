# Codex / OpenCode 遗留验收（未完成）

- `source_id`: `native-package-host-backlog:20261008`
- `as_of`: `2026-10-08`
- `retrieved_at`: `2026-10-08`
- 来源：用户明确要求“先跑通claude code底座吧，codex，opencode遗留”，并批准Claude优先与CC Switch映射实施计划。

这些义务由当前Change原6.2/6.4及其他两宿主内容核对迁出，不是完成、删除或验收豁免。当前完成前置只覆盖Claude；长期三宿主方向、已有共享工具/模板和历史证据保留。后续必须由用户另行安排与授权，不自动开启模型窗口或合并其他Change。

## 未完成事项

- [ ] 原6.2：在当前Codex原生产品会话完成既有fixture Company/独立Skeptic/主线程CIO及独立MRVL技术Market最小组合，核对加载、权限、初始输入、query/calculate/submit/精确read、调用与源码保护。
- [ ] 原6.4：在当前OpenCode原生产品会话完成同等组合，核对primary/subagent、实际Skill、首轮隔离、工具权限、完整计算/报告分页消费及首错停止。
- [ ] 原7.1相关部分：核对两宿主实际合法切片原报告的核心依据、期间/单位、反证与限制，分别裁定业务、宿主执行和内容。
- [ ] 后续宿主验收的规格/实现/测试/证据映射及独立完成批准；不得以当前Claude完成回签两宿主PASS。

## 继承现场与限制

- Codex：旧Folder trust仅为历史观察。最新尝试在Terminal命令校验阶段停止，未启动Codex进程；错误地将整个JSON overrides作为单个`-c`是另行发现的命令缺陷，即时hook根因未证实。最终私有预备命令已按独立TOML `-c`修正，配置读取仅四业务MCP enabled，额外cua_repl仅在该次预备覆盖中禁用；没有执行修正后的模型命令，不改用户全局配置或自动代选信任。
- OpenCode：最新实际CLI只给附件而缺positional message，返回`Error: You must provide a message or a command`，模型前停止。inline私有配置四业务MCP已解析enabled；message-before-file修正仅经静态语法检查，未运行。旧四份真实报告的VALIDATED不抵消首错后继续、Skill缺证或统计截断/空计算选择。
- 所有旧窗口停止，不借余额/改参重试/续期。原始[旧真实结果](minimal-native-result.md)、[旧证据](minimal-native-result.json)及私有原件保持原时点；未归档/发布的当前工作区和其他Change不被认领。
