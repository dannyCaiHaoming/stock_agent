# MRVL→CIO 输入测量：可访问证据基线（2026-10-02）

## 口径与限制

本记录只使用所选项目文件夹内的归档验收记录和当前实现作只读核对，没有访问历史私人运行原件，也没有启动模型、修改产品代码或重写 ALB 冻结包。以下数值是“已归档记录载明的历史观测”，不是本次从原 JSONL 独立重算的实际账单或当前 ALB 基线。归档记录文件本次 SHA-256 为 `5c2d0229340245cc69701ee44638061eedc918e3f2b8c3c623575b77a7f679f7`；该 hash 只绑定记录本身，不替代历史运行包验证。

## 同一历史运行的可引用观测

`predecision-native-handoff-validation.md` 第 105–137 行记录了一次 2026-10-01 的 MRVL 研究级 CIO / `gpt-6-luna` 运行：七份获准报告被实际读取七次，模型选择其中六份作为论据；一次 Gate 查询取得十项事实，最终六个引用均被查询。记录中的 Prompt 为 176,745 UTF-8 bytes，输出 Schema 为 526,631 bytes，七报告全集的模型表示为 244,990 bytes。这三项是不同交付层的历史字节统计，既不能直接相加当“模型输入 token”，也不能据此确定逐次工具返回的网络序列化字节、每报告贡献或缓存命中位置。输出 Schema 的字节规模约为七报告全集模型表示的 2.15 倍；这是本批候选优化优先级的线索，不证明未来运行仍有同样比例。

该记录还引用当次 `turn.completed.usage`：父线程 input 14,253,226 tokens，其中 cached input 13,881,088 tokens（占 input 约 97.39%，不得再次加总）；非缓存部分按减法为 372,138 tokens；output 7,973 tokens，其中 reasoning output 1,068 tokens（亦非另加）。这不是初始 Prompt 的 token 数、报告读取单独消耗、上游子调用总量或美元费用。原记录说明超过半小时的等待伴随远端 compaction stream 断开及重试，不能把延迟归因于报告过长。此批原始 JSONL 未在所选文件夹内，故上述 usage 为文档转述，未独立复算。

2026-09-25 的另一条 MRVL 研究级 CIO 验收记录报告十份来源报告（九份正向及一份反证），与上述七报告运行不是同一冻包或模型调用；两批不能合并计算比例或当作 A/B。既有八维紧凑投影的参考 tokenizer 统计则属于上游八维任务，完整投影不是 CIO 的旧模型实际输入，不能用来推算此处节省。

## 当前实现的交付机制（只读代码核查）

当前 `build_predecision_cio_prompt` 第 405–453 行先交付已验证目录，但明确要求 `fixture_runtime.read_reports` 读取目录内全部完整报告。`read_cio_reports` 第 109–143 行校验角色权限、精确报告 ID、路径和文件 hash，构造完整 JSON 返回并生成带输出 hash 的事件；`fixture_mcp.read_reports` 第 762–792 行可再将其转换为短引用模型视图。`verify_cio_report_reads` 第 146–183 行要求真实读取事件覆盖全部获准报告（`read_ids == allowed`），并分别记录模型选择。这说明初始目录缩短不等于后续报告未被交付，也说明不能把目录授权算作已读取。代码文件可能正受 ALB 并行开发影响，本次读取时的 hash 分别为 CIO handoff `6451aa9d…`、predecision stage `a1771def…`、fixture MCP `b2039b21…`，不把它们当历史运行锁。

## 项目内可访问的替代样本（2026-10-03 独立只读核查）

在 `evals/results/` 中检查了两类候选。`runtime-replay-and-eval-hardening-acceptance-20260907/runs/source-normal/` 的 `audit/fixture_snapshot.json` 标记 `fixture_id=normal-research-v1`、`scenario_type=normal`；CIO 输入内嵌两份已验证报告（Company 和 Skeptic），`events/mcp/events.jsonl` 只有三条结果事件：两条 `fixture_evidence.query` 和一条 `fixture_math.calculate`。它没有本次所需的 `fixture_runtime.read_reports` 事件或可用的 CIO 父线程 `turn.completed.usage` 原始 JSONL。`ablation-v3/runs/normal-research/cio-only/` 也是同一冻结 fixture，`validated_reports` 为空、仅有一次 Evidence query，更不适于作为报告交接测量样本。这些是旧版合成 Eval，不是 2026-10-01 MRVL 原运行，也不能证明新版 CIO 目录读取协议的交付字节。

为保留一个可从原始文件复算的、有报告又有父线程 usage 的**非等价参照**，另核查 `evals/results/runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock/regression-runs/normal-research/`。其 `audit/fixture_snapshot.json` 亦标记 `normal-research-v1` / `normal`；`inputs/runtime_cio.json` 是 11,262 bytes（SHA-256 `8242fdc339cd096c52d6ef8d8300f22ce02b64b821ced8d58a1338052d094c02`），`prompts/runtime_cio.txt` 是 1,105 bytes。输入内嵌 Company 和 Skeptic 两个报告对象；用 `json.dumps(ensure_ascii=False,separators=(',',':')).encode('utf-8')` 单独重序列化，分别为 4,268 和 3,630 bytes，合计 7,898 bytes。这个合计只是一种本次定义的离线 JSON 表示，既不是输入文件内精确子串的长度，也不是模型实际收到的独立报告工具返回；不得与输入文件相加。调用 manifest 的工具权限仅含 `fixture_evidence.query`；三条 MCP 结果事件为两条 Evidence query 和一条 Math calculate，**没有报告读取事件**。原事件文件 `events/mcp/events.jsonl` 为 1,634 bytes（SHA-256 `2cbc18e30ce57da22369298f81ff7bde988ee0919d989e33ea64d6911d9ed651`），只存 ID、hash 等事件元数据，不存工具完整响应，不能据其文件大小推算模型视图。

此替代运行的原始 `invocation/codex-events.jsonl` 为 75,298 bytes（SHA-256 `be722e2c3c813a38241b689480726c8a70de7a5cc3e275ea42c2f087b7de21b7`），有一条 `turn.completed.usage`：父线程 input 500,424、cached input 454,656（约 90.85%，包含在 input 内）、算术非缓存部分 45,768、output 9,399、reasoning output 1,286（包含在 output 内）。这些是该合成回归运行整体用量，不是两报告的边际消耗，也非计费或 MRVL 用量；原事件还包含 command/file-change 等活动，不应将总量归因于报告。两种样本的 schema/协议、来源、日期、报告数量与 MRVL 不同，不能拼成同源 A/B、据比例外推节省或判断研究质量。替代样本的用途仅是验证测量口径：文件字节、事件证明与父 usage 必须分别报告，缺测要保持缺测。

## 原件访问与下一步

该七报告原运行路径在受保护的 `Library/Application Support` 下，当前环境拒绝挂载；另一条 `/private/tmp` 历史 MRVL 目录已不可访问。项目文件夹内没有对应 `report-catalog.json`、正式报告或 CIO 原始调用事件。项目内已核查的替代合成 Eval 把两份报告内嵌于 CIO 输入，并无 `read_reports` 交付链，不能填补 MRVL 原件缺口。因此 Tasks 1.1/1.2 只能算“归档记录初步盘点＋非等价替代样本核查”，不能标记原件独立测量完成；无法验证每个 MRVL report 的字节/hash、当次实际 MCP 模型视图、父子完整 usage 或计费。不得把这份基线称作实测优化收益。


若要完成原件级审计，需由用户决定是否在所选文件夹提供有权分享的历史运行副本；完整 hash 验证要求原件字节，脱敏会破坏与原 hash 的对应关系。若只提供用户端聚合统计而非原件，报告必须继续注明不可独立核验，且无需提供账户凭据、Tiger 账本或私人文件。获得访问以前，不修改共享 CIO 实现，不启动 A/B 或声称节约 token。

资料来源：`openspec/changes/archive/2026-10-02-simplify-research-handoffs-and-acceptance/predecision-native-handoff-validation.md` 第 105–137 行；`reviews/development/activate-cio-for-predecision-research-acceptance.md` 第 74–82 行；当前 `product/runtime/cio_handoff.py`、`predecision_cio_stage.py` 和 `fixture_mcp.py` 上述行区间。
