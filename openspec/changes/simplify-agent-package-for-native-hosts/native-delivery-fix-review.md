# 原生交付故障修复与当前完成边界

- `source_id`: `native-delivery-fix-review:20261008`
- `as_of`: `2026-10-07T16:26:21.297026+00:00`
- `retrieved_at`: `2026-10-07T16:26:21.297026+00:00`

## 结论

**开发交付接缝已修复；Company真实报告和整个Change仍未完成。** 当前19/26：原24项不删不降标，新增并完成3.7“小型私有授权”、3.8“上下文精确分页”；原6.1–6.4、7.1–7.2、8.1七项仍未完成。

项目继续以Claude Code、Codex、OpenCode为原生执行底座。此次只有已有Python业务工具、MCP参数、操作说明及聚焦测试变化，没有新增Agent架构、模型API/SDK、任务调度器、重试循环或后台执行服务。

## 本次Company真实尝试

用户明确要求使用新授权恢复Company。原桌面产品会话实际读取了527字节小型授权，使用正确任务`t.d3657c083eb28ec1b64fe532`调用原生`research_context`，没有沿用旧CLI任务。期间产品会话再次要求同会话确认；开发方已澄清这是用户主动恢复，不是开发方自行重试，没有修改权限设置或绕过真实审批。

本次窗口为UTC `2026-10-07T16:06:51.593622Z`—`16:21:51.593622Z`（北京时间10月8日00:06:51—00:21:51）。原生工具返回：

> result (119,722 characters across 1 line) exceeds maximum allowed tokens

产品会话报告尚未读取宿主落盘正文，所以不能称其已消费权限和输出Schema。实际Company专业委派0，事实query/计算/提交/报告/回执均0；没有运行中的专业任务，没有自动续期。主研究任务数由产品会话报告为1，协作跟进turn不伪装成专业Agent执行或Provider usage测量。此结果是实际交付失败，不是缺Company角色、CLI未登录、OpenAlex缺配置或研究内容FAIL。

只读量测该任务显示：1398项`allowed_evidence_ids`占109,479字符，输出Schema8128字符。资源漂移门禁此次没有拒绝正确任务；之前旧授权的RESOURCE_DRIFT失败仍原样保留。

## 已实现的修复

### 3.7 小型任务授权由现有准备入口生产

`product.tools.prepare task`增加可选`--agent-grant-output`。完整操作方grant兼容不变，另写本任务的精确引用/凭据、role/capability/security_id/cutoff/task_hash及来源时点；不交付事实ID、资源绑定、大task、依赖正文或连接/准备秘密。输出须为源码外私有绝对路径，非法、同路径、已有文件及symlink在创建任务前拒绝，0600/O_EXCL写入且不打印秘密。专业角色仍通过受限业务工具取资料，不将短包当作者认证。

### 3.8 context精确分页

`research_context`增加`evidence_offset`、`evidence_limit`，默认32、最大64。返回原始ID页、`allowed_evidence_total`、`next_evidence_offset`及完整输出Schema。服务端保存全部允许集，每页先校验任务凭据、输入/Gate和资源绑定；目录不计实际事实查询，计算输入枚举改为数量，计算及血缘仍由既有工具读取。未截断JSON、删事实、扩大工具/来源权限或改变两稿门禁。

## 验证与版本边界

93项受影响测试通过，39.024秒；本Change strict通过。大型合成任务验证1398项长ID完整翻页无遗漏/重复、真实stdio响应、合法query/submit、错误页参数/凭据/任务/资源漂移拒绝，以及目录不冒充取证。第一次92项中有1项新测试失败：它在被拒首稿后再次提交完整稿，原两稿/精确修订检查正确拒绝；已分离测试作者场景，不放宽产品门禁。原失败和最终结果均记录在[结构化证据](native-delivery-fix-evidence.json)。

在原获准外置根新建`desktop-deliveryfix-product-workspace`及对应审阅源/私有授权，仅对上一桌面270项批准来源覆盖以下四项：

- `product/mcp/research.py`
- `product/tools/research.py`
- `product/tools/prepare.py`
- `product/hosts/INSTALL.md`

并行Intake仍为原批准字节；300项导出完整性通过。旧桌面导出前后完整性不变，旧任务未重签、旧源码未就地修改，其他旧安装不作为写入目标；开发/用户全局配置不改。新文件权限仍不是OS强制只读证明。

新任务`t.f1cb9300748705dc10c33090`绑定新副本：

| 交付项目 | 实际结果 |
| --- | --- |
| 由已实现CLI生成的agent-grant | 514字节，0600 |
| 首次context正文 | 13,055字符；原失败响应119,722字符 |
| 完整允许事实数 | 1398，服务端未删减 |
| 首/次页 | 各32项，偏移准确、无重叠、Schema相同 |
| 错任务凭据 | `NATIVE_RESEARCH_ACCESS_INVALID` |
| 正式Company来源search | `NATIVE_MATERIAL_SOURCE_ACCESS_FORBIDDEN` |
| 新任务研究query/计算/提交 | 均0 |
| 新模型/来源网络/账户调用 | 均0 |
| 原生产品会话切换/新窗口 | 未执行、未恢复 |

上述新副本结果是实际确定性stdio交付证明，**不是修复后原生Agent执行证明**。旧产品会话仍指向旧副本，不能直接使用新任务；任何实际恢复都须使用新副本/精确小包和有效窗口，不能从历史余量或准备完成推导续期。

## 逐项复核剩余任务

| 任务 | 当前真实缺口 | 不再作为前置的问题 |
| --- | --- | --- |
| 6.1 | 三宿主各自有效模型/阶段/预算/停止点、实际权限与合法资料依赖；Claude此次窗口已结束 | CLI登录不是Claude桌面前置，不重复索取已批准安装范围 |
| 6.2 | Codex真实专业角色/Skill、独立首轮、报告及主线程综合；旧角色unknown结果未被后续真实成功替代 | 研究MCP已实际可见，不再笼统称所有工具未加载 |
| 6.3 | Claude修复后Company实际委派与报告，然后才是完整场景的Market/独立Skeptic/综合证据 | 桌面角色/MCP已可见，短授权和大context故障已有代码修复 |
| 6.4 | OpenCode真实primary/subagent、工具面和首轮隔离及报告/综合 | 模板存在不等于原生通过，不能用Claude代跑 |
| 7.1 | 三宿主原报告的依据/期间单位/重要反证/限制与非动作核对 | 不新增自动模型评委，结构合法不替内容裁定 |
| 7.2 | 上述实际证据闭合及一次人工最终完成批准 | 本报告补映射，不宣称代码减少或token/成本改善已测得 |
| 8.1 | 满足完成条件并获批准后同步主规格、归档、限定提交推送 | 尚未归档、暂存、提交或推送，不夹带其他Change |

完整八维的Macro配置限制、研报/Market来源不足及BODY_VERIFIED正文0仍保留。OpenAlex是既有文献适配器，不是Company冻结研究或宿主加载前置；此次未配置、调用、替换或移除它，不能用Company独立切片掩盖完整研究缺口。

## 明早目标与执行边界

用户希望明早完成是当前推进目标，不等于删掉三宿主验收、自动增加产品模型/来源预算或提前批准最终归档。已完成不依赖这些条件的交付修复、明确源副本和任务准备；没有承诺已实现无人值守目标调度，也没有创建后台模型执行器。当前未运行专项Eval、Execution Replay、Regression、Calibration、Ablation或Promotion；研究级Risk和账户能力未开放。
