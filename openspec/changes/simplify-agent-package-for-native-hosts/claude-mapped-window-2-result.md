# Claude 第二次映射窗口：来源不符停止与新会话准备

- `source_id`: `native-package-claude-window-2-followup:20261008`
- `as_of`: `2026-10-08T14:11:00.630358+00:00`
- `retrieved_at`: `2026-10-08T14:12:34.767579+00:00`

## 结论

**Change 仍为24/29，未完成。** 第二次窗口实际进入了产品主线程，模型映射和新cwd有证据，但共享Skill仍从旧包加载；按首错规则停止，专业作者、业务调用、新报告均为0。当前阻断不是模型名称差异，也不是“消息完全未启动”。

新候选已完成零模型准备，**尚未在新原生会话加载，也未获得第三次窗口授权**。此记录不恢复任何旧窗口，不替代最终人工完成批准。

## 第二次窗口实际观察

| 项目 | 事实与限制 |
| --- | --- |
| 授权 | 用户经AskUserQuestion明确选择“授权一次新窗口（推荐）”；最多5个原生任务/30分钟 |
| 时间 | UTC13:54:06.257942开始，原截止14:24:06.257942；来源不符后停止，开发侧14:07:06.840005关闭，不使用剩余额度 |
| 主线程 | 原生消息实际投递；新cwd及新CLAUDE.md加载已观察，桌面声明claude-opus-5/high，新assistant元数据为gpt-6.1-sol，与已批准opus映射吻合 |
| 实际Skill | UTC14:00:20.959调用portfolio-council，仅传skill/args；14:00:20.985注入正文的Base directory仍在旧minimal-slice包，不是本次mapped候选 |
| 证据位置 | 短tool_result只返回Launching；实际Base directory来自另注入的isMeta正文，不误写为短回执内容 |
| 等价性 | 旧/新该Skill正文SHA-256相同，但不能据此推导安装整体、角色或MCP来源正确，仍拒绝继续 |
| 未执行 | 小型授权读取0、专业作者0、业务调用0、新报告0、CIO/Risk未运行；只观察1个产品主线程，不是Provider请求或费用统计 |
| 模型限制 | 专业作者模型未观察；未读取CC Switch配置/数据库，Provider wire仍未验证 |
| 保护 | 当次38项指定源码/测试、1,832项旧文件和582项新包/来源文件hash不变；不是OS强制只读证明 |

[原始结果白名单](claude-mapped-window-2-result.json)保持不变。[早期准备快照](claude-mapped-window-2-preparation.json)生成于实际Skill检查之前，已被来源拒绝覆盖，不能作为6.1完成证据；checkbox从未勾选。第一窗口的[未进入CLI结果](claude-mapped-native-result.md)独立保留，不由第二次成功投递回签。

只证实了本次来源不符；内部缓存根因未知，不能推广为所有Claude版本的固定行为。

## 最小修补与已完成检查

沿Design D4.2，仅修正Claude主线程、README、INSTALL及运行手册的薄说明：从精确新项目目录新建原生产品会话，再分别核对真实Skill、角色、MCP来源；切cwd、结束turn或新CLAUDE.md加载不保证全部刷新。

未新增Python生产代码、角色、Schema、模型后端、加载器或测试框架；没有改全局模型、认证、代理、权限或版本指针。原会话与旧包保留，不清空、删除或用别名/路径重试。

- 修改后模板/导出聚焦测试：**29项，exit 0，unittest 13.188秒**（外部wall 13.297394秒）。38项指定源码/测试检查期间hash一致。
- 新Claude候选：**274项精确来源、308项导出文件**，只overlay三份包内薄说明，不复制dirty树或并行Intake修改。
- 既有prepare入口建立三个全新专业任务及CIO连接；CIO任务等真实新正反报告后才准备，不伪造依赖。
- 实际候选stdio：合法context、错误任务凭据拒绝、Skeptic禁读及分页Schema通过。MRVL目录27项/16,663字节；血缘仅检查首个64/1,518 ID页，不冒称完整消费或作者指标选择。
- 新候选准备期间2,471项指定旧文件hash不变；产品模型、来源网络、账户调用及新报告均为0。

完整测试命令、hash和限定证据见[新会话候选准备](claude-fresh-start-readiness.json)。这证明确定性准备，不证明原生来源刷新、专业执行或内容通过。最新规格/文档检查单独见[文档检查](claude-fresh-start-document-check.json)。

## 下一步的最小用户动作

当前可用工具没有新建桌面Code产品会话的接口；不能用开发Agent、另一个CLI/SDK、任务工作树或项目会话管理器代替。

在Claude桌面Code tab新建一个**空白产品会话**，直接选择以下项目目录；保留旧“Company 原生验收”会话，不在旧会话里再次切目录：

```text
/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/claude-fresh-start-current-20261008T140951Z/claude-code/product-workspace
```

新会话的第一次产品执行仍需新的明确有界授权。建议边界保持原样：当前opus→gpt-6.1-sol映射、专业inherit；最多5个原生任务/30分钟，从首次准入尝试计时；只做既有fixture Company/独立Skeptic/主线程CIO/原Risk和独立MRVL技术Market；首个加载/权限/Skill/业务错误、映射外模型、隔离不可证、源码/旧产物变化或截止即停，不重派、改参重试、换入口或续期。此处只是待授权约束，不是授权已经取得。

不要求提供凭据、改全局配置、安全模式或CLI登录。实际Skill/角色/MCP来源仍须验证，新会话本身不保证通过。

## 剩余完成条件

6.1、6.3、7.1、7.2、8.1均保持未完成：新会话有效准入/授权、四职责真实执行与完整读取、原报告内容核对、最终人工完成批准、随后限定归档发布。Codex/OpenCode保持[遗留未验收](host-backlog.md)。未运行完整公开股票八维、真实账户建议或Eval/Replay/Promotion；未同步主规格、归档、暂存、提交或推送。
