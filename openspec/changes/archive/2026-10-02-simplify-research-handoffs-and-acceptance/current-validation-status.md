# 当前补验状态（2026-10-01）

本页保留2026-10-01验收结果；历史失败及原件保持原样，不形成重复重跑义务。2026-10-02最终发布收尾见 [archive-closeout.md](archive-closeout.md)：八维 Change 已另行验收归档，原共享归属阻断已有明确 Git 基线可分离。人工连续推进授权见 [批准记录](bounded-runtime-validation-approval.md)末节，候选晋升仍为 `NOT_PROMOTABLE`。

| 当前验收项 | 底层证明与适用范围 | 状态 |
|---|---|---|
| H01–H19 实现及确定性接缝 | [关闭矩阵](closure-matrix.md)、各组原执行记录；normal 修复相关89项、Eval 修复相关30项，新来源/反证接缝各组117/31等记录分开；分组有重叠，不汇成独立总案例数 | 对应范围独立复核及新来源增量复核完成 |
| 基本面→研报、期权定点 | [原真实执行记录](bounded-runtime-execution-evidence.json)，2/1子Agent；未受到本轮仅 Council Trace/Eval 包装修复影响 | 真实执行与主开发内容核对通过；不代表全八维完成 |
| fixture normal 完整闭环 | [新真实运行证据](normal-native-handoff-success-evidence.json)，`host-normal-2191734a-baa7-4c9e-a6ad-565b5ca00ec1`；实际双Specialist→主线程CIO→Risk→合法Trace/decision/report/内置确定性Eval | PASS；内置Eval不冒称独立语义评分 |
| 独立 Runtime Eval | [真实评分及收集恢复记录](native-runtime-eval-handoff-evidence.json)，`handoff-eval-normal-20261001-ZM36NZ`；独立Terra子会话完整读取冻结输入，原首稿收集/封装后五维PASS | PASS；原协调进程收集失败保留，不宣称该进程自动端到端成功 |
| predecision CIO | [本轮记录](predecision-native-handoff-validation.md)及[最终独立增量复核](independent-predecision-review.md)；用户批准新真实正反包替代验收输入，CIO读取七报告、查询事实、首稿合法终态 | PASS；原反证期间错误未传播，保留为非阻断缺陷；不声称上游稿已修复、当前账户适配或候选晋升 |
| Task6.6 独立只读复核 | [原独立复核](independent-review.md)保留；[新输入增量复核](independent-predecision-review.md)覆盖最终CIO及640项快照 | 已交付；H09补验及Task6.5通过，原包缺失不再是本次已批准输入的阻断 |
| Task6.7 最终完成批准及发布 | 原批准及本次明确归档授权均有效；此前共享归属阻断已有八维发布基线可安全分离，见[最终收尾记录](archive-closeout.md) | 完成：三个主规格同步、归档、限定提交及远端推送均已核实；任务30/30，其他用户修改未纳入 |

## 本轮已关闭的机械阻断

1. native CIO 消费证明沿原 Trace `events` 保存，避免写入消费者不接受的顶层字段；原 Schema、白名单及安全校验不改。
2. Eval 读取证明支持真实 `functions.exec` 中 JSON 实参包裹的 `tools.exec_command`：先解码实参，再解析精确 shell 路径，并验证完整工具输出。错误后缀、错误文件、部分输出仍拒绝，不执行包装代码、不修研究引用。
3. Eval 提示中的后续 CLI 使用准备进程的 `sys.executable`，避免登录 shell 把 `python3` 切换到缺少依赖的解释器；不硬编码本机路径进入产品源码。实际原评分已用同一依赖环境的既有收集和封装命令恢复，未重新调用或调整评分。
4. 新正反来源准备保留来源身份和新执行身份，来源数据包不重签；公司 Evidence 目录采用保真列式表示去除重复键，完整事实仍通过原查询读取。核心正向采集相对路径改从重验后的原来源包解析，并在读取前拒绝符号链接及越界。显式核心模式拒绝材料批次组合及自动回填，默认全维入口不变。
5. 显式独立反证 `frozen-gate` 沿已有白名单核验本次研究模型，不再误用 fixture 候选模型；该来源模式仍只允许 `runtime_skeptic`，fixture creation 的候选模型锁未改变。失败准备原件已保留，修复后仍复用同一公司/正向研究，不追加上游模型调用。
6. 独立反证首轮2400秒超时后，原派发与 Start 的 turn 身份证明：子 Agent 的 PreToolUse 同样携带父 session_id，原协调控制误将其送入长等待。修复仅从可信 Start 身份区分子任务，禁止其协调工具并要求返回研究；父线程原等待约束保留。attempt6真实完成，不再出现自等待。
7. 恢复 attempt index 显式传入实际 MCP 配置环境；任务提示准确区分本系统正向产物/第三方原始资料，明确 scope、assumption_id 和允许引用位置。attempt2–5失败原件保留，不自动改稿或放宽 Schema。attempt6最终7次非空canonical query、另7条运输事件，首稿合法保存；全部七份报告进入新 CIO 冻结输入。

## 证据复用及停止边界

- normal 的保护快照与运行前后完整文件清单在原 `invocation/process-result.json`；本轮后续仅修改 Eval 读取/提示和测试，未改变该 normal 的研究内容、CIO/Risk/Trace业务链。其证据只覆盖对应未受影响路径，不包装为最新全候选晋升证明。
- Eval 原提示、manifest、原始JSONL、stderr和退出结果不改；新收集结果与正式评分为单独产物，真实会话、输入、评分及hash仍由原运行层验证。修复后新增模型调用为0。
- 新来源补验前的原账为8次父进程启动，其中7次到达模型；研究/Specialist子调用11次、独立dev_eval子调用1次。本轮新来源另外启动9父/12研究子（公司1父1子、core1父5子、反证6父6子、CIO1父无子），包含所有失败轮；前置未启动模型的准备失败另记。可见父usage不等于完整链消耗，缓存不重复相加。
- 额外只读检查仓库已有记录的 `activate-cio-mrvl-host-VjA0aX`、`activate-cio-mrvl-terra-22F07B`、`QShuu9`、`gy9Dga` 和 `activate-cio-mrvl-prepare-gKRW3l` 原目录，均不存在。未搜索整个用户目录、未补造历史包。
- Task6.5已完成：新真实正反包及CIO合法终态经实际运行和独立内容复核通过。旧包保持缺失，不使用fixture、摘要或程序补造观点，不修改旧输入或锁。当前进度29/30，仅Task6.7最终人工完成批准及限定发布未完成。
- 已知非阻断项：原反证研发期间错误未被CIO传播但原稿未修复；CIO冗余输入和远端compaction重试导致高消耗。均已如实记录，不为追求效率数字新增模型调用，不包装为候选晋升PASS。

## 最终人工批准前核对

2026-10-01继续推进时只读核对：独立复核的640项源码清单全部仍匹配，完整映射hash仍为 `acb6109ca6e83a6259c8ff6f820623e1ae4d38f9fc30fbca1460541e6ee5fe49`；实际补验记录列出的7个CIO产物文件hash全部仍匹配。进程退出0、合法研究终态、未超时及原完整性证明仍成立。仅纠正本页查询次数，未修改产品、历史运行包或锁，未重跑任何测试/模型/Gate。

上述核对后的最终人工完成批准已由用户明确提交，见[最终批准记录](final-human-approval.md)，不是用运行授权或Reviewer结论替代。发布仅包含本Change相关hunk，不包含候选晋升或恢复原八维。工作区191项修改含其它任务工作现场，不允许全目录暂存。本次同步及严格校验已完成，但独立发布复核确认共享hunk缺少可恢复的实施前内容，无法安全分离；按规则停止发布，详见[发布归属记录](publication-scope-review.md)。Task6.7的人工批准子步骤已完成，其完整归档提交推送步骤保留未完成，不撤销实现完成批准、不扩大提交范围。
