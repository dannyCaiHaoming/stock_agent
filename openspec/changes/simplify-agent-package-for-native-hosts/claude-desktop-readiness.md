# Claude Code桌面接线：已安装文件与待核验项

- `source_id`: `claude-desktop-connection-readiness:20261007`
- `as_of`: `2026-10-07T15:20:19.582132+00:00`
- `retrieved_at`: `2026-10-07T15:20:19.582132+00:00`

## 本次交付

当前开发继续在Claude Code桌面Code tab进行；不要求独立CLI登录，不启动另一个模型CLI，不迁移桌面认证。宿主仍负责Agent执行，项目只补确定性业务工具和原生项目配置。

已在既有获准外置根新建桌面产品项目：

`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/claude-code-current-20261007/desktop-product-workspace`

- 270项精确审阅源，以此前批准的`source-reviewed`为基线，仅覆盖本次审阅的`product/mcp/research.py`、`product/hosts/INSTALL.md`和`product/hosts/claude-code/README.md`；并行Intake字节不纳入。
- 300项导出文件集合及SHA-256通过。导出操作方`package_content.py`不在产品载荷中，其本次实际源码hash单独留证，不冒充旧清单已有它。
- 项目`.mcp.json`只列Company，解释器/PYTHONPATH指向新副本；直接使用`--connection-env-file`读取相邻私有目录，不需要`--mcp-config`启动参数或继承`STOCK_AGENT_*`环境。
- 凭据没有复制进产品源码。连接复用既有Company请求/Gate，新增独立任务绑定新业务资源；旧任务、四份旧安装、公开样本、开发配置及1501项已有受保护文件字节不变。未读取或修改用户全局配置。
- 产品文件0444、目录0555仅为权限设置，不是OS强制源码不可写证明。

详见[结构化证据](claude-desktop-connection-evidence.json)。私有连接、任务packet、待生效权限配置和不含秘密的操作说明只保存在该外置根的`grants/desktop/`，不作为公开附件。

## 已验证的边界

46项受影响的确定性测试通过（19.878秒），OpenSpec strict通过。测试包含实际导出副本→任务准备→业务stdio查询，不只检查配置字符串：

- 无继承连接环境时合法私有文件可用；JSON其他键不会注入环境，显式文件优先于错误环境。
- 文件/父目录权限、symlink、相对或空路径、缺文件/字段、坏JSON、错误凭据和角色错配均在业务副作用前拒绝；文件失败不回退有效环境。
- 导出只选择指定MCP服务，不读取或复制秘密；非法服务、空/错误形状映射、相对及源码/目标内路径在创建目标前拒绝；默认三宿主导出保持原路径。
- 新桌面安装副本的initialize、tools/list和精确Company task context实际通过；错误任务凭据返回`NATIVE_RESEARCH_ACCESS_INVALID`，正式Company来源search返回`NATIVE_MATERIAL_SOURCE_ACCESS_FORBIDDEN`。

```bash
.venv/bin/python -B -m unittest tests.test_native_operator_preparation tests.test_native_research_history tests.test_native_research_connection tests.test_native_host_templates tests.test_native_package_export tests.test_native_entry_retirement
```

新任务仍只允许MRVL冻结Gate的1398条Company事实，cutoff为`2026-09-28T12:35:32.208143Z`。安装检查没有替研究作者选择或query事实、计算、提交报告；产品模型任务、来源网络和账户调用均为0。测试中的合成查询不冒充本样本原生研究。

## 桌面原生核验尚未完成

[官方Desktop说明](https://code.claude.com/docs/en/desktop)说明桌面与CLI共享项目`.mcp.json`等配置；这不等于本会话已经热加载了新文件。当前开发会话工具清单仍没有Company研究MCP或`runtime_company_analyst`，不得用通用开发Agent替代。

在桌面Code tab打开上述产品项目后，需要原生确认：

1. 实际发现的角色、Skill和Company服务确实来自该副本；同名用户级/桌面服务可能覆盖项目定义，不自动扫描或改写全局配置。
2. 采用受限产品权限并核对其生效。相邻私有`company-session-settings.json`只是待应用的原生规则，**当前未由项目自动加载**；尤其不能在bypass模式下凭deny字段宣称源码只读。主线程禁止源码/文件/命令/Web工具和prepare_task/search/fetch，专业角色只获对应业务工具。
3. 经获准方式交付私有任务packet，只向Company授予本任务task_ref/task_token，不交付操作方连接/准备凭据；当前packet尚未送入研究角色。
4. 核对有效模型、调用/时间上限与停止点后才能恢复Company研究。14:42:03Z开始的CLI窗口已停止并过期，不自动转移或重置到桌面；本次零模型准备没有恢复该窗口。

以上是实际剩余接缝，不是CLI认证问题；本轮工具没有创建或重载桌面产品会话的接口，也没有用Shell、SDK或开发Agent绕过它。未确认前保持`host_role_skill_loading=UNVERIFIED`、`native_permissions=UNVERIFIED`、`private_task_packet_delivery=NOT_DELIVERED`、`content_verdict=NOT_REVIEWED`。

## Change状态

仍为17/24。桌面业务接线修复和文件安装不等于6.3完整验收，三个宿主真实研究、独立Skeptic首轮、主线程综合、内容核对及人工完成批准仍未完成。OpenAlex不是本Company冻结Gate切片的前置；本轮没有配置、移除、替换或调用它，完整八维原有资料缺口保留。未运行专项Eval、Execution Replay、Regression、Calibration、Ablation或Promotion，未同步主规格、归档、暂存、提交或推送。
