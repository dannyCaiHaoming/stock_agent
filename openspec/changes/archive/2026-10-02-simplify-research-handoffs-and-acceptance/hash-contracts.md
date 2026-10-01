# H13：现有交接的 hash 口径与历史兼容

本表解释现有协议，不新建对象仓库、锁管理器或迁移平台。摘要始终由确定性层计算；模型不填写、比较或解释它。旧文件不重写，旧 Schema/协议按原算法读取；协议、投影版本和文件字节版本不是同一个概念。

## 算法与种类

| 种类 | 精确输入 | 当前/历史算法 | 共享入口 |
| --- | --- | --- | --- |
| file-bytes | 文件原始字节，含空白与换行 | `sha256/1.0.0` | `file_hash`、`verify_file_hash` |
| canonical-object | 完整 JSON 对象，包括其中的其他摘要字段 | `canonical-json/1.0.0` | `canonical_hash`、`verify_legacy_object_hash` |
| self-excluding-envelope | 仅排除指定**顶层**自身字段，嵌套同名及其它摘要必须保留 | `canonical-json/1.0.0` | `legacy_envelope_hash`、`verify_legacy_envelope_hash` |
| fact-content | 来源原始对象，或 Memory 契约明确的内容字段投影；两者不互代 | 来源用 `provenance-json/1.0.0`，Memory 投影用 `canonical-json/1.0.0` | 来源 `content_hash` 是共享 `legacy_provenance_hash` 的别名；Memory `fact_content_hash` / `_verify_fact_version` |
| delivered-view | 实际交付的 packet / Gate / Research View；完整对象和自身摘要排除按对应字段定义 | `canonical-json/1.0.0` | 完整 packet 用 `canonical_hash`，View 自身字段用 `legacy_envelope_hash` |

两个旧 JSON 算法在纯 JSON 值上字节相同，但不能因此对非 JSON Python 类型猜算法。二者均使用 UTF-8、`ensure_ascii=False`、键排序、紧凑分隔符；不进行 Unicode NFC 归一化。纯 JSON 算法不接受 Decimal/时间对象；来源旧算法把 Decimal 保留小数表示后写成字符串，将有时区 datetime 转为 UTC，将 date 写为 UTC 零点字符串，无时区 datetime 拒绝。旧算法的非有限数行为只作历史兼容：当前草稿/工具/正式产物仍须先经过拒绝非有限数的 Schema，不能因为可以计算旧摘要就放行数据。

`canonical-json/2.0.0` 是**显式选择**的 type-tagged、域分隔算法：整数/布尔/浮点/Decimal/字符串不混同，时间要求时区、Unicode 码点不变、非有限数拒绝；类型与算法参与摘要。当前正式写入没有批量切换到该算法，不能用它校验旧 digest 后回写。未知算法、未知种类或缺少支持的旧协议失败；不得遍历多种算法找一个能通过的结果。旧裸 digest 无法证明自身类型，类型来自字段所属的契约，不能只按64字符长度比较。

## 生产者与消费者

| 边界 | 生产/消费位置与规则 |
| --- | --- |
| 来源标准化 → MCP/Memory | `product/mcp/provenance.py` 的公开别名共用旧来源序列化；原始内容摘要不是 Gate 投影摘要。Memory 明确读取旧递归投影和新显式投影，验证时分别列出投影版本与序列化版本。 |
| 资料准备 → 冻结资料/八维 | `research_materials_stage.py` 的 task/manifest/index/audit/materialization/View 自身摘要共用 envelope；内容投影仍是原显式字段集合，不能变为整个对象。 |
| Gate → 专业任务/CIO | `evidence_gate.py`、`live_context.py`、研究阶段及 `cio_handoff.py` 使用 Gate 的顶层 `bundle_hash`；引用图绑定的完整 Gate 对象摘要有不同口径，不互代。 |
| 调度 → Start/Stop | `invocation.py`、`codex_hook_recorder.py` 的 manifest/event 使用顶层自身排除；task input、packet 和 prompt 包装对象是完整 canonical-object；资源文件按字节。独立脚本 Hook 仍直接加载同一个 hashing 模块，不新增依赖或模型启动。 |
| 引用图 → 草稿解析 | `multidimensional_references.py` 的 map_hash 自身排除，packet/binding/document 全对象摘要不排除；未知引用协议拒绝，不模糊匹配。 |
| 计算 MCP → 收据/Hook/报告 | `fixture_mcp.py` → `calculation_handoff.py`：receipt/event/artifact 自身摘要排除；工具输入/输出用完整对象。ratio 输入顺序保持，不排序归一化。收据损坏、事件输入/输出摘要错误按具体文件行或 calculation 定位。 |
| 提交 → Stop/下游绑定 | `research_submission.py` 的具体存稿 content_hash 是 envelope；packet_hash 是完整对象。短回执绑定精确不可变版本，完整验证失败不自动换稿或修复。v1–5只读，当前v6写入边界不变。 |
| 普通股/八维 → bundle/中文报告 | 普通股报告使用完整对象摘要；八维正式 report_hash、bundle_hash 自身排除。导出关系中的**完整八维报告**摘要包含其 report_hash，不能用内部自身摘要替代。Markdown 的 `{text: ...}` 对象摘要不是文件字节摘要。 |
| Skeptic → pre-decision package | `independent_skeptic_stage.py` 的 index/manifest/proof/package 自身排除，正式 report 的完整对象摘要和 JSON/Markdown 文件字节摘要分别保留。首轮权限不变。 |
| CIO 冻结输入 → 当前/历史读取 | `predecision_cio_stage.py` 的 request/manifest/invocation/trace 自身摘要；报告目录按原投影，冻结文件按字节验证。只读 artifact 模式不借当前资源或旧绝对路径替代冻结依赖。 |
| 两类 Eval → 结果消费 | `common_stock_eval.py` / `runtime_eval.py` 的 input/output/result/eval/proof 自身摘要使用共享算法；rubric/semantic_input/prompt 是各自原包装的完整对象摘要。结果重算仍检查底层记录和评分，摘要通过不代表语义通过。 |
| Memory/浏览器 → 历史或下游 | plan/view/reference 自身摘要、报告包中的完整对象摘要、原始文件字节分别验证；`research_consumption_audit.py` 与 `web/read_only.py` 用共享 envelope 验证 coverage/事件。未签历史事件仍可读但不变为执行证明。 |

关键错误保留原稳定码前缀，追加 `HASH_MISMATCH:<kind>:<algorithm>:<location>:field/expected/actual`。身份、权限、Evidence/PIT、业务关系或字段绑定不一致仍用原专门错误，不能把它们误称 hash 错误或以重算摘要修复。

## 验证边界

测试使用当前生产者实际输出、实际 Hook/MCP、本地临时冻结包和原消费者，覆盖正常、篡改、跨口径、历史向量、文件空白/键序、自身字段、Unicode、Decimal/时间、非有限数和未知算法。实际命令、完整源码 hash 和结果记录在 `implementation-evidence.md`；各测试集合重叠，不相加作独立样本数。不证明 Codex LLM 已运行、研究内容合格、独立内容评分或 Promotion PASS。
