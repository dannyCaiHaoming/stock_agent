# Claude映射模型：本轮候选与检查

- `source_id`: `native-package-claude-mapped-readiness-report:20261008`
- `as_of`: `2026-10-08T13:32:02.833977+00:00`
- `retrieved_at`: `2026-10-08T13:39:19.938855+00:00`

## 范围与实现

按用户明确的Claude优先请求及已批准计划，只推进Claude Code，Codex/OpenCode的原生验收与内容义务在[遗留清单](host-backlog.md)保持未完成。当前OpenSpec严格校验通过，CLI确认24/29、剩余5项；两项迁出不是两项完成。

角色继续使用`model: inherit`，三个native Skill无model/isolation覆盖。用户明确的`opus`→`gpt-6.1-sol`映射由已有CC Switch/宿主配置负责，项目只更新主线程/安装/运行说明与验收口径。分别记录桌面声明`claude-opus-5/high`、用户批准映射及实际主子观察；不要求同名，不将声明或转录当Provider wire证明。不新增模型路由、CC Switch Client、Python模型检查器或模型API/SDK，不读取其数据库/凭据，不修改用户全局配置。

## 确定性证据

| 检查 | 实际结果 | 证明边界 |
| --- | --- | --- |
| 现有模板与精确导出测试 | `tests.test_native_host_templates`、`tests.test_native_package_export`共29项，13.385秒，exit 0；指定源码/测试hash未变 | 包含inherit、固定角色/Skill、精确工具、缺源/漂移/冲突拒绝及其他宿主根入口不变；不是原生运行 |
| 当前规格与文档 | OpenSpec strict通过；18份相关文档、150个本地链接无缺失，空白/末尾换行和限定diff检查通过 | 不是模型或研究内容检查 |
| 新精确来源 | 原274项批准源仅覆盖Claude main-thread、README及INSTALL三项；仍274项，不复制dirty树，并行Intake排除 | 业务源保留批准字节，不认领并行变更 |
| 仅Claude导出 | `claude-mapped-current-20261008T132228Z`，308个文件（含manifest），verify_export通过 | 不覆盖旧候选，不生成/激活其他宿主安装 |
| 新任务与实际stdio | 新Company/独立Skeptic/Market三任务及CIO连接；合法context、错误任务能力拒绝、Skeptic禁读与分页Schema通过 | CIO任务等真实新正反报告；目录/传输检查不是作者消费 |
| MRVL统计 | 目录27项、16,663 UTF-8字节；精确血缘首个页64/1,518 ID | 未完整读取血缘，未替作者选指标或query事实 |
| 保护 | 38项指定源码/测试及1,832项指定旧文件准备前后hash相同；新包/来源582文件另记录窗口前基线 | hash不是OS强制只读证明 |

测试日志SHA-256：`7fc84c2ae671ec29970896f1430f864d9a566932b439331a6e017a073609ab6d`。结构化白名单结果、精确来源/hash及私有回执hash见[准备证据](claude-mapped-readiness.json)。原始日志、任务能力凭据、连接文件和转录留在私有外置目录，不进入Git。

一次性操作方准备脚本首次误以为导出器属于274项运行包清单，发生KeyError，尚未创建目标。已改为复用聚焦测试绑定的操作方导出器；运行包清单不变，第二次零模型准备通过。该错误不是原生作者错误，也没有消耗模型重试。

## 已批准的新原生窗口

- 开始：`2026-10-08T13:32:02.833977Z`。
- 统一截止：`2026-10-08T14:02:02.833977Z`，不因等待消息/批准而自动续期。
- 上限：5原生任务；同一产品主线程1、Company/Skeptic/Market各1，第5项只用于宿主自动辅助，不用于重派。不是Provider请求/token/费用计数。
- 样本：fixture `SEC-AAA`/cutoff `2026-01-31T23:59:59Z`正反/CIO与原Risk；独立MRVL `TECHNICAL_STRUCTURE`/cutoff `2026-09-28T12:35:32.208143Z`/benchmark SPY。输入/Gate/任务/报告不混用。
- 首个原生/Skill/业务错误、未批准目标、加载/权限未知、隔离不可证、源码/旧产物变化或截止即停止。不改参重试、修订、重派、换入口/CLI/SDK或续期。

第一条跨会话目录切换消息返回20秒启动等待超时，工具说明仍可能稍后处理；已在目标转录中看到消息，但尚未看到其执行新目录切换，最后观察仍为旧候选。未重复投递，已订阅一次idle通知。此处只记录观察，不把消息出现当目录加载成功，也不把暂未观察到作者写成确定的模型调用总数。

当前业务原报告、原生工具池/专业Skill、Skeptic初始输入、主子模型及内容均未通过本窗口验收；6.1/6.3/7.1/7.2/8.1仍未勾。无来源网络/账户、专项Eval/Replay/Promotion或归档/提交/推送。旧窗口及结果保持原时点，不回签成功。
