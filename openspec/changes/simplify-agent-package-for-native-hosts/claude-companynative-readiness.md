# Company新入口：精确候选与原生交接准备

- `source_id`: `claude-company-native-readiness:20261008`
- `as_of`: `2026-10-08T02:54:05.314870+00:00`
- `retrieved_at`: `2026-10-08T02:54:05.314870+00:00`
- 目标：继续完成`simplify-agent-package-for-native-hosts`。
- 状态：**精确候选与独立任务已准备；原生窗口未启动，仍21/28。**

## 已推进的实际准备

新候选位于既有获准外置根下的`claude-code-current-20261007/desktop-companynative-product-workspace`。从上一个271项精确批准源，仅覆盖Claude主线程指引、Claude README、INSTALL并新增company-native原生Skill，形成272项源/303项导出。没有按当前dirty目录自动选文件；并行Intake保持原批准字节。

导出完整性通过；新Skill已精确进入`.claude/skills/company-native/SKILL.md`。原包302项文件保持原字节，三个专业角色与原包逐字节一致。候选及源设0444/0555，仅表示文件模式，不是同用户OS不可写证明。

- source manifest SHA-256：`1c0fa3786e4285712bd44f41898c17889a461c7b4ddd583fa53cae3197bcf38d`
- export manifest SHA-256：`f3651db71272793c8d8473d78dfca2f5b9a382988ac65f9003eda4065ce22cf8`
- 根CLAUDE.md SHA-256：`0fe3f4c131f2dec2e4678c45cc860c5412ed9ad804b7bb02dde4d7fa37ea8a1c`

从新候选的既有确定性准备入口生成独立Company任务`t.fc80a741e9208c4130055072`，task hash=`654df51bc41761aefeafaae835627143d46a1831161a99e9e37b16e115dbb0e2`。514字节私有agent-grant为0600，凭据不进入本报告；两个旧任务共8文件在准备前后不变，不回签旧任务。

30项调用端聚焦检查及strict证据继续适用于未改的修复代码，不为准备文档重复全批。详见[修复报告](claude-company-native-call-repair.md)与[准备证据](claude-companynative-readiness.json)。

## 有效窗口后由开发方执行的交接

1. 同一用户创建的“Company 原生验收”会话目前idle，仍在旧dispatchfix副本，model元数据claude-opus-5/high。先以原生目录工具切换到新候选并结束该turn，不能同turn假定新内容已加载。
2. 下一turn核对宿主实际加载的新根、Company角色、company-native Skill与Company业务MCP，不仅看文件存在。缺入口/角色或来源不符即停止。
3. 主线程读取新私有小包，仅把本次问题、MRVL证券/cutoff、精确任务凭据、有效预算/硬截止和Company停止点放入Skill args。不给专业作者操作方连接凭据，不交其他结论，不代选证据。
4. 只调用Skill(company-native,args)。不构造Company Agent参数，不用worktree、remote、Hook、子CLI/SDK、通用开发角色或另一Skill回退。
5. 原Company作者实际context/catalog/query、必要计算及submit；唯一允许修订在原作者任务内完成，不通过再次调用Skill创建替代作者。返回后读取精确回执，分列业务验证、宿主观察和内容裁定。
6. 保存实际可得的Skill→作者、模型/五Skill/工具权限及query/计算/提交/原报告证据。失败、未验证如实保留，不用声明或文件hash补造作者身份。跨会话回告若仍受消息上限限制，不换入口绕过，可只读已有记录取得结果。

## 待明确的新窗口边界

沿用此前已讨论的最小Company方案：MRVL原冻结Gate、cutoff=`2026-09-28T12:35:32.208143Z`，当前claude-opus-5/high、专业角色inherit，最多3原生任务/15分钟，首次尝试开始固定硬截止，失败计入且即停，不自动重派或续期。停止于Company报告，不联网补采、不八维/Skeptic/CIO/Risk、不账户/交易。

**旧窗口在失败后已经停止；goal继续完成Change不自动重置已停止窗口或扩大模型额度。** 本次准备没有发送消息唤醒产品会话、没有原生Skill/作者执行、研究query/计算/提交或新报告；新增产品模型任务/来源网络/账户均0。

Company切片不替代完整Claude验收。原七项6.1/6.2/6.3/6.4/7.1/7.2/8.1全部保留，完整多维的Macro/研报/Market资料与配置缺口不隐藏；后续三个宿主场景、内容核对及最终人工完成批准仍需各自满足。未执行专项评估、主规格同步、归档或Git发布。
