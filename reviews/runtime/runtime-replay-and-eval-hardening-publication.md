# runtime-replay-and-eval-hardening 安全发布记录

日期：2026-09-09。依据当前用户对“保留本地原始证据，排除私密会话状态后完成原已批准 commit/push”的明确授权。

## 批准与发布边界

- 人工批准：`reviews/runtime/runtime-replay-and-eval-hardening-approval.md`。
- 独立复核：`reviews/runtime/runtime-replay-and-eval-hardening-independent-evidence-review.md`，SHA-256 `0a94f3d921d4f8657ab4013fac4070123cff369bcb32119afa782646eb4f84ad`。
- 归档：`openspec/changes/archive/2026-09-09-runtime-replay-and-eval-hardening/`，三个主规格已同步。
- CHANGE_REVIEW: PASS；CANDIDATE_PROMOTION: NOT_PROMOTABLE。本次提交不是 Promotion PASS，不更新生产版本指针。
- 本轮不重跑测试、产品 LLM、Regression、Replay 或 Release Gate，只核对发布文件、既有 hash、规格同步和隐私边界。
- 新 `streamline-codex-development-environment` 规划文件不属于本次提交。

## 源码及验收标识

本轮只读重算与已批准记录一致：

- 82 个受保护产品文件的源码快照：`24fe59edbc75db2c5d667df7e58b069f63e136aad59a0ff22782cb27e0fa74fb`。
- Candidate lock：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`。
- Launcher：`8aec4e641a0cfdee0040e33e2481cda79d99eb48f7cf70f1d4b53a2449ee74c2`。
- Hook：`e276180b0bfd3d9d21e48f0b6e2ff7bcf2ecd2df3f33cbe7d58b3843cf43bf31`。
- Launcher 测试文件：`83d48343431c9ef47926a89f253f54da380c3f06a2d81c7b4cdd254995a85997`。
- 最终 suite：`rrh-final-lock-regression-suite-20260909`，hash `179b70a83526db786357354a5bdcddcae55c06cabe05e513e81b8db3e55c7b39`。
- suite 文件：`evals/results/runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock/regression/suite-final/result.json`。

## 私密排除与可审计性限制

新增 Git 忽略规则 `evals/results/**/.codex-runtime/`，排除其中 354 个状态文件（约 1.31 GB），包括 SQLite、日志、临时消息等。所有原始文件保留本地，未删除、脱敏重写或复制到其他位置。已有 Python 缓存忽略规则继续生效。

发布其余 17,163 个证据文件，包括原始 invocation 事件、决策/Trace/Eval、Capsule 对象、历史失败与成功报告；不修改其原始内容或 PASS/FAIL。当前 final-lock 中 Capsule 引用的 1,536 个对象均在可发布集合内。源码模式扫描未发现其余候选证据中的私钥、常见 API/GitHub/AWS Token、JWT 或非空凭据赋值；JSONL 检查未发现原始用户角色/session_meta 记录。模式扫描不是不存在任何敏感信息的数学证明。

**远端不是本地运行目录的逐字节完整副本。** 既有 Runtime Eval/Regression 的整目录 hash 可能覆盖 `.codex-runtime`；仅凭 Git clone 不能重算这些包含私密状态的历史 run_tree hash，也不能将其视为可直接执行完整晋升验证的包。历史绝对路径及源码树清单继续保留原值，可能指向仅本地保留的状态和缓存。需要这些整树校验时只能在原始授权环境核验，不补造私密文件、不改写已批准 hash、不将“不随 Git 发布”写成“证据从未存在”。此限制不改变已基于本地完整证据完成的独立复核及人工批准。

## 可发布证据集标识

以下不是历史 run_tree hash，而是此次可发布集合的独立标识。算法：对目录内 Git 可发布文件建立 `{相对路径: 文件字节 SHA-256}`，按键排序，以 UTF-8、`ensure_ascii=false`、紧凑分隔符编码为 JSON，再做 SHA-256。目录前缀均为 `evals/results/`。

| 目录 | 文件数 | 可发布集合 SHA-256 |
|---|---:|---|
| runtime-replay-and-eval-hardening-acceptance-20260907 | 4260 | `5d662eaf71e1aac1cb26b5a410a24027083985c61c922cb297d80a5b560030ca` |
| runtime-replay-and-eval-hardening-final-20260908 | 2235 | `d7406a83ac924a8b00c9895cccaa9f00b3c2b81b9a7c4c9bae8127b81e98bae7` |
| runtime-replay-and-eval-hardening-final-independent-20260908 | 277 | `42279f3aae80caad44ab7204d307246a582a8511b0a6a4036fe510a5eddd98e2` |
| runtime-replay-and-eval-hardening-final-independent-v2-20260908 | 1061 | `9de089a17677bd3962d5d2b34aafabfcdd3dfe4a04f88e7562052ae58d7cc723` |
| runtime-replay-and-eval-hardening-focused-closure-20260908 | 697 | `0b325905ee0e94b45190750ccf5a8487d1d06e7c81a00d1dcec5f7b02304d8e6` |
| runtime-replay-and-eval-hardening-hardening-fix-20260907 | 2830 | `e0f75948ca562f3f844629f7627a6c856a38ae2fdb1bde133d70147f809d8e81` |
| runtime-replay-and-eval-hardening-nested-diagnosis-20260908 | 3279 | `602616649e75dc4ead71995605a36499e8d6787bfac43fc48482872a35634f59` |
| runtime-replay-and-eval-hardening-nested-diagnosis-20260909 | 2524 | `bd50fc0781873fa12f64144f6e0cdb7ed896f9fa546ac3dd3faf73f096281d67` |

## 发布检查方式

- `git status --short`、`git diff --check`、暂存差异及文件清单检查。
- `openspec validate --specs`：8 个主规格通过；此命令仅校验规格，不运行产品或测试。
- `git check-ignore` 确认原私密数据库被排除；提交前再检查暂存树不含 `.codex-runtime`、凭据或新 Change 文件。
- 提交候选的源码扫描命中 `tests/test_replay_capsule.py:109`；人工读取上下文确认是按字母表顺序构造、用于测试敏感数据拒绝的合成字符串，不是真实凭据。仅对该文件的这一精确测试值分类为误报，不放宽其他扫描。
- commit/push 的实际结果以本次 Git 提交对象、远端分支及任务最终答复为准；本文件不预写“推送成功”。

## 原始证据空白格式的人工处理决定

暂存检查 `git diff --cached --check` 返回非零：394 处行尾空格、19 处文件末尾空行，全部位于 `evals/results/` 的原始证据，源码及其他提交文件无此类问题。用户已明确批准将这些原始证据空白格式作为非阻断项，保留原字节和 hash，继续提交推送。这不是把检查结果改记为 PASS，也不豁免源码格式问题、敏感信息或验收失败；本轮不格式化历史证据。
