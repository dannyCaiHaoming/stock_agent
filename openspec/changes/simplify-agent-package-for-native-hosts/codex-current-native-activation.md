# Codex优先：当前环境接线与实际加载阻断

- `source_id`: `codex-current-native-activation-summary:20261007`
- `as_of`: 2026-10-07T07:33:42.041505+00:00
- `retrieved_at`: 2026-10-07T07:33:42.041505+00:00

用户最新明确“直接用codex环境来验证，后面再搞Claude Code、OpenCode”，据此将验收顺序调整为Codex优先。沿用此前15个原生任务/30分钟上限，源检索9/正文15的已批准范围保持；不增加预算，不换来源或账户权限，不以单宿主替代最终三宿主门禁。

## 实际完成的接线

1. 在已授权外置验收根下建立`20261007-codex-native-first`，270项精确源：原批准源加v4实现候选的12项精确差异，Intake初始化继续使用原批准HEAD。独立导出当前Codex产品工作区，旧三宿主安装未覆盖。导出源码只读；这不是全进程隔离证明。
2. 建立与当前资源hash绑定的四类私有业务连接。私有入口仅从私有授权文件读取本角色连接凭据并运行现有`product.mcp.research`，不启动模型或另一宿主，不含模型SDK/派发/等待/重试逻辑，凭据不进入项目配置/Git。
3. 当前项目`.codex/config.toml`仅追加三角色和四MCP连接，原始字节完整保留为前缀；用户原模型、sandbox、开发角色、并发及原设置未改。三角色展开共享正文，原生配置禁shell/Web/App、read-only及对应业务服务工具限制；它们尚未成为实际权限证明。Skills引用指向新产品副本，未覆盖开发Skills。
4. 从新产品副本执行四个实际业务stdio initialize/tools/list，全部通过；Company精确任务context通过，Skeptic不暴露正向报告读取。开发权限probe与未来作者任务隔开，不冒充作者实际取证。源网络/账户0，新报告0。

## 实际当前宿主观察

当前turn工具元数据中没有research_context/query/submit/prepare工具；原生`spawn_agent(agent_type=runtime_company_analyst)`实际返回`unknown agent_type 'runtime_company_analyst'`，未创建研究子Agent。不能用普通开发Agent、通用shell研究或另一个CLI/SDK伪造已加载。当前会话尚未反映新项目配置；四服务stdio可用只证明确定性连接，不证明原生宿主可调用。

按保守额度核算，当前主任务预留1、失败的角色创建尝试计1，总计2/15，剩余13；创建成功的研究子Agent0、实际研究稿0。没有自动重试或重新派发。实际模型未知，不把project model配置当运行观测。

界面工具明确拒绝控制`com.openai.codex`自身（安全限制），没有通过其他UI技术/进程注入绕过。已使用项目配置完成可做部分；需由用户在Codex重新载入MCP/项目会话后，下一次turn先实际核对角色与工具可见性，再继续已授权验收，无需重复批准预算。

宿主官方说明支持项目MCP配置及服务重载，但本次未执行/观察到重载成功：[MCP配置](https://learn.chatgpt.com/docs/extend/mcp)、[App Server服务重载](https://learn.chatgpt.com/docs/app-server)。来源配置的既有缺口保留，切宿主不自动证明正文准备就绪；正式全链路仍须逐项核对依赖/截止点，不能绕过原Macro阻断。

## 发布与完成边界

本次`.codex/config.toml`追加及`.codex/agents/runtime_*.toml`是本机验收配置，不进入原生产品实现v4发布候选；原有开发/用户修改不被认领。外置私有连接、配置备份和入口不提交。实现源码未改，已有测试证据继续绑定相同源码；只做本次配置/安装/连接聚焦检查。Change仍17/24，6.2未完成；Claude Code/OpenCode后续，内容复核和最终批准/归档发布仍未完成。完整记录见[激活与实际拒绝](codex-current-native-activation.json)。

## 当前会话重载可达性补验

2026-10-07：实际`codex mcp list --json`正常解析当前项目配置，company/market/skeptic/cio均enabled且无disabled_reason，stderr为空。当前模型工具元数据仍未出现research工具；没有再次创建角色或消耗研究任务。确定性导出的当前协议包含`config/mcpServer/reload`，但现有daemon version实际返回控制socket不存在，因此没有连接proxy、发出reload或另起daemon。协议存在和配置可解析不等于本会话实际加载。需用户重新打开Codex，再在本会话先验证角色/工具；不重复申请已有授权。实际新模型/源检索/正文/账户调用均0，保守已计2/15，剩13。既有正文来源配置缺口仍保留；完整验收未通过。详见[codex-native-refresh-availability.json](codex-native-refresh-availability.json)。

## 2026-10-07 重启后的真实原生观察（覆盖前述未加载状态）

当前Codex已实际加载company/market/skeptic/cio业务工具。原生MCP的Company context、catalog及精确query成功；正式研究任务调用来源search被写前拒绝，形状合法的错误任务能力凭据也被拒绝。resources/list返回Method not found表示服务仅暴露tools，不再是unknown server。上述真实工具调用只证明对应原生业务接线；不证明研究作者、独立首轮、报告内容或完整验收。

按用户“继续”恢复后，操作方通过原生research_prepare_task准备了独立COMPANY_RESEARCH任务。Company可独立消费既有冻结Gate，本任务不依赖OpenAlex正文；完整八维仍保留Macro/研报/Market准备缺口，未省略material_inputs绕过旧阻断。实际spawn仍返回unknown agent_type runtime_company_analyst，未创建子Agent，不自动重试或用开发Agent替代。保守任务计3/15，剩12；研究子Agent0、报告0、来源网络/账户0。当前主线程精确turn_context模型元数据为gpt-6.1-sol，不等同于Provider执行证明或未执行的Specialist模型。22份公开原件及797项受保护源码hash均未改变。

用户明确没有OpenAlex配置。该凭证只属于当前资料正文适配器，不是Codex模型运行要求；现有官方Fed Gate中有2511字符已冻结政策文本，但不能机械冒充新的BODY_VERIFIED准备回执。未新增Provider、改写旧限制或放宽验收。完整记录见[codex-native-loaded-observation.json](codex-native-loaded-observation.json)。三宿主、独立首轮及内容/综合仍未完成，17/24不变，未归档/提交/推送。

## 2026-10-07 新会话观察及原生角色配置修复

用户批准新建的 Codex 验收任务 `01a115af-52e3-7680-bc3e-7e0a7975d641` 实际停止于 `STOPPED_NATIVE_ROLE_UNAVAILABLE`：Company 工具可见，研究角色不可见，未派生研究 Agent、未查询研究资料或提交报告。计入该任务主线程后累计 4/15，剩余 11；原硬截止为北京时间 17:40:24。

随后零模型检查复现了角色 MCP 部分配置的原生解析错误：只有 enabled/disabled_tools、没有 transport 的服务段报 `invalid transport`，完整连接段解析成功。已补全三个自有 Codex 角色模板及本机验收角色配置，保持每个角色仅启用对应服务、禁用 prepare_task 和原有通用工具限制；本机原配置已私有备份，不修改用户全局配置或旧只读安装。三个角色分别通过实际原生配置解析，16 项宿主模板/导出检查通过。此问题与会话角色不可见的因果关系仍须真实角色发现验证，不能据此宣布加载或权限 PASS。

22 份公开原件保持原 hash。旧 v4 候选补丁及导出证据仅覆盖修复前版本，本次三个角色模板和一份测试是后续增量，不回签旧安装。记录见 [codex-native-role-transport-check.json](codex-native-role-transport-check.json)。当前 17/24，真实研究、独立首轮、内容及三宿主验收未完成，未归档、提交或推送。
