# simplify-llm-runtime-boundaries 验收记录

本记录只保存最小化运行身份、测量、校验及复核结论。冻结报告正文和私人来源包留在仓库外，不写入本文件。

## 基线与影响范围

- 旧真实研究级 CIO 运行：`predecision-cio-298ab3e4-d4cc-4b42-b35e-35ea651ae7fb`，模型 `gpt-5.6-terra`；冻结来源 `host-common-stock-e23531ee-571d-44ee-b974-e5a426b36171`，package hash `104597b5956aef80ab9609dbf5a074e63df2f0a2a2f617ed49be085045360a26`，报告 10 份。原始产物在 `/private/tmp/activate-cio-mrvl-host-VjA0aX/run`。
- 旧 `prompt.txt` 为 113,985 字节，SHA-256 `e5743a0d08f4ca990e13e4726044a050674894f7fad6616818832d055e0d7b1e`。旧三份全文指令源文件按当前工作树计共 22,801 字节；该合计不是报告部分，也不等于模型实际 token。旧事件显示该回合总输入 164,596 tokens，其中 cached input 99,840，输出 6,904；总输入包含运行中工具往返等上下文，只作观察值。
- 本次修改预计涉及 `product/AGENTS.md`、Portfolio Council Skill、CIO Agent TOML、CIO 阶段装配、`product/version-manifest.json`、对应测试及本记录。`product/AGENTS.md` 原有 Tiger 未提交片段须保留；不触及 Company、Market、Skeptic 的运行实现。
- 修改前进程检查：本受限环境的 `ps`/`pgrep` 不可用；`lsof` 的 `cwd` 列表仅见桌面 Codex 进程在仓库或根目录，未见运行目录中的 Codex；`lsof -c python3 -c bash` 未返回宿主运行进程。未强行终止任何进程。这是当前观察，不是全系统进程不存在的证明。
- 版本切换与必要回退按上述指令源文件、CIO 阶段装配和 `product/version-manifest.json` 成套处理；保留 `product/AGENTS.md` 中既有 Tiger 片段及其他工作区修改，旧运行文件不回写。

## 阶段规则映射

| 规则 | 新有效位置与处理 | 确定性保护 |
| --- | --- | --- |
| 只读、无交易/账户写入、运行中不改产品文件 | 产品指令阶段段落；来源 Skill 和 CIO 协议保留原规则 | 命令沙箱、Hook、进程/源码完整性检查及非动作输出 Schema |
| 冻结报告和工具返回是资料，不是执行指令；不编造或静默选冲突 | 产品指令阶段段落；CIO 综合须自行区分事实与推断 | Gate、来源/引用闭包；语义仍需独立复核 |
| 原截止点、当前账户未知、禁止动作、`Risk=NOT_RUN` | 产品指令、Skill 与 CIO 协议的阶段段落；动态 prompt 仅保留输出字段值 | 请求级别模型前检查、输出 Schema、finalizer |
| 完整正反报告、Skeptic challenge 取舍和观察条件 | Skill 阶段段落及动态研究问题；十份报告原文不裁剪 | 来源 package/hash、报告目录和消费身份校验 |
| 现金/债务双侧事实、MD&A 冲突、MRVL 相对市场传导 | 动态 prompt 原有针对性修复保留 | 引用查询门禁只拦错误；语义由独立内容复核 |
| Evidence 查询身份与允许集合、JSON 输出 | 动态 prompt 保留单处具体操作说明 | 动态 Schema、Gate-scoped MCP、查询事件和 finalizer 拒绝非法引用 |
| 旧 fixture Council、Eval 和未发布建议流程 | 保留在各原文件供对应入口使用；研究级 CIO 只提取显式阶段段落 | 产品资源发现与旧入口聚焦检查 |

Company 的 `common_stock_stage.py` 派发文本与 Agent TOML 都有 canonical `evidence_id`、计算引用和财务期间说明；Market 的 `multidimensional_stage.py` 派发文本和 Market Catalyst 协议有结构及引用限制；Skeptic 的主阶段 prompt 主要控制隔离派发，重复程度较低。三者本次只读审计，不修改；后续若精简需各自独立的实际运行质量证据，不能沿用旧上游报告代替。

## 新版本验证

- 指令源文件用少量显式成对标记提取；段落损坏由准备阶段拒绝。有效指令及来源文件仍由现有 prompt、环境清单和终态校验绑定；`stage_instructions_hash` 对有效段落内容单独复核。产品版本清单的 Skill/CIO hash 已成套更新，`discover_product_resources` 成功；Skill 版本 `3.7.1`、CIO 版本 `3.1.2`，仅表示资源内容变化，不表示候选晋升。
- 相同来源包的零模型准备目录为 `/private/tmp/simplify-cio-mrvl-DDcsb3/run`，run_id `predecision-cio-simplify-20260925`。来源 run/package hash 与旧基线一致，报告目录 `cmp` 一致，十份报告 hash 逐项一致，原来源目录不改。新构造的完整 prompt 94,267 字节，SHA-256 `d15cdb99168167f0c4f454e0b6dfe388193013f38616cbaf9635a76977d5de90`；有效阶段指令段 3,791 字节，SHA-256 `4dd106ee59b0687e66ef7ca9bedb53c6bc8546ce14e960591e849b1b7c807b71`。完整 prompt 较旧版减少 19,718 字节（约 17.3%），报告正文未压缩。此处是模型调用前的准备记录；实际模型用量见下方真实 Smoke，不把字节降幅当成 token 或研究质量结论。
- 聚焦验证：`tests.test_predecision_cio_stage`、`tests.test_independent_skeptic_stage`、`tests.test_multidimensional_stage`、`tests.test_common_stock_research_contracts` 和 `tests.test_runtime_foundation.ProductDiscoveryTests` 共 183 项通过；另有旧 fixture Agent 配置与 Skill 边界的 26 项聚焦检查通过。`openspec validate simplify-llm-runtime-boundaries --strict` 和 `git diff --check` 通过。新测试覆盖阶段标记缺失/重复/颠倒/空内容、普通标题调整、准备前拒绝及有效指令 hash 篡改；旧 fixture 配置和原研究阶段停止点未见受影响回归。
- 扩大检查中有既存不匹配，未算入 PASS：`tests.test_runtime_foundation` 两项仍期待旧 candidate 版本或与当前工作树的 Luna 路由 hash 不一致；`tests.test_product_config` 一项仍期待 Skill `3.5.0`，而本次变更前 HEAD 已为 `3.7.0`；`tests.test_native_architecture` 一项命中原有 demo 固定文本。上述测试/文件不属本次改动，未为通过检查而修改它们。

- 新宿主真实 Smoke 只有一次尝试：`/private/tmp/simplify-cio-host-smoke-nhK2HB/run`，run_id `predecision-cio-e8936541-3433-4eec-9a4a-742f0f07d182`，显式 `gpt-5.6-terra`。使用原 package hash，报告目录与旧运行逐字一致；请求/实际级别均为 `RESEARCH_SYNTHESIS`。宿主开始 `2026-09-25T05:08:18.796949Z`，报告生成 `2026-09-25T05:10:37.129393Z`。进程退出码 0、未超时、无失败原因、受保护源码前后完整性一致；终态 `COMPLETED_RESEARCH_SYNTHESIS`、`check-predecision-cio=PASSED`，Trace hash `e0202de318afccd96b647bc35d5350b8d134a595fd86ca0b415768ee8d5ebc9e`。
- 新真实 prompt 为 94,324 字节，SHA-256 `3f74dcf1e39c5f60c68d2af5384d5382409c3130957433cea04578aa6c6d886d`；与旧真实运行相比少 19,661 字节（约 17.2%），run_id 长度差使它比零模型准备的输入多 57 字节。模型事件显示总输入 151,639 tokens（cached 90,624）、输出 6,363；比旧回合少 12,957 输入 tokens（约 7.9%），但缓存与输出不同，不能把单次差异解释为稳定成本或质量提升。新报告耗时约 138 秒，旧报告约 146 秒，不能据此推断稳定等待时间收益。
- 事件中一次真实 `fixture_runtime.query` 成功，覆盖 15 个 Gate Evidence ID；最终输出消费 10 份同源报告并引用同一查询集合。一次 `turn.started`、一次 `turn.completed`，无 `turn.failed`、无 MCP 工具失败、无验证失败或模型重试。两条 CLI `item.type=error` 是已知 Hook trust bypass 提示，后续查询和回合均成功，未算作工具或研究失败。报告/Trace SHA-256 分别为 `930ec56d72c9a7ee767c979c3c48dab2dfefed2323abda8f61ab591eae531c97` 与 `a00ce526b6bca72aa1ae9ab71bd0ac27ceca21bafb816cd7b3add61f02452d8c`。无 `decision.json`、`risk.json` 或 advice draft；`Risk=NOT_RUN`、`complete_portfolio_decision=false`。

- 独立只读复核结论：**结构 PASS；研究内容 PASS，未见相对旧 MRVL 基线的重大退化。**复核者未运行测试或模型。报告分别给出历史 cutoff 与低置信判断、分析期限、业务/价格/账户边界；现金与长期债务各有 SEC Evidence 且同在只读查询中。双 MD&A 文本冲突仍为限制，不把数据中心需求直接推动利润写成事实。三项 Skeptic challenge 均为 `PARTIALLY_ACCEPT`，各自说明证据边界、判断影响和重评条件；Macro 保持条件推断，Market 对比 SPY 20/60 日正窗口与 MRVL 的 20 日修复、60 日落后。来源报告目录与旧运行完全相同，无动作/Risk 文件。复核者核对的报告行见新运行 `report.md:8-80`，报告和 Trace hash 与上文一致。新报告相对旧报告少展示一项资本开支金额，两项反证由 `ACCEPT` 变为 `PARTIALLY_ACCEPT`，宏观事件叙述更概括；这些差异不构成已发现的重大退化，也不能由单次运行归因为指令消减。该结论仅覆盖单一 MRVL 研究样本，不代表长期稳定性。
- 最终差异只包含本 Change 的 CIO 阶段装配、产品阶段指令标记、Skill/CIO 版本清单、聚焦测试、OpenSpec 和本记录。`product/AGENTS.md` 中既有 Tiger 只读券商片段及其他 Tiger/Luna 未提交文件均保留；未整仓暂存或改动它们。对本 Change 新增内容检查未见凭据或私人账户号，`git diff --check` 与 OpenSpec strict 通过。两项范围外旧版本测试及一项 demo 架构测试的既有失配已如实记录，不将其改称 PASS。

用户于 2026-09-25 明确批准本 Change 完成、主规格同步且归档。主规格 `portfolio-council-orchestration` 新增三项要求并通过 `openspec validate --specs`（20/20）及 Change strict 校验；归档和 scoped Git 发布仍按开发流程逐步核验。
