# Company调用端诊断与原生入口修复

- `source_id`: `claude-company-native-call-repair:20261008`
- `as_of`: `2026-10-08T02:45:11.866992+00:00`
- `retrieved_at`: `2026-10-08T02:45:11.867078+00:00`
- Change：`simplify-agent-package-for-native-hosts`
- 当前：**21/28**；调用入口配置已修复并通过零模型检查，**尚未安装或实际执行新入口，不是Company研究成功或Change完成**。

## 1. 查明了什么

从指定Company会话的官方本地导出提取两次原始Agent tool_use，而不是只采信主线程自述：

| 原生调用时间（UTC） | 原生记录中的参数 | 实际结果 |
| --- | --- | --- |
| 2026-10-08 00:25:26.946 | runtime_company_analyst、worktree、opus | 00:25:26.963，worktree错误，作者创建前失败 |
| 2026-10-08 01:36:54.571 | runtime_company_analyst、worktree、opus | 01:36:54.585，同类失败；新根指引已加载仍复发 |

同一会话2026-10-07 15:33:16.571/15:39:45.124两份prompt_snapshot中的Agent input_schema一致：required只有description/prompt；isolation/model均可选、无default。三字段最小Agent调用通过真实捕获Schema的确定性验证，错误worktree/opus组合也能通过Schema——**Schema合法不等于符合本次授权**。

因此已排除“工具要求必须填这两个字段”，第一处确认的错误是主线程→原生Agent的调用输入带了未经本次授权的覆盖；worktree触发非Git目录错误，不是Company MCP、资料或研究稿错误。继续添加同样的提示无法构成修复。

## 2. 还有什么不能定论

- 捕获的是较早两份原生Schema快照，桌面CLI pin为2.1.289；不是每次失败前的新抓取，也不是独立CLI 2.1.291的证明。
- 原生tool_use已经包含错误字段，但echoWireToolInputs=false，未取得Provider wire输入或更上游转换代码。不能仅凭该记录断言字段必由模型生成，或认定桌面桥接/默认处理存在某个已证实缺陷。
- 两次失败都没有实际省略Agent字段；本轮也不消费旧窗口来试派。因此不宣称当前桌面Agent省略已经实际成功。
- 宿主程序目录访问申请存在解析失败，未读取或修改厂商程序。没有为诊断绕过权限、关闭TLS校验、改认证、升级或patch应用。

本修复处理项目可控的调用接缝，不假称修好了未经定位的厂商内部代码。

## 3. 修复不再依赖模型拼Agent参数

旧路径：主线程生成Agent调用 → 仍填worktree/opus → 作者创建前失败。

新路径：主线程调用原生Skill(company-native,args) → **Claude Code自身**按固定frontmatter创建原Company角色。

新增配置`product/hosts/claude-code/skills/company-native/SKILL.md`：

```yaml
context: fork
agent: runtime_company_analyst
background: false
user-invocable: false
```

当前捕获的Skill Schema只允许skill/args，additionalProperties=false；isolation/model不能作为该调用的额外参数。Skill正文只转交本次独立问题、证券/cutoff、精确任务授权、预算和停止点，不复制研究方法或预选证据。模型继承、原角色正文、五个预加载Skill和精确业务MCP工具不变；无Skill级model/isolation/permissionMode/allowed-tools/hooks覆盖。

这是Claude的原生配置和安装映射，**没有项目派发器、参数改写Hook、SDK/子CLI、等待控制器、重试或生命周期平台**。共享portfolio-council仍是用户入口，四职责不增加；Market/Skeptic路径未改，CIO仍是明确综合阶段的当前主线程。新入口缺失、角色不可用或宿主拒绝时停止，不回退Agent重派或续期。

[官方Skills文档](https://code.claude.com/docs/en/skills)说明context fork Skill内容成为任务prompt，自定义agent提供system prompt/model/tools/permissions，不继承主对话历史。这个Skill配置不是Agent(subagent_type=fork)复制父历史；本轮仅Company，不借此声称Skeptic隔离已验收。官方说明是配置依据，仍不代替本机实际观察。

## 4. 实现与检查

- 洁净导出把精确已审阅的源原字节映射到`.claude/skills/company-native/SKILL.md`，仅Claude安装此发现入口；其他宿主保留自己的配置与共享方法。
- 缺源/hash漂移/与共享Skill同名目录冲突在创建目标前拒绝；不覆盖旧包，恢复原源后可重新导出。
- 根CLAUDE.md加载更新的薄主线程指引，Company例子改为skill/args，不再生成Company Agent参数。
- 新增五项用例覆盖捕获Schema、固定角色/五Skill、额外参数拒绝、精确映射与拒绝/恢复；原受影响用例继续运行。没有fake Agent或模拟宿主成功。
- **30项聚焦检查全部通过，9.671秒，exit=0**。384项产品/焦点测试字节前后不变；这只是测试写入范围观察，不是OS保护、实际作者或权限证明。
- **OpenSpec strict通过**；apply确认3.10完成、21/28、原七项保留。17项本轮文件的限定格式/常见凭据模式检查通过，捕获Schema与两份原生快照共四处精确相等；不是完整发布审查。
- 首次格式包装命令把`git diff --no-index --check`表示普通文件差异的exit=1误判成格式错误，17项诊断均空；用合成干净/尾空格正负例确认exit=1/3的区别后，修正检查器分类并通过，没有为此改产品源码或重跑模型。该开发检查错误保留在结构化记录，不包装为产品测试失败。

真实命令、输出、实现hash和范围见[检查证据](claude-company-native-call-check.json)；原始调用的安全白名单见[诊断证据](claude-company-native-call-diagnosis.json)，捕获Schema在`tests/fixtures/native-hosts/claude-code-2.1.289-tools.json`。原转录、prompt、task_token、连接秘密、完整metadata和思考块不进入这些文件。

## 5. 本次没有偷偷重跑

本次用户请求授权开发诊断与修复，不自动开启研究窗口。新增产品模型任务、专业作者、Company报告均0；未发送消息唤醒旧产品会话、未安装/激活新包、未创建新任务或改旧安装/授权/hash。原失败与旧UNKNOWN记录保留为原时点快照，新发现另列。

下一项实际证据应来自有效授权窗口中的新入口发现、Skill→原Company作者、实际模型/五Skill/工具权限、query/计算/提交和原报告，不再沿同一Agent误参路径重试。原七项6.1/6.2/6.3/6.4/7.1/7.2/8.1仍未完成，三宿主完整场景、内容核对和人工最终完成要求不变。

本轮未执行专项Eval/Execution Replay/Regression/Calibration/Ablation/Promotion，未同步主规格、归档、暂存、提交或推送。
