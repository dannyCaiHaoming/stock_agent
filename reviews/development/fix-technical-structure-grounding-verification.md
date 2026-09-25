# fix-technical-structure-grounding 验收记录

## 冻结样本与首个差异

- 缺基准样本：`/private/tmp/simplify-macro-market-terminal-20260925-v2/run`，Gate 文件 SHA-256 `42f2595626e3f80c71f579fa90a3e24db8292b0e60f4bc18e1266454d9a86a72`。Technical packet SHA-256 `39c285418621386e2126218592d23e4cf45e5170488bcb6b05f4522b6e57ac13`：MRVL 日线 250 行、SPY 0 行、calculation/chart 均为空。原草稿 SHA-256 `29a5cc33bd6a0a21d459a3ac9ca3712df51eef3bf51826793b8f2b9560a1afab`：状态虽为 `INSUFFICIENT_EVIDENCE`，仍有四条无计算引用的 Claim，因此被 `DIMENSION_REPORT_CLAIM_UNGROUNDED` 拒绝。缺失发生在冻结 Gate，不能归因于 Macro/Market Agent 的上下文消减；本 Change 不补采或跨 run 合并 SPY。
- 基准完整对照：`/private/tmp/activate-independent-skeptic-mrvl-20260924-v9/run`，Gate 文件 SHA-256 `7c6c4ea58bf7ce78b17d5f1951583016ae886d7090039ad7c4f79c258092556c`。Technical packet SHA-256 `f16b1c7763e42f8762b6f00f43972dc093732ed95fa4dd5e1f4b0f339d711be8`：MRVL/SPY 各 250 行，calculation/chart 均存在。报告 SHA-256 `81f202e7153f57f8257ba56a4e304d5b89045e704aaedb1009fe583d70a971e9`：`COMPLETE`、12 项计算、四条有 `calculation_refs` 的 Claim。此报告只作为另一冻结身份的对照，不移入缺基准运行。

## 本次实现与确定性验证

- 无 calculation 的 Technical packet 将 `claims.maxItems=0`、`status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、`data_gaps.minItems=1` 锁入输出约束；保存前再次验证报告状态、零 Claim/计算/附件和非空缺口。
- calculation 有效时保留原引用门禁；chart 缺失仅记图表 gap，已知的历史不足与输入数值无效分别说明，未知渲染、文件或权限错误继续失败。
- 命令：`python3 -m unittest tests.test_multidimensional_stage tests.test_multidimensional_research_contracts tests.test_governance`。结果：72 项通过。测试覆盖 MRVL 有日线/SPY 缺失、MRVL+SPY 完整、计算成功/图表失败及未知错误；合成 Hook `SAVED` 与研究包 `coverage.status=INSUFFICIENT_EVIDENCE` 分开验证。
- `openspec validate fix-technical-structure-grounding --strict` 与相关实现文件 `git diff --check` 通过。上述确定性检查不等于真实模型验收。

## 真实宿主验证状态

- 首次尝试目录：`/private/tmp/fix-technical-structure-host.IeVZnF/run`。prepare 成功，新的 Technical packet 将缺基准状态约束写入输出 schema；packet SHA-256 `9da0eda83a09e7c03d20e3c6e7fd5f0d3454d48ed47b69bc3841780ff4fa0a9c`。
- 该次 launcher 在派发前失败：`MULTIDIMENSIONAL_CODEX_PROCESS_FAILED`，八项任务均为 `NOT_DISPATCHED`，`process_exit_code=1`、`timed_out=false`、源码完整性不变。`process-result.json` SHA-256 `525796d67b4bb63ae3b5ac20f67bb98b32f5974e917e197386108201a10fec5e`；`codex-stderr.log` SHA-256 `2d8b902fb51c4fb0108c58a40b037f3ed52641f00cdae67901d7cbda9b4b8473`，根因是受限开发终端初始化 Codex 客户端时 `Operation not permitted`。这是环境失败，不是产品验收。
- 用户在 macOS 宿主 Terminal 重跑同一缺基准冻结输入，新运行目录为 `/private/tmp/fix-technical-structure-verify.vygd7G/run`。launcher `stage_status=PASSED`、`process_exit_code=0`、`source_integrity_unchanged=true`；Technical Hook 首轮 `SAVED`、`repair_state=NOT_REQUIRED`。`process-result.json` SHA-256 `1e97c64ca361fabcf39d8b4b1fe7d41684c63177ffadf34a42c19f663704f20b`，`subagent-events.jsonl` SHA-256 `ec051cf20c680658f6ccdf7cbf259bf5fb0dda69a5d0aca9ae7ccc47cc0d44ae`。
- 新 Technical packet 仍为 MRVL 日线 250 行、SPY 0 行、calculation/chart 均为空，SHA-256 `9da0eda83a09e7c03d20e3c6e7fd5f0d3454d48ed47b69bc3841780ff4fa0a9c`。真实模型报告 SHA-256 `cd301bb19a5b4d666da62cc237ed1f641423386cf7de5038cadf2682cc064af0`：`status=INSUFFICIENT_EVIDENCE`、`sufficiency=INSUFFICIENT`、`claims=[]`、零计算和零附件；明确指出缺冻结的 `US:SPY` 调整后收盘日线，以及这使趋势、相对表现、波动和推翻信号无法得到可引用计算。研究包 JSON SHA-256 `da68cec5dc860365f6d07ae46371508b6dbc32bcab81e559d744bb8befb5d4ea`，Technical `coverage.status=INSUFFICIENT_EVIDENCE`；Markdown 第 16、30 行也如此，未误标为 `COMPLETE`。当前网页并无 Technical 展示卡片，因此这里只验证下游研究包无误标，不声称网页已呈现该 gap。
- `PASSED` 表示研究阶段完成收集，不代表八个维度都成功或 Technical 研究充分：本次 `7/8 SAVED`，失败项是独立的 `RESEARCH_REPORT`，错误为 `DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING`；研究包对此保留 `FAILED`。`COMPANY_RESEARCH` 亦未在本次报告中生成。两者均不属于本 Change 的 Technical 修复范围，不能据此宣称整个多维研究完整。

## 独立复核

`CHANGE_REVIEW: PASS`（仅针对 `fix-technical-structure-grounding`）。独立只读复核核对了真实宿主 Technical Start/Stop、`SAVED`/`NOT_REQUIRED`、冻结 packet、报告、研究包及文件/内嵌哈希：缺 SPY 场景没有无依据 Claim，报告与 coverage 均保留 `INSUFFICIENT_EVIDENCE`。完整 SPY 基准样本和 chart-only/未知错误聚焦测试继续有效，未发现 Gate、Risk、交易、其他 Agent 或跨 run 拼接边界退化。复核还确认 `RESEARCH_REPORT` 的独立失败在 process-result 与 bundle 中显式保留；当前网页没有 Technical 卡片，不能声称网页已展示该 gap。最终 72 项聚焦测试、OpenSpec 严格校验与差异检查均通过。剩余限制是该宿主运行仅 `7/8 SAVED`，不代表全维度研究完整；本 Change 等待用户明确完成批准后才可同步归档，不启动无关 CIO/Eval/Regression。
