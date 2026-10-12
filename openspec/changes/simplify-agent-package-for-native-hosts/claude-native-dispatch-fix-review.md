# Claude 原生委派失败复核与主线程指引交付修复

- `source_id`: `claude-native-dispatch-fix-review:20261008`
- `as_of`: `2026-10-08T00:47:35.379988+00:00`
- `retrieved_at`: `2026-10-08T00:47:35.380139+00:00`
- Change：`simplify-agent-package-for-native-hosts`
- 结论：**指引交付修复完成；原生委派尚未重新验证；Change 未完成（20/27）。**

## 1. 真正失败在哪里

原窗口 UTC `2026-10-08T00:23:23.917061Z`—`00:38:23.917061Z` 已停止并过期。产品目录/settings/MCP/Skills切换生效后，原生 Company `research_context` 成功返回；产品主线程回报允许事实1398项、首个页32项、下一偏移32及完整Schema。此前的大响应超限已不再是这次派发失败的原因。

第一处分歧在**主线程调用原生 Agent**：指定了`runtime_company_analyst`，却额外传入`isolation=worktree`与`model=opus`。派发层返回：

> Cannot create agent worktree: not in a git repository and no WorktreeCreate hooks are configured.

显式`worktree`是已确认的失败触发条件，发生在Company作者创建之前；不是Company研究工具、冻结资料或CLI登录失败。调用级`opus`也偏离已批准的专业角色`model: inherit`，但作者未创建，不能宣称子模型实际执行或发生实际换模。

该次保守计主线程1＋失败派发1＝2/3任务尝试，不是Provider usage测量；专业作者、研究query、计算、提交、报告与回执均0。原始停止结果及限定证据分别保留在[原窗口结果](claude-company-deliveryfix-native-result.md)、[原窗口证据](claude-company-deliveryfix-native-evidence.json)，不改写成修复后成功。

## 2. 需求与实现调整

[官方 Subagents 文档](https://code.claude.com/docs/en/sub-agents)说明普通子Agent从主线程当前目录启动，`worktree`是可选额外隔离；调用级模型覆盖优先于角色的`model: inherit`。这说明不应把Git/worktree或独立CLI认证当普通桌面Company研究前置，**不证明当前桌面工具已接受省略字段**。展示的`worktree | remote`联合类型也不是实际JSON Schema的`required`集合。

检查发现一个可修复的交付缺口：旧导出根`CLAUDE.md`只拼产品规则与CIO正文，没有自动加载Claude专属主线程操作说明。尽管原临时交接已明确禁止worktree/模型覆盖，仍发生误参；本次修复是复发预防，不能证明缺指引是唯一原因，更不能保证模型必然遵从。

已先更新Proposal、Design **D2.2**、`native-agent-package`两个场景和Tasks **3.9**，再完成：

| 改动 | 实际行为及边界 |
| --- | --- |
| 新增`product/hosts/claude-code/main-thread.md` | 普通研究使用实际加载专业角色；最小调用省略`isolation/model`；不猜`none/local`、不创建Git/worktree/hook、不转remote/SDK；实际省略被拒时原样报告，不自动重派 |
| `product/tools/package_content.py:export_package` | Claude根入口按产品规则→已审阅宿主指引→CIO正文拼装；只交付正文，不生成或执行Agent调用 |
| 精确源约束 | 指引必须在审阅清单；缺失报`NATIVE_PACKAGE_MAIN_THREAD_INSTRUCTIONS_MISSING`，hash漂移报`NATIVE_PACKAGE_REVIEWED_SOURCE_DRIFT`，均在目标创建前拒绝 |
| Claude README与INSTALL | 解释实际加载入口、当前目录与模型继承、官方语义和实际宿主观察的区别 |
| 专业角色/其他宿主 | 共享角色及Skill正文未改；三专业角色仍inherit及原工具/Skill白名单；Codex/OpenCode根入口不变，不要求新增Claude指引 |

没有新增executor、参数派发器、SDK/API模型后端、等待/重试控制器或跨宿主事件平台；没有改变运行权限、全局配置或旧任务绑定。

## 3. 聚焦验证，而非研究验收

已实际执行：

```bash
.venv/bin/python -B -m unittest tests.test_native_package_export tests.test_native_host_templates tests.test_native_entry_retirement
```

结果：**25项，7.271秒，exit 0，OK**。覆盖精确根入口字节、无额外参数的最小例、缺源/漂移写前拒绝、旧包不变和恢复、专业定义不变、Codex/OpenCode根入口不变以及旧正常模型启动不回退。OpenSpec strict校验亦通过。测试通过后勾选3.9，并重新读取apply指令确认 **20/27、remaining 7**。

这些是确定性交付及契约证据，没有fake Agent成功稿，也没有模型调用；不认证新指引实际加载/遵从、省略字段被接受、专业五Skill、实际模型、工具权限、研究质量或内容。没有为文档再跑全批，也未运行专项Eval、Replay、Regression、Calibration、Ablation或Promotion。该改动不由网页preview执行，因此未启动无关Web服务。

## 4. 新候选和独立任务已准备

在既有获准外置根`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/claude-code-current-20261007`新建：

- `desktop-dispatchfix-source-reviewed`与`desktop-dispatchfix-approved-source-manifest.json`；
- `desktop-dispatchfix-product-workspace`；
- 私有`grants/desktop-dispatchfix/company-task-grant.json`及`company-agent-grant.json`。

从上一版270项精确批准源开始，仅覆盖Claude README、INSTALL并新增主线程指引，共**271项源、301项导出**；没有机械纳入当前dirty树。原Intake批准字节保持不变，当前并行Intake/Tiger及其他Change未混入。新导出完整性、根入口精确拼装通过；三专业角色导出字节与旧修复副本完全相同，旧副本和原manifest保持原字节。产品文件0444/目录0555是文件模式约束，不冒称同用户OS强制只读。

| 对象 | SHA-256 |
| --- | --- |
| 精确源manifest | `bcee581547cd447cd20fb60a43160897df3252c2b844d0862fb35e0ff6d2108d` |
| 导出manifest | `660dc380f7fc2dd659dfb1e95c2e545e7c382f912c35037fdef3d72795643ba7` |
| 新根`CLAUDE.md` | `703484a68af16dff3f595bf3078acfd033abd83a7a28d6872fd5b0f9ce91b391` |
| 主线程指引源 | `9d6a2de9044a317188be63467dac6eef6d4ac09972e1330b532ea1c95a2a4c0e` |
| 本次开发导出器 | `cf732bfb7e78fbc7946b160ad61ddf5c262aa78a28611d8cb6bf0a9603e1f3da` |

开发导出器作为操作方工具单列hash，不擅自塞入产品载荷。私有Company连接仍沿用原安全文件位置，不复制或输出连接秘密。

新候选的现有确定性准备入口已创建独立业务任务：

- `task_ref`: `t.4596c02cf3ff6e0711a9c8f2`；
- `task_hash`: `acf5e6468bb7d931c5acca5bacaf288200634ab6eafcdbfe075187d7e9d86807`；
- 角色/能力：`runtime_company_analyst` / `COMPANY_RESEARCH`；
- 证券/cutoff：`US:COMMON_STOCK:MRVL` / `2026-09-28T12:35:32.208143Z`；
- 小型私有授权：**514字节、0600**，不公开其中凭据；
- 准备调用模型数0，旧任务字节未变；没有回签旧task或扩展其能力。

业务任务准备不等于原生模型任务或执行窗口。**新候选尚未切入产品会话，新Agent调用、模型、研究来源网络和账户调用均未发生。**

## 5. 剩余工作与停止边界

| 未完成任务 | 当前缺口 |
| --- | --- |
| 6.1 | 三宿主完整实际场景的当前会话、权限、模型预算和停止点；本次Company准备不替代整项授权 |
| 6.2 | Codex真实专业作者、完整阶段与独立首轮证据，旧unknown agent_type尚无成功替代 |
| 6.3 | Claude首先需要真实观察省略参数的调用；Company作者/五Skill/权限/报告未验证，更未完成全部场景 |
| 6.4 | OpenCode真实角色执行、独立首轮及工具隔离证据 |
| 7.1 | 三宿主原报告及对应内容核对；目前没有本次新Company稿可核对 |
| 7.2 | 映射继续保留缺口，三宿主必要证据与一次人工最终完成批准尚缺 |
| 8.1 | 完成批准后的主规格同步、归档、限定commit/push和远端核验；本轮均未执行 |

下一次Company实际验证应在有效明确新窗口内，先请求切换新候选目录、结束当前turn，再依据宿主加载消息确认来源；使用新任务小包，按根指引省略额外`isolation/model`。实际宿主若拒绝省略，保留原错误与未执行部分，不猜参数、不自动重派、不换后端。旧15分钟窗口及剩余1/3不自动恢复；本次开发请求和`/goal`不扩展成无限模型、其他宿主或后续阶段授权，未开启后台目标或定时器。

即使Company成功，也不能勾完整6.3或缩减三宿主/内容目标。完整八维的原Macro配置及研报/Market正文限制继续保留，不以Company冻结Gate可用宣布已解决。没有全仓全绿、真实用量/成本改善或候选晋升结论。

机器可读范围见[限定证据](claude-native-dispatch-fix-evidence.json)，最新准备状态见[验收清单](native-acceptance-plan.md)，规格→实现→验证对应见[实施映射](implementation-map.md)。
