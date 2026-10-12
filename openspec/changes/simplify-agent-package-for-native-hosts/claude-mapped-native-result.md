# Claude映射模型：本轮原生准入结果

- `source_id`: `native-package-claude-mapped-native-result-report:20261008`
- `as_of`: `2026-10-08T13:39:09.679Z`
- `retrieved_at`: `2026-10-08T13:44:52.613211+00:00`

## 结论

**本轮停在Claude桌面会话消息启动层，未进入专业派发。窗口已在开发授权侧关闭；Change仍24/29，剩余5项，不归档/提交/推送。**

用户明确批准的`opus`→`gpt-6.1-sol`映射已进入薄宿主指引与当前规格，名称差异不再单独阻断。现有角色`model: inherit`、三个native Skill不覆盖model的实现保持，不新增CC Switch Client、路由器、模型后端或项目调度器。此次没有新主/子模型执行观察，不能声称映射下的实际研究链路已经通过，也没有重新触发或解除旧zero tools问题。

## 实际证据

| 观察 | 事实与边界 |
| --- | --- |
| 新候选 | 仅Claude，274项精确批准来源、308个导出文件；3个新专业任务及CIO连接。29项模板/导出测试及实际stdio正负例通过，见[准备记录](claude-mapped-readiness.md) |
| 具体新窗口 | 开始13:32:02.833977Z，原截止14:02:02.833977Z，上限5原生任务/30分钟；不借旧余额、不续期 |
| 首条准入请求 | 只请求跨turn切换到新候选，明确本turn不派作者、不用业务工具。SendMessage返回20秒内未见目标启动，delivery=undelivered；工具提示仍可能稍后处理 |
| 应用转录 | 能看到跨会话消息的回显；这不证明消息已进入原生CLI或目录已经切换 |
| 官方导出 | 捕获时间13:39:09.679Z；CLI最新assistant仍为12:02:08.546Z，新窗口内无新CLI user/assistant消息，无新工具调用，cwd仍是旧候选 |
| 原生状态 | idle、isRunning=false、cliProvablyIdle=true；无待权限、待输入、待周期或后台工作。CLI binary pin为2.1.293，桌面模型声明claude-opus-5/high；permissionMode为bypassPermissions是已有状态，本轮未修改 |
| 停止边界 | 13:44:52.613211Z在开发侧关闭授权，不再投递后续研究。stop_session请求被当前auto mode分类器拒绝，未换工具绕过；**不能声称已发送中断、清空队列或取消Provider请求** |
| 业务与内容 | 新专业作者/业务工具/报告均未观察到，CIO任务未准备、Risk NOT_RUN；没有新报告可做内容裁定 |
| 保护 | 38项指定源码/测试、1,832项指定旧文件及582项新候选/来源文件hash均未变；不冒称OS强制只读 |

官方导出的原转录/metadata/本地状态zip仅留在本机私有材料中；公开结构化证据只保存白名单字段、捕获时间和文件hash，见[结果JSON](claude-mapped-native-result.json)。没有发布原转录、能力凭据或CC Switch配置；观察到的消息数不等于Provider请求、token或费用计数，idle也不等于Provider cancel。

## 当前任务与最小恢复条件

- 6.1、6.3、7.1、7.2、8.1保持未完成；已完成的零模型准备不替代原生加载、权限、独立首轮和真实报告证据。
- Codex/OpenCode继续在[遗留清单](host-backlog.md)保持未验收，不启动它们，不用旧OpenCode报告替代Claude结果。
- 需要先恢复既有Claude桌面产品会话的直接输入处理。应用消息回显与官方CLI记录存在差异，当前证据不足以确定内部根因；不改用户认证、代理、模型、安全模式或宿主安装来试错。
- 本窗口已关闭，后续实际尝试须有新的明确有界授权；不能恢复剩余额度或重投本次任务。新的最小窗口仍可沿原5原生任务/30分钟计划，不增加角色、来源、后端或基础设施。
- 最终人工完成批准未取得；未执行专项Eval/Replay/Promotion、归档、暂存、提交或推送。
