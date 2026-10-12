# 修复副本 Company 原生尝试结果

- `source_id`: `claude-desktop-company-deliveryfix-attempt:20261008`
- `as_of`: `2026-10-08T00:33:33.695792+00:00`
- `retrieved_at`: `2026-10-08T00:33:33.695792+00:00`
- 结论：**上下文交付已成功；原生委派失败；Company报告未生成。**

## 本轮实际推进

用户明确授权使用修复副本和新窗口。沿用MRVL冻结Gate，只执行Company，最多3个原生任务，固定UTC `00:23:23.917061—00:38:23.917061`（北京时间08:23:23—08:38:23），失败不自动重派，不续期。

1. 原产品会话的宿主消息明确目录、项目settings、MCP与Skills已切入`desktop-deliveryfix-product-workspace`。不是仅凭静态配置判断。
2. 产品主线程读取514字节小包，使用精确任务`t.f1cb9300748705dc10c33090`。原生工具调用列表中已观察到`research_context`调用。
3. 产品主线程回报：角色、MRVL和cutoff一致；允许事实1398项，默认页32项，下一偏移32，完整输出Schema返回，没有再次超限。原生调用与已返回Skill参数相互对应；原始含凭据转录不公开。它证明本轮交付接缝，不证明专业作者执行。
4. 主线程实际调用了修复副本的`portfolio-council`。专业Company作者未创建，因此不能据此宣称其五项Skill预加载、工具权限或研究推理通过。

## 实际失败及责任边界

产品主线程回报失败调用参数：

```text
subagent_type=runtime_company_analyst
isolation=worktree
model=opus
```

派发错误：

```text
Cannot create agent worktree: not in a git repository and no WorktreeCreate hooks are configured.
```

这些参数没有遵循本轮不创建worktree、专业模型继承的指令。Company模板本身仍为`model: inherit`，不是模板要求切换模型，也不是MCP、冻结资料、任务授权或CLI登录失败。失败发生在创建专业作者之前。

进一步只要求原主线程依据已有签名说明，不试调用、不新增工具或研究：其展示的`isolation`类型只列`worktree | remote`，没有明确的本地非worktree值，也未标可省略；`model`说明允许省略，但展示类型未标可省略。**实际是否接受省略仍未知，不能把“去掉参数即可成功”写成已验证修复。**

没有为绕开错误执行`git init`、创建worktree、配置hook、改权限、另开CLI/SDK、换通用开发Agent或新增项目派发器。后续真实研究需要宿主可用的、符合本轮边界的原生委派入口；这不是增加来源或账户权限能解决的问题。

## 成果与消耗

| 项目 | 本轮结果 |
| --- | --- |
| 原生context | 成功回报，分页与完整Schema正常 |
| 主线程任务 | 1 |
| 失败专业派发尝试 | 1 |
| 保守尝试计数 | 2/3，不是Provider调用或费用测量 |
| 实际Company作者 | 0 |
| 事实query / calculate / submit | 0 / 0 / 0 |
| draft_ref / report_id | 无 / 无 |
| 业务报告裁定 | NOT_RUN |
| 内容裁定 | NOT_REVIEWED |

开发侧在UTC `00:30:58.190658`只读核对精确任务目录，`tools`、`calculations`、`submissions`中的JSON文件各0，与产品线程停止回报一致。没有报告可读取、展示或归档；不能用合成稿补齐。

## Change进度与停止点

- 保持**19/26**。本轮补上修复后的原生交付观察，不勾整个6.3；三宿主、完整专业/独立首轮/综合、三份报告内容及最终人工批准要求保持。
- 本轮只更新当前Change的验收记录与映射，没有修改产品源码、运行安装、配置或旧任务，没有重签资源绑定。
- 未重跑已有93项确定性测试；其有效范围仍以原证据为准，不把它们当本轮研究PASS。
- 没有新增来源、八维、Skeptic、CIO、Risk、账户或交易调用；未运行专项Eval/Replay/Regression/Calibration/Ablation/Promotion。
- 研究已经停止，未使用剩余额度自动重派，未延长窗口；未归档Change、暂存、提交或推送。

结构化记录见[本轮限定证据](claude-company-deliveryfix-native-evidence.json)；最新授权与进度见[tasks.md](tasks.md)，完整验收边界见[native-acceptance-plan.md](native-acceptance-plan.md)。旧失败和准备快照均保留，不回签。
