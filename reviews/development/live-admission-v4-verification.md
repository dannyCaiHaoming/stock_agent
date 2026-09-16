# 个人研究双状态准入：限定接缝证明

所属 Change：`us-equity-live-advisory-slice`。本记录关闭已批准 Design 1.3 的实现差异，不是实际研究或 Promotion PASS。

## 本轮结果

- 新 source-access/snapshot/profile 为 4.0.0；历史 v1/v2/v3 状态不重解释。
- `require_source_admission` 统一校验批准记录、完整 canonical hash、范围、时间、状态；当前 collection 仅接受 v4，Gate 和上下文从底层重验。批准记录同时作为被锁定资源。
- Yahoo、NASDAQ、东方财富以及当前 SEC 路径使用同一准入检查。SEC 的旧离线客户端行为不重写；当前 v4 调用对 401/403/429 锁住失败、不继续请求。请求预算、价格、身份、PIT、Evidence 和 Risk 不放宽。
- 中文报告分别展示操作者批准、上游 UNVERIFIED、批准 hash 和限制。样例默认 NOT_APPROVED，不含联系身份或实际持仓。
- 最终 175 项 live 确定性测试 PASS、无跳过；OpenSpec strict validate 与 git diff --check PASS。完整命令、原始输出和文件 SHA-256 见 `live-admission-v4-test-results.json`。首次新增渲染用例遗漏必填字段曾失败，已保留失败输出及仅修测试的说明，没有隐藏失败或放宽契约。

## Task 与证据适用范围

| Task | 本轮关闭证明 |
| --- | --- |
| 1.1 | 来源说明保留四源条件、未知额度、域名及限制；批准记录独立保存，上游未核实不伪造授权 |
| 1.3 | v4 Schema、统一准入及缺失/未知/暂停/DENIED/范围/时间/hash 正负测试；旧契约测试仍通过 |
| 3.1 | 当前 profile/discovery/prepare/Trace 接通，真实原文字节合成接缝与来源锁漂移负测通过；不等于真实模型已加载 |
| 4.3 | 新运行说明、未批准样例 Schema、双状态中文报告渲染与批准 hash 测试通过 |
| 5.1 | 受影响 live 接缝 175 项和严格校验；未执行平台全量 Regression/Calibration/Ablation/Gate |

旧 `live-data-seams-closeout-tests.json`（SHA-256 `52cc3acf414ebb43bdebdf2904ec59e717cebe502d24c973c9a372bd9ed7cacb`）是调整前 167 项证明，不冒充 v4。未改的固定 Agent/Skill、fixture、Risk 原证据仅在文件 hash、输入和依赖一致时继续适用；新来源请求准入以本轮实际测试为准。

Task 1.5、2.6 的真实目录/主行情调用与 5.2 单股实际验收继续保留；5.3 三股、5.4 独立复核、5.5 人工完成批准未完成。全进程隔离仍 UNVERIFIED。未归档、提交或推送。

## 本轮真实宿主尝试：阻断，未运行模型

经授权使用既有 `scripts/run-product-smoke.sh --profile live-us-equity`，以 MSFT＋虚构数量和现金、外置 v4 配置执行一次单股入口。完整脱敏命令、输入/输出路径、SHA-256 与原始错误事件见 `live-admission-v4-host-attempt.json`。

- FIRST_DIVERGENCE：`NASDAQ_UNIVERSE` 的第 1 个请求（limit=200，offset=0），`NASDAQ_TRANSPORT_FAILURE`；09:56:53.550211Z 开始，09:56:54.238430Z 失败。
- ROOT_CAUSE：仅能确定请求层失败；当前适配器将 URLError/TimeoutError 合并包装并丢失底层错误类型，现有证据不足以确定 DNS、TLS、代理或具体上游原因。不能将先前 TLS 观察推断成此次实证。
- 实际退出码 2；未获得目录/快照、未调用主备行情或 SEC、未启动 Specialist/CIO/Risk，LLM 调用 0。
- 错误产物 SHA-256：`71290838e58d3a38053bc40eeb697575b5d6681df0b7eb403d3df25bec2a1949`。
- 按 Design 7 停止，无自动重试、无绕过目录、无切源或代理变更。未把失败当 NO_TRADE 或正式研究 PASS。

当前进度 18/24；阻断的是实际目录传输，不是用户批准状态。尚无依据要求用户修改某项系统/代理配置。下一步需要针对该传输错误补充可脱敏的底层原因，再决定最小修复；不默认重跑 Council 或全量 Gate。本记录不是独立评审或人工完成批准。
