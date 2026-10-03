# 功能归档与限定发布记录

- `source_id`: `archive-publication:trading-skills:20261003`
- `as_of`: `2026-10-03`
- `retrieved_at`: `2026-10-03`
- Change：`add-independent-tiger-trading-skills`

## 已完成的归档

人工批准见 [functional-acceptance-approval.md](functional-acceptance-approval.md)。实际执行 `openspec validate add-independent-tiger-trading-skills --strict` 通过，然后执行正常 `openspec archive add-independent-tiger-trading-skills --yes`，未使用 `--skip-specs` 或 `--no-validate`。

CLI实际归档为 `2026-10-03-add-independent-tiger-trading-skills`，同步：
- `historical-trading-reflection`：新增16项Requirement；
- `tiger-desktop-trade-journal`：新增15项Requirement。

同步后的两份主规格分别严格验证通过。Proposal的超过10个delta提示和长Requirement提示为非阻断建议，没有借此拆改已批准范围。归档时任务59/61；两个未勾项分别是6.1接受的真实视觉例外、6.3尚待执行的Git发布。归档没有将这些项目自动升级为PASS。

## 证据适用范围

复用原441项确定性检查、最终插件查询变化的privacy/CLI76项、独立复核及已有实际洁净安装证据。本轮只做文档/OpenSpec/差异/hash/发布检查，未重新运行这些测试、产品、模型或网络探针。补充浏览器证据见 [browser-acceptance-evidence.md](browser-acceptance-evidence.md)。真实视觉UNVERIFIED、部分覆盖、金融计算缺口和Promotion NOT_RUN均保留。

## Git副本与本地原件的区别

两份原机器证据含本机绝对路径、插件缓存位置或私人产物locator，不发布原件，不访问它们所指向的私人正文。另一本原始实施验收Markdown含两处显式换行用尾随双空格，也只发布有独立标识的派生副本，不对原件实施格式化或豁免源码问题。三个原件仍留本地归档目录，字节未改写。

| 本地原件（不进入Git） | 原件SHA-256 | 发布的派生副本 |
| --- | --- | --- |
| `implementation-evidence.json` | `26a88cc11f1c008005dea5bf1685393005786dcd172193e1712e28084b8190f6` | [implementation-evidence.publication.json](implementation-evidence.publication.json) |
| `ui-reading-increment-evidence.json` | `67127f0431c549cf5c13f6d64bd31e85fef1b552234387b5e5eecc2057559230` | [ui-reading-increment-evidence.publication.json](ui-reading-increment-evidence.publication.json) |
| `implementation-evidence.md` | `413695ad9a3e03ed46a93c0539f215725e6ee9f0cae9e12f583d823c29060b6a` | [implementation-evidence.publication.md](implementation-evidence.publication.md) |

JSON派生副本分别替换9、12个路径值为 `LOCAL_ONLY_LOCATOR_REDACTED`，并增加 `_publication` 声明、原件hash与字段名单；其他历史字段不改写。Markdown派生副本只将两处双空格换行改成`<br>`，附原件hash和发布边界。它们不是原件，不是新执行结果。历史Markdown指向以上三个原件的链接只在本地完整归档有效；Git读者应使用本表派生副本。其余已审阅的脱敏证据JSON保持原样。

Git副本不能重算本地完整证据目录、私人产物目录或安装来源的原始hash。浏览器原报告、截图、临时账本、harness、启动配置与转录不发布，公开机器索引只保存其hash和限定结论。不能据缺失文件补造执行/安装证明。

## 限定源码与共享文件

限定为两个独立Skill的9个文件、`product/trading_journal/`的22个文件、18个 `test_trading_journal_*.py` 文件、两份主规格和本归档的审阅文件；不提交pycache或私人文件。

共享文件只包含：
- `.gitignore`：`/product/.private/`、`/.codex-local/`及相应注释；不提交另一Change的认证笔记排除段；
- `.agents/plugins/marketplace.json`：洁净本地插件来源路径；
- `product/version-manifest.json`：`tiger-trade-journal=1.4.0`、`trading-reflection=1.4.0`；其余并行版本差异不提交；
- 三个既有测试的六处 `copytree` 增加 `.private` / `__pycache__`排除。

`test_component_versions.py`和Runtime现有复制排除已经在基线，不夹带当前 `common_stock_stage.py` 的单股研究变化。其他Council/Runtime/Schema/Agent/Web/只读券商API/配置/产品方向/活跃Change全部排除并保留工作树。

格式检查还发现 `tests/test_trading_journal_charts.py:616` 的字符串结束引号后有一处词法尾随空格。运行冻结解除后仅去掉该空格，Python AST（不含行列元数据）逐项相同，字符串内容不变；不以原测试的SHA-256冒充新字节hash，不重跑或扩大旧测试结果。原件hash为 `7675a32f6f8370154bd1a0d48c83ee66cd9064a58f391924966fc62586414eb5`，修正后为 `20ddd99772c545f90f810cfffc1b193cf4c858251a023b5f92a716ccb39e675c`。这是明确记录的词法格式修正，不是测试失败豁免。

## Git发布结果

独立备用索引完成85个文件的精确路径、JSON解析、敏感模式、共享hunk与 `git diff --cached --check` 检查，全部通过；准备阶段共享暂存区为空、HEAD与工作树未改变。备用索引只作为发布准备，真实执行结果如下：

- 基线：`68022648f73a179b011ae9db2e6e55ec8e1a7577`。
- 新分支：`archive/independent-tiger-trading-skills`，从该HEAD创建，不切换其他内容基线。
- 限定实现/规格/归档提交：`01c48c4bf63fb3519391d7877d0e2b042bb887d9`，85个文件，实际父提交等于上面基线。
- 实际 `git push -u origin archive/independent-tiger-trading-skills` 成功。
- `git ls-remote --heads origin archive/independent-tiger-trading-skills` 返回该完整提交hash，远端为 `https://github.com/dannyCaiHaoming/stock_agent.git`。
- 本次是新分支发布，不宣称合入main；没有创建PR、自动合并或force push。
- 已提交路径与审阅清单完全一致；31个产品/Skill文件hash仍与归档前相等。三个本地原始证据的hash保持相等，私人文件/本地配置未被Git跟踪。
- 实现提交后共享暂存区为空；分支准备时登记的全部工作树文件hash仍相等，其他Change和用户原有修改保留。工作区仍dirty，包括并行开发、三个本地原证据与本地浏览器配置，不宣称全仓库洁净或全仓库测试PASS。

另一会话已明确通知第五次ALB运行结束、释放运行冻结窗口；其内容验收和发布批准仍与本Change无关。本会话据自己的既有用户批准继续限定发布，已告知共享文件的index范围和单处测试空白修正；未编辑该会话Change/相关主规格、产品源码或共享运行配置，没有全目录暂存。

第一次装配共享index时发现前一天的零字节 `index.lock`，未发生部分暂存。确认文件属当前用户、inode/大小/mtime稳定、无Git写进程后，仅删除该遗留空锁并成功装配精确索引；没有终止进程、提权或删除仓库/用户材料。

依据实际实现推送及远端核验完成6.3；最终60/61，6.1仍为已接受的真实视觉UNVERIFIED例外。此记录及最终任务状态随后以仅文档的限定提交保存；该文档提交的实际hash及推送结果由最终交付另行报告，避免在文件中提前伪造自身提交身份。
