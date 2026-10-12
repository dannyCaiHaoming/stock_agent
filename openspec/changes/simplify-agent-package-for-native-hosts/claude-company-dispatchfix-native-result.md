# 新副本 Company 原生实跑结果：重复误参，未产生研究报告

- `source_id`: `claude-desktop-company-dispatchfix-window:20261008`
- `as_of`: `2026-10-08T01:41:24.642925+00:00`
- `retrieved_at`: `2026-10-08T01:41:24.642925+00:00`
- Change：`simplify-agent-package-for-native-hosts`
- 结论：**新指引已实际加载，但未阻止主线程重复误参；Company 未执行，窗口已按失败停止。20/27，不是验收完成。**

## 授权与执行范围

用户明确要求：“授权新窗口，用新副本实跑Company，继续推进”。新窗口固定为UTC `2026-10-08T01:34:40.643875Z`—`01:49:40.643875Z`（北京时间09:34:40—09:49:40），最多3个原生任务/15分钟，失败计入、不自动重派或续期。当前主线程模型元数据为`claude-opus-5`、effort=`high`，专业角色应继承；没有Provider usage测量，也没有实际子模型执行。

仅消费`US:COMMON_STOCK:MRVL`既有冻结资料，cutoff=`2026-09-28T12:35:32.208143Z`，停止于Company报告。不联网补采、不八维/Skeptic/CIO/Risk、不账户交易；不改运行源码、配置、权限或认证，不使用子CLI、SDK或remote。

## 实际完成的加载与交付

1. 原桌面产品会话已完成原生目录切换，并结束该turn。
2. 下一轮实际宿主消息确认cwd、settings、MCP和Skills来自`desktop-dispatchfix-product-workspace`，并加载包含新主线程指引的根`CLAUDE.md`。不是仅凭静态文件认定加载。
3. 在确认加载后，向同一主线程交付新任务`t.4596c02cf3ff6e0711a9c8f2`及514字节私有小包位置，明确要求省略`isolation/model`。
4. 产品主线程报告已读取并核对任务引用/hash；其当前副本`portfolio-council` Skill调用实际可见。没有因此推定专业五Skill已执行。

候选为271项精确源/301项导出，根`CLAUDE.md` SHA-256为`703484a68af16dff3f595bf3078acfd033abd83a7a28d6872fd5b0f9ce91b391`。新任务hash为`acf5e6468bb7d931c5acca5bacaf288200634ab6eafcdbfe075187d7e9d86807`。不公开任务能力凭据、连接秘密或原始工具prompt。

## 失败与证据限度

产品会话中实际可见一次Agent工具调用；主线程停止报告明确承认仍传入`isolation=worktree`和`model=opus`，返回：

> Cannot create agent worktree: not in a git repository and no WorktreeCreate hooks are configured.

第一分歧仍在主线程→Agent，Company作者创建前失败。精简会话读取可见调用及停止报告，不含完整调用参数payload；因此参数值按主线程报告标注，不冒称从原始payload独立提取。`worktree`失败路径与错误相符。

**这次没有实际尝试省略字段。** 不能据此断言桌面拒绝省略、真实Schema强制这些字段、产品角色/MCP损坏或官方文档失效。实际JSON Schema的`required`集合仍未知。已确认根指引加载但同一误参复现，说明“补充指引交付”本身未达到行为复发预防效果；不能继续以相同提示、重新导出或再开窗口当作已验证的修复。

保守计主线程任务1＋失败委派1＝**2/3任务尝试**，不是模型请求/turn数或费用测量。产品会话已停止，最后活动时间为UTC `01:37:27.215Z`；没有使用余量重派、补worktree/Git/hook、换模型或转SDK/CLI。

| 项目 | 本轮结果 |
| --- | --- |
| Company专业作者 | 0，未创建 |
| 专业五Skill、实际模型及工具权限 | 未执行，不能由主线程加载推定 |
| 新任务context/catalog/query/计算/提交 | 会话未观察到Company MCP调用；精确目录tools/calculations/submissions JSON均0 |
| Company报告、draft_ref、report_id、回执 | 0，不存在可交付研究稿 |
| 内容裁定 | NOT_REVIEWED，无报告 |
| 后续阶段、来源补采、账户交易 | 未执行 |

## 停止后核对与回告限制

UTC `01:41:24.642925Z`只读核对新精确任务目录存在、三类JSON记录各0。候选完整导出检查通过，302个文件（含导出manifest）与原导出清单一致。旧任务4文件在两次停止后观察间保持不变。

首次开发方完整性命令漏传既有`verify_export`函数的`result`参数，出现TypeError且未写基线；读取签名、传入hash已核验的原manifest后检查通过，没有改产品代码或重跑模型。私有快照创建于01:37:45，后取得的宿主元数据表明研究主线程已在01:37:27结束，因此它**不是运行前基线**；原“运行中”注释由本记录纠正。hash只能说明相应字节/时段，不证明实际权限或作者身份。

产品主线程尝试通过SendMessage回告；其停止报告称宿主因自动跨会话消息达到10次而阻止发送，需用户在产品会话发言解除。精简事件可见发送尝试，但不含底层拒绝payload，故该限制按报告事实列示。开发方通过已授权的只读会话记录取得结果，没有换消息入口或创建会话绕过限制。该回告限制发生在研究派发失败之后，不是本次研究未启动的原因。

## 对Change的影响

- 3.9指引交付及其确定性覆盖成立；本次新增真实加载证据，但**行为问题未解决**。
- 6.3仍未完成，Company小切片没有报告；6.1/6.2/6.4/7.1/7.2/8.1亦未勾选，保持20/27。
- 下一处需要证据的是当前原生调用端能否形成正确参数，以及实际工具Schema是否有强制字段；不把重复错误包装成“省略不支持”。在该点获得有效诊断或修复证据前，不自动再次授权式重跑同一路径。
- 没有新增执行器、Hook控制、参数改写服务或模型后端；未执行专项Eval/Replay/Regression/Calibration/Ablation/Promotion，未归档、暂存、提交或推送。

结构化记录见[本轮限定证据](claude-company-dispatchfix-native-evidence.json)，此前交付修复保持在[修复报告](claude-native-dispatch-fix-review.md)，原窗口失败仍见[上一窗口结果](claude-company-deliveryfix-native-result.md)。
