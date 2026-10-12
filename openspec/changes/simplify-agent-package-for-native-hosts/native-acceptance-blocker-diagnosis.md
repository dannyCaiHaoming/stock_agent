# 原生验收阻断定位：Fed 原件已找到，准备接缝与 Claude 工具池仍未通过

- `source_id`: `native-acceptance-blocker-diagnosis:20261008T074838Z`
- `as_of`: `2026-10-08T07:48:38.893483+00:00`
- `retrieved_at`: `2026-10-08T07:48:38.893483+00:00`
- 结构化证据：[native-acceptance-blocker-diagnosis.json](native-acceptance-blocker-diagnosis.json)。
- 状态：**24/31，未完成**。本次推进 6.1/6.3 的前置定位与 7.2 的证据映射，不勾选原七项。

## 1. 本次新增的实物证据

**Fed 官方原 HTML 没有丢失。** 按冻结事实中的精确 hash，在稳定公共 Research Memory 的 `raw-cache` 找到政策 HTML 和对应 RSS。未扫描或读取私人会话数据库、账户、Handoff、研究判断或未知秘密。

| 对象 | 实际检查 |
| --- | --- |
| 官方政策原 HTML | 84,741 字节；SHA-256 `2011e2321ac11bdcdf3c18acc2bc31ed1896a4d57080522f9b0cb056f3e94a08` 与冻结事实及缓存记录一致 |
| 政策缓存记录 | `8614da9f9ff90cbdbeeed5bdbc422df0f54750dcf953d20c6675f6041f5165c1`；既有 provenance hash、key hash、正文 hash 均通过 |
| 对应 RSS | 9,645 字节；SHA-256 `6ef9f8ee2019c031b583ee3a64eec38170840e2ff4229ec92e43f49702857855` 与政策事实 metadata 一致 |
| RSS 缓存记录 | `f34853fd4c944ddd1aed3f342c146548c7a3a8a15f23ad09591849e760acefad`；记录/key/正文 hash 均通过 |
| 时点 | 政策 `as_of=2026-09-16T18:00:00Z`、`retrieved_at=2026-09-28T12:14:44.199212Z`；RSS 首次缓存获取为 `2026-09-28T12:10:22.906385Z`，均早于原宏观 cutoff |
| 原宏观快照 | 文件 SHA-256 `8de2fee84763756394b873a412825c94a9cbc73a0d67c44f5d2f3396142b97b3`；envelope hash 通过 |
| 原事实复现 | 既有 `_visible_text` 从原 HTML 得到 2,511 字符，与冻结事实 `value` 逐字相等；未触及生产者 12,000 字符上限 |
| 原件保护 | 上述五个文件前后 SHA-256 相同；只代表文件观察，不是 OS 强制只读证明 |

先前在所选公开运行的 `data-v2/research-memory` 下两个精确 hash 路径未找到；随后在稳定公共缓存找到。局部路径缺文件不能被概括为原材料不存在。本次没有重新获取 Fed 网页、补采来源或产生作者查询收据。

原官方网页为 `https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm`；该 URL 只用于说明已冻结来源，没有发起新的研究来源访问。

## 2. 当前真正缺少的是生产者到消费者的接缝

| 边界 | 当前真实行为 | 验收影响 |
| --- | --- | --- |
| [既有官方采集器](../../../product/mcp/live/macro.py:410) | 原 HTML/RSS 进入追加缓存，归一为合法 Evidence | 可以验证原件与历史获取，不自动形成当前原生准备报告 |
| [原生资料客户端](../../../product/tools/materials.py:31) | 生产入口仍只创建 OpenAlexResearchClient；可注入 client 是测试接缝 | 尚无已实现的冻结官方原文发现/读取生产入口 |
| [OpenAlex 正文获取](../../../product/mcp/live/public_research.py:215) | 缺 api_key 在内容获取前拒绝 | 用户没有配置；不能靠授权或改变提示词消除 |
| [准备选择校验](../../../product/tools/materials.py:107) | 本任务实际 search、成功 fetch 文档及作者选择必须绑定 | 不接受开发线程手写准备结论或伪造尝试 |
| [文档依赖消费者](../../../product/tools/documents.py:53)及[连接准备](../../../product/tools/research_connection.py:155) | 相应 BLOCKED_CONFIGURATION 依赖拒绝，原生正文需合法字段/sections/时点 | 不能省略 material_inputs、重命名旧稿或改标 SOURCE_LIMITED 绕过 |

因此，**“找到了原件”只关闭原材料可读取性这一未知，不关闭正文消费、实际作者准备或完整 Smoke。** 官方政策文本也不自动等于独立研报，不能据此替模型选择材料或宣称全部研究覆盖满足。

可行的后续最小方向是：只针对既有、hash/PIT 已验证的官方冻结缓存，补当前原生文档目录、只读读取和准备选择血缘，沿用现有提交与消费者边界。它不需要换 Provider、造凭据或补采网络，但仍涉及当前 OpenAlex-only 准备准入行为及 Design D5 的来源层边界。**这只是待决定的修补方向，不是已批准的新增实现任务；须先明确最小范围、更新 OpenSpec 并显式 apply，不能用临时转换脚本静默代替。** 原 OpenAlex 失败和旧准备记录保持。

## 3. Claude：已排除调用误参复发，尚未确定工具注册根因

已知[失败原记录](claude-companymcp-native-result.json)表明，实际 `company-native` 调用只含 `skill/args`，在 Company 作者创建前，全部 11 个精确工具名均被列为 `unrecognized`，然后 `zero tools` 拒绝。没有 Company 报告、计算或提交。

指定官方导出的该次实际 CLI 为 **2.1.289**；最后一份有 tools 字段的 `prompt_snapshot` 在前一天，不能证明失败当时的父/子工具池。独立终端安装 **2.1.291** 的只读实现检查只能解释错误分类，不能反推 2.1.289 的实际配置/连接状态。未修改或执行宿主内部实现。

仍需在实际原生产品项目取得版本匹配的 `company` 连接状态、精确工具池与加载来源，区分注册层失败和作者业务层失败。现有 stdio 返回全部工具名，以及 `mcpServers: company` 配置存在，均不能替代该观察。不猜测某个安全 flag、缓存、桥接或厂商缺陷已被确认为根因，不扩大白名单或改全局安全/认证，不用同一声明盲派。

## 4. 原七项的实际依赖

| 任务 | 本次推进 | 仍不能勾选的原因 |
| --- | --- | --- |
| 6.1 | 原始官方材料已定位并验证；安装候选与有效确定性证据继续复用 | 合法原生资料准备、当前宿主权限及有效有界完整运行计划未齐 |
| 6.2 | 没有新增 Codex 产品执行 | 完整原生研究、首轮隔离及主线程综合证据仍缺 |
| 6.3 | 已知失败版本、阶段和工具池证据限制分清 | 当前原生工具注册及作者执行未通过 |
| 6.4 | 已有分页/SEC 修复候选不重建 | 没有新原生作者计算、报告与完整场景；旧窗口继续停止 |
| 7.1 | 无新的三份原报告可核对 | 内容裁定不能由合成报告或此诊断替代 |
| 7.2 | 补本次原件→准入→消费者→宿主→内容缺口映射 | 仍缺实际三宿主、内容和一次最终人工完成批准 |
| 8.1 | 没有归档或发布 | 完成前置不满足，不提前同步主规格、暂存、提交或推送 |

本次没有产品源码/测试行为修改，因此复用源码 hash 一致的[最终 174 项检查](query-pagination-native-fix-check.json)，不为诊断文档重跑全批。未启动产品模型、新候选/任务/profile/窗口、研究来源或账户调用；未运行专项 Eval、Replay、Regression、Calibration、Ablation、Promotion。原窗口、原计数、原失败和生产指针保持；原始导出、正文、prompt 与能力秘密不公开。
