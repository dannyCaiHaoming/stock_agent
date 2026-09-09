# runtime-replay-and-eval-hardening 人工批准记录

- 批准日期：2026-09-09（Asia/Shanghai）。
- 批准人：当前仓库用户；依据本任务中明确的人工批准消息。
- 批准事项：Change 实现完成、Task 11.10、主规格同步、OpenSpec 归档及相关 Git 提交和推送。
- CHANGE_REVIEW: PASS
- CANDIDATE_PROMOTION: NOT_PROMOTABLE
- 本记录不代表 Promotion PASS，不授权修改生产版本指针；历史 Promotion FAIL 与基线证据缺失保持原状。

## 批准依据及完整标识

- 独立 Reviewer：Euler，Agent ID `01a0839f-40fc-7743-9904-8f99f1dd3e1b`，未参与最新实现。
- 依据报告：`reviews/runtime/runtime-replay-and-eval-hardening-independent-evidence-review.md`。
- 报告文件 SHA-256：`0a94f3d921d4f8657ab4013fac4070123cff369bcb32119afa782646eb4f84ad`。
- 产品源码快照（按 integrity_snapshot 的受保护文件集合）：`24fe59edbc75db2c5d667df7e58b069f63e136aad59a0ff22782cb27e0fa74fb`。
- Candidate：`0.3.0-candidate.1`。
- Candidate lock：`618f746c35c7df17a37a64d4338bbbfc73e3a9875fe6ad9ea56f471b166ac198`。
- Launcher SHA-256：`8aec4e641a0cfdee0040e33e2481cda79d99eb48f7cf70f1d4b53a2449ee74c2`。
- Hook SHA-256：`e276180b0bfd3d9d21e48f0b6e2ff7bcf2ecd2df3f33cbe7d58b3843cf43bf31`。
- 证据包：`evals/results/runtime-replay-and-eval-hardening-nested-diagnosis-20260909/final-lock/`。
- Regression suite ID：`rrh-final-lock-regression-suite-20260909`。
- Suite hash：`179b70a83526db786357354a5bdcddcae55c06cabe05e513e81b8db3e55c7b39`。
- Regression Set：`1.1.0`，hash `6004fb79ed7ec5de46310e017cf493b2362b3259ddf2222982d78e75d9a143ef`。
- 运行模型与 CLI：`gpt-5.6-terra`、`codex-cli/0.153.4`。

## 证据复用和流程范围

复用独立 Reviewer 已核对的三次 normal Smoke、六个真实 LLM 案例、六份 Runtime Eval 与 12-case Regression。此前测试、独立评审、Replay、Ablation、Calibration 和 Promotion 证据仅按报告声明用于未受影响的 Change 能力验证，不冒充当前候选锁的晋升证据。

Task 11.10 的完成依据为既有独立评审、最新收尾证据复核及本次人工批准。依据用户明确指令，本轮仅进行归档/规格校验、差异、提交范围和敏感信息检查，不重跑测试、产品 LLM、Regression 或 Release Gate，不修改产品实现。

当前候选晋升仍须另外满足相应证据和批准条件；本次 Git 提交/推送只发布已批准的 Change 实现和归档资料，不构成生产版本晋升。
