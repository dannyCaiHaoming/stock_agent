# 共享研究角色

四份Markdown是自有产品角色的唯一正文源：

| 职责 | 正文 | 承载 |
| --- | --- | --- |
| 公司研究 | [runtime_company_analyst.md](runtime_company_analyst.md) | 宿主原生专业Agent |
| 市场与多维 | [runtime_market_catalyst.md](runtime_market_catalyst.md) | 宿主原生专业Agent，每项任务一个capability |
| 独立反证 | [runtime_skeptic.md](runtime_skeptic.md) | 不继承正向历史的原生独立Agent |
| 综合 | [runtime_cio.md](runtime_cio.md) | 用户当前宿主主线程，不派CIO子Agent |

宿主模板只注册角色、依赖Skills和实际工具/权限，不维护另一份研究方法。发布导出时把这些正文展开到目标宿主文件，不能在运行时由Python创建会话、派发模型或翻译事件。

共享Skill源在 `../skills/`。专业角色需实际加载其方法；正文/配置可读不等于实际执行或隔离已验证。服务端任务能力仅限制数据范围，不认证原生作者身份；缺宿主观察如实UNVERIFIED。

产品工作禁止源码写入和账户/券商能力。实际权限仍以各宿主可生效配置和工具拒绝证据为准，不能以角色提示词代替。安装冲突或最低隔离无法确认时停止对应能力，不覆盖用户设置。
