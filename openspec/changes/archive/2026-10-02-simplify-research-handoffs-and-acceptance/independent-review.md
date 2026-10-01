# H01–H19 独立只读复核记录

- Reviewer：`01a0f3d2-ea67-7772-816f-b14b3179159d`（dev-reviewer / Copernicus），未参与实现；其实际模型未单独取证，不猜测。
- 记录日期：2026-10-01；以下为 Reviewer 原结论，主开发只落盘，不把部分 PASS 改为整体完成。
- `CHANGE_REVIEW: FAIL / MISSING_REQUIRED_RUNTIME_EVIDENCE`（predecision 原始完整正反包缺失）。
- `CANDIDATE_PROMOTION: NOT_PROMOTABLE`。
- Task6.6 复核工作已交付，不表示 Task6.5 完成，也不代表最终人工完成批准。
- Reviewer 无损清单已按其口径从实际源码重建并核对两项 hash，保存为 [完整快照清单](independent-review-source-snapshot.json)，避免复核记录只依赖临时目录；未修改原基准或旧运行锁。这是取证副本，不是新产品版本锁。

+本轮 Task6.6 只读复核结束：已检查接缝未发现新的实际源码阻断；normal 与独立真实 Eval 的底层记录支持各自 PASS。**Change 尚未完成**：Task6.5 的 predecision 原完整正反包仍缺失，Task6.7 尚无最终人工完成批准。候选保持 `NOT_PROMOTABLE`，原八维 Change 保持暂停。

本轮未写文件、未运行测试/模型/Gate，未归档或执行 Git 发布操作。以下记录供主开发落盘。

## H01–H19 逐项结论

“PASS”限定于下列实际已复核接缝，不表示每个分支都经过本轮真实模型运行。

规格简称：

- R：[research-handoff-contracts](specs/research-handoff-contracts/spec.md)
- M：[multi-dimensional-holding-research](specs/multi-dimensional-holding-research/spec.md)
- D：[codex-development-environment](specs/codex-development-environment/spec.md)

| 项 | 判定及实际核对 | 证明边界／规格 |
|---|---|---|
| H01 | PASS：检查 invocation/Hook 技术身份装配及冒用身份负例；normal 原语义稿不需抄技术元数据。 | 非所有角色真实运行；R7–16 |
| H02 | PASS：引用绑定任务、类型、Gate 和允许集；未知或跨类型引用拒绝，不猜测修复。 | 源码及确定性正负接缝；R18–27 |
| H03 | PASS：外部 Claim 限定报告 ID/hash；重名及旧裸 ID 歧义保留或拒绝。 | 已读 scoped Claim 实现与对应测试；R18–27 |
| H04 | PASS：文档选择绑定冻结完整对象，计算选择绑定成功结果；不重写正文或原值。 | 未逐篇重新开展外置文档研究；R19、30 |
| H05 | PASS：结构先于血缘；成功收据重验真实事件、输入顺序和结果，重签 ledger 不能覆盖事件。 | 已检查计算装配及负例；R29–45 |
| H06 | PASS：材料审计重建真实 search/fetch、缓存及失败记录；重复调用不按唯一文件数折算。 | 不把工具存在当研究充分；R92–97 |
| H07 | PASS：短回执精确解析原稿版本；凭据先验、错凭据不占额度；bearer 不冒充真实身份。 | 已检查 submit/resolve/修订绑定；R63–79 |
| H08 | PASS（已检查接口）：各阶段保留独立业务 Schema，共享机械装配，不递归删除研究内容。 | 未逐分支进行真实模型补验；R7–16、82–90 |
| H09 | **部分 PASS／缺证**：normal 双报告实际读取、选择、装配及 Risk/Trace 消费闭合；predecision 源码与确定性接缝已检查，但原真实正反包不存在。 | predecision 保持 `NOT_RUN / SOURCE_PACKAGE_MISSING`；R92–101、Task6.5 |
| H10 | PASS：真实 Terra parent/child 身份、读取、首稿和封装评分均核对；五维分数、理由、引用未变。 | 普通股 Eval 仅静态/确定性证据；不宣称真实运行；R103–105 |
| H11 | PASS：检查首稿加一次修订、基础稿及允许路径绑定、完整复验与第二次失败停止；CIO 1.0.1 时序分离合理。 | 最新 normal/Eval 均首稿成功，未实际触发局部修订；R70–79 |
| H12 | PASS：检查版本权威、派生镜像及漂移拒绝，不取最大版本或改历史锁。 | 声明一致与实际加载分列；D36–45 |
| H13 | PASS：检查文件字节、规范对象、自身字段排除、事实/视图口径与历史算法兼容。 | 未全仓重新验证所有历史 hash；R107–116 |
| H14 | PASS：检查明确位置的事实投影、独立观察记录及唯一视图回绑；嵌套同名语义字段保留。 | 未改写或迁移历史数据库；R118–131 |
| H15 | PASS：检查标准 Schema 适配、组合及兄弟约束、未知关键字/外部引用拒绝；normal NO_TRADE 两执行字段实际为合法 null。 | 不代替本轮全测试执行；R44–61 |
| H16 | PASS（已有完整包接缝）：冻结依赖读取与新执行准入分离，缺契约、越界及漂移明确拒绝。 | 无法验证已丢失 predecision 包内容，不拿 fixture 替代；R133–142 |
| H17 | PASS：检查共享路由、多对多、UNMAPPED、权限隔离以及获取/交付/查询/引用分列。 | 不把配置清单当真实消费；M36–49 |
| H18 | PASS：检查终态投影与消费者；保存、exit0、来源限制、内容审阅和晋升状态不混用。 | normal 是 fixture 合法闭环，不是完整八维研究验收；M25–34 |
| H19 | PASS（本轮检查范围）：角色/方法/任务分层，开发权限不继承 CIO；历史义务、失败和暂停状态保留。 | 本 Reviewer 结论不等于人工批准；D14–34、47–67 |

## 三处重点修复与真实证据

- **Trace 修复**：[run_package.py:1236](/Users/caihaoming/Documents/stock_agent/product/runtime/run_package.py:1236) 将 `CIO_REPORT_CONSUMPTION_VERIFIED` 放入既有 `events`。实际成功 Trace 无新增 `cio_report_consumption` 顶层字段；未扩 Schema/白名单。89 项接缝记录和关联源码已检查，不将旧失败包改称成功。
- **CIO 时序绑定**：[cio_local_revision.py:58](/Users/caihaoming/Documents/stock_agent/product/runtime/cio_local_revision.py:58) 保持启动 prompt 绑定，将启动时尚无 CIO 输入与研究后冻结输入分开。实际 normal 的 Start 为不可比阶段，Stop 绑定已准备输入；不是解除输入漂移校验。
- **Eval 两处修复**：[eval_execution_proof.py:93](/Users/caihaoming/Documents/stock_agent/product/runtime/eval_execution_proof.py:93) 新增 JSON 实参解码及 shell 精确路径解析；[runtime_eval.py:560](/Users/caihaoming/Documents/stock_agent/product/runtime/runtime_eval.py:560) 使用 `sys.executable` 派生后续 CLI。对应测试覆盖空格/引号、backup 假路径、错文件、部分输出及解释器派生。未执行 JS 来验证证明，也未改历史 prompt。

独立核对结果：

- normal 的 **14 个原文件 hash**、Eval 的 **21 个原文件 hash**全部相符。
- 原始 Eval 子线程确有 manifest/model input 完整 `cat` 输出；仅 `wc` 的记录不作为读取证明。
- 实际 child 最终 JSON 与 `semantic-native-draft.json` 相同；原稿、封装结果与正式 Eval 的五维内容逐字段相同。
- execution proof 重算为<br>
  `5a925f88ee0fef4e0b6a1b2696dab0b23ec2b41b043ba007d375b562fc1b26de`
- 正式 Eval hash 重算为<br>
  `1a57c9ecd2da16ee98b67048b0fabf393bcff24f1866bab3fde09dddf9215104`
- source run 的 285 文件映射 hash 仍为<br>
  `3d98b95ff7e25beb29f889b3d5824b11f5ade847fa84a7f0ef7ead582bde0c81`

内容上，normal Analyst/Skeptic/CIO 没有从单点价格推导估值、从债务推导偿债结论，或把管理层计划当执行成果；工具权限限制与事实缺失分开，低置信度 NO_TRADE 有明确补证条件。因此支持该 fixture 的内容判定，不证明真实股票完整研究或八维达标。

原 Eval wrapper exit7 保留。此次是**同一真实首稿经确定性收集/封装后 PASS**，不是原 coordinator 自动端到端成功，也不是重新评分。

## 完整实际源码快照

本轮重算了 **639 个文件**，不是只计算修复文件。范围沿既有完整快照：`product、tests、scripts、.agents、.codex、docs、reviews`，加 `AGENTS.md、PRODUCT.md、pyproject.toml`；排除 OpenSpec evidence 自引用、外置运行产物及忽略文件。它不是全用户目录审计，也不是候选版本锁。

口径：每文件 SHA-256 原始字节；文件名使用仓库相对路径。清单对象采用 UTF-8、`ensure_ascii=False`、`sort_keys=True`、紧凑 JSON、无尾换行。

- 完整 `files` 映射 hash：<br>
  `85d76c8fbcaaa0040f43288d2ecb558650c1d73ed658f7dce1ebf387f2fe882b`
- 沿原 `purpose/scope/files` 三字段组成的快照对象 hash：<br>
  `285f51bdc2755238620db2e46f9d7986099d9883f357c5197326d8140641588a`

**完整清单的无损表示**：既有 [639 项 source-snapshot.json](/private/tmp/stock-agent-handoff-input-evidence.UiIrPV/source-snapshot.json) 加以下 15 项替换；无新增或删除，其余 624 项实际字节相同。基准清单文件字节 hash 为：

`db19d8017368d0f6dc06eb30def542d218d19c671b1df1d53b8c36f6c6ca8305`

```text
product/runtime/cio_local_revision.py 26ad8d7449013212f44fe1e3dbd64e359a1f3e3debf57dd95b9ea465c014369b
product/runtime/eval_execution_proof.py 967705c76cc840adde85d48221b2a5ef5f43ca2a924a501411895e05eddebb6e
product/runtime/fixture_mcp.py cbe67bb03ab96f09402f8d8db089b75ffd8255321181a8602e3d4bf0a8b76de6
product/runtime/multidimensional_stage.py 3717d39e990d156b98ae52dd5a570cef13e3a3239d45fb03890f9267a4cdd01c
product/runtime/nested_codex.py 97ac45b96b7b4c5ccbea0203cd60ea758e13fdc35b11563a8a882f1bb65ae4f2
product/runtime/research_consumption_audit.py 58e6c27b9bb9b2e9d1a900a0e7e641cd39ea68bf7007b5d9d0cfb7efe16fd908
product/runtime/research_submission.py 8fac7bba10b1048b7c6d97bb5ea4c14a3b09ade88503aef713ab67ae7dbb66bf
product/runtime/run_package.py 83997de427770b9f62d7e026441015755327945b519210d9cb4fcd176f5cdb03
product/runtime/runtime_eval.py 1fc8a6ddd98728e09cd83b02e2d793c6eaf2041ceccbd1582fc8f6eb0818c5f2
tests/test_bounded_research_submission.py 9834b84983fa3c8a69ecc82a1118cb194fb5214591b7969e37a9b0d47f5605ec
tests/test_cio_handoff.py 1a71792e51a9cf829daedaa4b6e71cc2b6b22abdb6e4212f686e4cd2ef070913
tests/test_cio_local_revision.py 42209077e45cb2b420c50f7b5347763b8e3daa24c63539fd10a2b861460f8867
tests/test_eval_handoffs.py c6fcdea8f0bc17bf6948f010aced0dbe999bfb50b8d5b6d408096cde0a259bf2
tests/test_nested_codex_launcher.py f12b6d5cb67c90c338f9ca7fc357419453868769117ee253844519e660b4b349
tests/test_research_materials_stage.py c252f603d43286dcf325e28b7da19fb7216ed1b0ced0d1069f042177f61bba1f
```

normal 原 175 文件保护快照为 `f54e50a528ba12d4c1061e4129ac2defa859abb8795a76a2999bca3890b7a105`；当前对应映射为 `192513d77dbca86b96ae53f53ea9ec15a38b644a2fb613918fd22b076e1c4756`，差异仅上述两个 Eval 产品文件。故按影响面复用 normal，**不声称最新整树已全部真实重跑**。

另已重算 20 组输入证据中的 1,441 条文件 hash，全部相符；这是含副本重复项的核对条数，不是独立测试案例数。

## 剩余阻断与未检查事项

唯一已知无法自行恢复的输入阻断：**predecision 原有效正反研究包及冻结依赖正文缺失**。依据现行 Task6.5、R92–101/R133–142 和 D58–67，继续标缺证；不以 fixture、摘要、新造 Skeptic 或 normal 替代，不新增历史失败批次重跑义务。

本轮没有做全仓逐文件语义审计、逐个确定性用例执行、全部历史依赖正文重审或 Promotion 检查；89/30 项依据既有执行记录及关联实现复核，不冒称 Reviewer 重跑。

Task6.6 的本轮复核记录已交付；Task6.5、Task6.7 仍未完成。Reviewer 接缝 PASS 不替代人工批准，也不授权归档、提交、推送或恢复暂停八维任务。
