# 第12节持续本机工作台独立只读复核

- `source_id`: `development-review:persistent-workspace:20261003`
- `as_of`: `2026-10-03T08:02:34Z`
- `retrieved_at`: `2026-10-03T08:02:34Z`
- 结论：本表绑定源码的独立复核通过，未发现仍需修复的具体阻断。根线程已报告全量441项确定性检查通过；其后的5行插件查询改动没有降低安装门禁，对应privacy/CLI专项76项通过，实际安装、绑定、旧文件不变及服务健康证据已闭合。完全虚构Chrome入口被屏蔽，浏览器交互验收仍未完成。本结论不等同第12节全部验收完成。

复核读取当前五份规划、第12节服务/界面/更新层、Ledger事务、CLI、两Skill及对应虚构测试。复核者未读取 `product/.private`、账户或真实交易材料，未启动测试、产品、模型、网络、服务或浏览器；只追加本复核文档。第二位只读复核者对初版CSV事务/重叠检查交叉核验后结束；修复由根线程及数据层worker实施。

## 实际发现与修复闭合

| 初版具体问题 | 当前修复与证据范围 |
| --- | --- |
| 外层 `BEGIN IMMEDIATE` 被内部连接上下文提前提交；新记录提交后快照失败导致部分成功 | Ledger新增 `atomic_write`；内部批次、快照及行情子快照操作在外层事务存在时不自行提交。CSV接纳、保存批次及全历史快照同处一个写锁；失败回滚。新增虚构测试覆盖冻结失败、既有来源保留、冻结期间外部连接不能写及行情父/子快照一并回滚。 |
| 新来源文件的失败清理在rollback释放锁后，另一写入方可能已接纳该文件 | 本次创建来源的清理通过 `on_failure` 在rollback及释放写锁前执行；本来已存在的来源不删除。新增测试在unlink时尝试外部SQLite写入，要求仍处于锁定状态，并验证随后同来源可成功导入。 |
| 网页仅选择成交时区，但日期窗口仍固定香港；已支持的美港混合正式账单无法选择 `PER_ROW` | 网页分别说明导出日期范围时区和CSV成交时区。前者仅三种固定IANA时区，后者额外允许 `PER_ROW`；严格已知账单识别保留，普通CSV逐行模式拒绝。数据层单时区未另声明范围时沿用来源时区，逐行账单必须另给范围时区。新增混合账单、美东午后边界及普通CSV拒绝测试。 |
| FILE_ROW_ONLY重叠按不同来源显示日比较，旧批次起点未知时区间被跳过；锁内仅检查records，未重检receipt-only变化 | `_csv_admission`按明确窗口中的成交时刻检测，日期精度跨时区保守处理；已有单边日期作为开放区间，未忽略未知开户起点。读预检和写锁内均复核相同hash及重叠；新增跨显示时区、开放起点、receipt-only期间变化及同来源幂等测试。 |
| 短窗口恰好包含全部记录时可能复用窗口期初 | 全历史matching与opening来源均排除 `requested_window`；含全部已保存记录的短窗口不能直接成为全历史matching。新增专门测试覆盖该分支。 |
| `file.text()`再UTF-8编码改变原始CSV字节，跨入口相同文件可能不再幂等 | 上传用ArrayBuffer及固定 `csv_base64`，服务端严格base64解码后保留原bytes；原有编码识别与文件hash职责继续由固定CSV适配器负责。解码后仍限4MiB，总body限6MiB，不传路径、文件名或URL。根线程后台17项请求检查通过，其中BOM/UTF-16/GB18030样例证明原bytes送到adapter；不将该请求替身测试宣称为实际浏览器文件上传。 |
| 蜡烛键盘固定/关闭没有通知主壳；根scrollHeight作iframe高度基线会逐次增长 | 桥接chart与candle-panel的Enter/Space/Escape，复用固定同源消息；主壳高度改测main实际尺寸，仅在结果变化时更新。根线程9项真实生成JS的DOM替身测试通过，覆盖主壳刷新成功/失败、图窗与版本保留及连续20次fit尺寸不增长。实际Chrome键盘联动及切换视觉仍未验。 |
| 实际插件登记查询默认读取远程catalog导致超时 | 相对本节 `installed-before`，仅将当前marketplace名称提前读取并传入官方 `codex plugin list --marketplace <name> --json`。timeout/check、精确pluginId、installed/enabled、version、source、marketplaceSource及真实cache位置校验完整保留，无fallback或手填登记。root实测限定本地查询0.09秒退出0；源码独立复核通过，新版privacy/cli专项执行另记录。 |

## 通过的源码范围

| 范围 | 复核结论 |
| --- | --- |
| 固定入口和生命周期 | 仅绑定 `127.0.0.1`，默认8765；CLI显式启动并持续至停止，端口冲突明确失败。没有自动启动、计时采集或模型编排器；旧短时只读入口保留。 |
| 请求边界 | 精确单Host；资料GET要求同源会话，POST另要求明确同源Origin及CSRF。固定状态/时间线/报告view/summary和三种更新路由；拒绝未知/重复参数、未知选择、任意路径/账户/SQL/URL/Shell/模型。严格JSON对象、重复键及非有限数拒绝；正文/解码上传/日期/时区有界。忙时在读body及调用adapter前409拒绝。无宽松CORS或原始来源下载。 |
| 输出和日志 | 响应no-store、nosniff及同源CSP；cookie随机且HttpOnly/SameSite Strict。异常与请求日志不回显来源正文；更新结果只取固定状态及计数，公有health无账户事实/访问秘密。用户文字沿用安全标签，内部版本/hash留后台定位。 |
| 线程和只读启动 | JournalUpdates只持有路径、账户引用及adapter，每次打开自己线程的Ledger；启动及刷新只读取全量账户current_records与校验快照，不写批次/快照、不抓行情、不启动LLM。新状态全部校验后一次替换，失败保留原可读generation。 |
| 时间线及原报告 | 最新时间线包括同账户全部当前记录，不能被最后较短批次截断。报告由 `load_review` 校验原packet和匹配快照，再形成各自ReviewProjection；版本按业务截止、保存时间及身份排序。新交易/修订计为未纳入该版研究，duplicate_candidate读时提示不算新事实。选择案例仍使用原冻结图，更新行情不换绑旧研究。 |
| 行情更新 | 只接受现有交易的公开证券身份及有界日期，不传账户、成交价或完整交易。股票与多个期权按标的复用，有总请求预算及每标的预算；身份、hash、OHLC、来源、时区及价格口径校验，失败保留旧行情。新有效行情形成子快照，未验证可用时间不升级为当时已知收盘。 |
| CSV持久化 | 起止日期、来源模式与启动账户绑定；同来源hash重复零增量，不稳定ID不同重叠批次写前拒绝；稳定ID保留追加revision，同秒相同数值的不同实际来源行不猜测合并。新成功导入生成全保存范围快照，保留旧行情与历史版本；写前真实隔离校验仍存在。 |
| 界面及Skill | 最新图与原文/全部已有建议分别呈现，显示交易、K线与选中复盘各自截止及未纳入数量；可选择旧版本。刷新保留仍有效的标的/合约/日期/图窗/固定日/分页与记录，失效标的或合约有说明；旧报告中不存在的选择明确提示未纳入。页面给真实Skill方法，没有券商或LLM假桥接。两Skill及新报告CLI装配版本均1.4.0。 |

## 执行证据与完成边界

根线程报告最终 `test_trading_journal_*.py` 441项通过，44.737秒，session `73205`。另确认后台请求17项、真实生成JS的UI 9项通过；后者使用DOM替身，不是浏览器观察。完整聚合后仅 `packaging.py` 的5行查询参数发生变化；该差异已与本节 `.codex-local/local-journal-implementation/installed-before` 比较，门禁保持；新版privacy/CLI专项76项通过，13.279秒，session `5069`。复核者没有另行执行测试。

根线程实际尝试完全虚构Chrome入口 `http://127.0.0.1:59604/`，得到 `ERR_BLOCKED_BY_CLIENT`，AX和截图 `.codex-local/local-journal-implementation/chrome-blocked.jpg` 保留阻断。没有换通道、端口或代理重试，虚构服务已停止、错误标签已关闭。因此12.7保持未勾，主壳刷新/失败/切换的实际浏览器交互验收未完成。复核者没有重新访问浏览器或查看私人材料。

根线程最终证据记录于 `persistent-workspace-evidence.md/json`：实际洁净安装 `0.3.0+trading-journal.a094a81cca11` 达到VERIFIED，source/cache共同hash为 `0f0dee1709bc77d6af5922fc02b8f0a19be78b21ef4809344731284ee0df9cb8`，其他205个基线文件等价；实存账本/报告绑定校验通过、无无效绑定；263个旧私人文件的hash/mtime/mode保持不变且无新增。启动、停止、重启后公有 `/health` 在 `127.0.0.1:8765` 返回RUNNING；根线程未访问真实HTTP资料投影。实际详单仅留忽略的本地审计，本复核不抄录私人交易正文。

真实私人页面的实际视觉仍为UNVERIFIED。根线程已按证据勾选12.2—12.6及12.8，12.7仍未勾，仅剩主壳Chrome交互被屏蔽的验收缺口；6.1/6.3也保持未勾。不得把健康/绑定/确定性测试转述为私人可视验收，不换协议或通道绕过先前访问拒绝。归档、Git提交/推送及候选晋升不属于本结论。

## 复核版本绑定

| 文件 | SHA-256 |
| --- | --- |
| `product/trading_journal/app.py` | `a9d74d50ce487f4d9dc82b950b8a236048e41d0996e60f6acd28fb722fe480a9` |
| `product/trading_journal/app_ui.py` | `345f64b0ce6d4192ed47a609f7bc7fd85725e9916f2c3af4370435cc4fe4e191` |
| `product/trading_journal/updates.py` | `bd5871b829e02dcd01ee5c3f2cffe3645fabe9e714189ad7d844deaee43b5389` |
| `product/trading_journal/ledger.py` | `465332735614ebb9fb45dc4909b3cfd8d9c695e031bee7417c6e888903a1fe99` |
| `product/trading_journal/cli.py` | `403948cbf68eac85762ff976eaf2bbdef49e487f36d59e680eb3a8e2d1077bce` |
| `product/trading_journal/packaging.py`（441项聚合后的5行差异） | `62ecad9e3838336954a3fa6d60e9e7abb5926be3eba98c26fff9b3e550c38e43` |
| `product/skills/tiger-trade-journal/SKILL.md` | `f552ab1d1dd7d6b59788d8bd40e8b67e7ed7114b6f789c4b537f69dd05abb479` |
| `product/skills/tiger-trade-journal/references/usage.md` | `c4c4215a3b37aabe82ec004c3470edf1a5f07081bd19ccef6d88de3fcfdd253f` |
| `product/skills/trading-reflection/SKILL.md` | `ec21610f2fb69be019cf1d2b27e449ddb778118e993bab48f615c11316d35d0e` |
| `tests/test_trading_journal_app.py` | `a0b436d12d5d313c5e5e32961c00d3a2122c6b7c2de060f6c17a78fc2768acf0` |
| `tests/test_trading_journal_updates.py` | `f117db7a0501bc3f34b787b0dc616b18ae3d1de0082ef4b25b80c75586099247` |
| `tests/test_trading_journal_app_ui.py` | `cfefdd4ec778bfa9116c5e992c8b8f7ed599334d1a043237e21f783b50f46a5b` |
| `tests/test_trading_journal_privacy.py` | `cf556c5c0a51a6f487c1d226edd202e45389498d6665d021eaaa52a7c5bc06df` |
| `tests/test_trading_journal_cli.py` | `19fc25ac68d131f98d65fcab4e9aec26bae6c9bd056447b229ac6043bb5081d5` |
| `proposal.md` | `60adc920e0e5abb12b43dcc7e622b6e0326bd45fabb361b147178492dd8c7f0d` |
| `design.md` | `07a45efcb3d5a09968e3c7925089d06f279e5a12c3ef7a3cb812a4ead83e7ebc` |
| `tasks.md`（复核时状态） | `1f7647ac9ce34e2808e5f339e9410401b250221b3b8ec58c570f3b023f6c0641` |
| `specs/tiger-desktop-trade-journal/spec.md` | `6e5572f4ac9cb68b0b4569cd2def3e9c31a31c612b84638fa90d2492315e4dc1` |
| `specs/historical-trading-reflection/spec.md` | `d045ef9b1c3cd25ef9eeb258e0d91f87b179a1df1200bb077e6a496fef4067d8` |

`tasks.md`的hash只表示首次绑定时的任务状态；根线程随后按有效证据更新勾选不代表产品源码变化，也不能借此勾选仍缺浏览器证明的12.7。安装/健康及专项补跑结果独立记于上文执行证据。
