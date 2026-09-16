# 主备拓扑版本锁：限定接缝验收

日期：2026-09-10；Change：`us-equity-live-advisory-slice`。开发实施记录，不是独立评审、真实来源许可或 Promotion PASS。

## 已关闭的实施任务

| Task / 规格 | 实际实现与验证 | 证明边界 |
| --- | --- | --- |
| 1.3 / live-us-equity-data 来源契约与迁移 | v3 source-access/snapshot、UniverseSnapshot、SourceSelection 和 profile 3.0.0；来源角色、客户端/适配版本、域名、事实版本、未知/试拉用途、悬空选择与漂移负测；旧 v1/v2 数据契约仍可离线校验 | 不将旧包改名/改锁成新包；旧包完整 execution replay 不在本 Change 验收范围 |
| 3.1 / portfolio-council-orchestration 正式来源迁移 | discovery 从实际 Schema 读取版本；锁定 NASDAQ/两套行情/SEC/日历/身份/collection/路由；source_context.topology_lock 包含目录、访问配置、逐股选择、原文和 Evidence；现有 Trace 保存相同上下文，底层重算并比较实际 discovery | 主源与备用 collection 合成测试均实际 prepare、读取原文、重算 Gate 和上下文；尚未证明真实 Codex 加载或调用 |
| 4.3 / 来源及运行说明 | 更新中文使用说明、主备条件/目录覆盖/隐私/宿主入口/版本兼容说明；新增四来源 UNCONFIRMED 合成样例，实际验证 Schema | 不提供伪造 AUTHORIZED；原合成 TEST 持仓不是用户持仓或真实标的运行 |

Task 2.1、2.4、2.5、2.6、5.1 的整项证据归集仍待完成，不因本轮局部通过自动关闭。1.1、真实目录 1.5、真实 1→3 研究 5.2/5.3、独立评审 5.4 与人工批准 5.5 仍未完成。

## 实际命令及结果

工作目录为仓库根目录。所有 Provider HTTP 为合成响应；SDK 只作本地解析，模型与宿主执行为替身，不发起产品模型、行情、Regression 或全套 Gate。

```sh
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_profile tests.test_live_collection tests.test_live_eval_contract tests.test_live_contracts_gate -q
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_source_routing tests.test_live_nasdaq tests.test_live_collection -q
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_collection tests.test_live_source_routing tests.test_live_cli tests.test_live_profile -q
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -v
python3 -B -m unittest tests.test_product_config tests.test_native_invocation_validation tests.test_native_run_package -q
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

第一次聚焦暴露缺少 json import 和旧配置负测异常处理不匹配（39 项、13 errors），均为实现/测试错误，不是权限或网络问题；修复后 39/39。后续分组 32/32、32/32。最终当前 live 集合 **158/158、0 跳过、18.216 秒、退出码 0**；三个共享/fixture 接缝模块 **36/36、退出码 0**。共享测试打印的 `NATIVE_EXECUTION_PROOF_FAILED` 属于预期失败传播用例，不是本次真实 Council 执行。OpenSpec strict 与已跟踪差异空白检查通过；未跟踪文件不能仅凭 git diff 声称经过独立审阅。

完整 live 测试工具返回分段、命令、工作目录及 21 个相关文件 SHA-256 保存在 [live-topology-v3-test-result.json](live-topology-v3-test-result.json)。该清单不是完整候选源码快照，也不是用户运行包。测试临时产物使用 TemporaryDirectory，测试后清理；测试证明是执行日志，不冒充持久化真实研究。

新增负测实际修改底层 manifest/discovery 或源输入：缺选择、错来源、Schema 版本、模型、Schema 文件 hash、客户端版本、域名、试拉用途，均被确定性拒绝。两个 collection 场景核对 prepare 的 manifest 与 Trace 来源锁，读取缓存原文字节并重新加载运行上下文。报告测试从 v3 snapshot/Gate 渲染，验证显示 eastmoney、AKShare 版本与主源 503 原因。

## 证据复用与剩余范围

- 上一轮 155 项和更早 90/105/131 项记录保留历史语义，不用其 hash 冒充当前新增 profile 的运行锁。当前受影响 live 测试重新执行；未改的 fixture 安全机制另以 36 项兼容测试核对，不扩大为全仓门禁。
- 当前真实 collect 只接受四来源 v3；真实 prepare 拒绝旧 snapshot。内部已有 `authenticity_required=False` 只服务确定性合成测试，CLI 不暴露该开关、宿主不接受测试包；不将测试身份例外提升为生产许可。
- 当前冻结包锁与源码不同会失败，不支持通过改写历史 hash 迁移。旧 v1/v2 的数据解析与契约分支保留；这里没有声称旧完整运行能在新源码下直接继续执行。
- 剩余下一步是归集数据身份/预算/PIT/路由整项证据，再处理正式单股入口的实际数据与研究验收条件。尚未运行真实单股或三股 LLM/Eval，不具备人工完成批准条件。
- 全进程源码隔离仍为 UNVERIFIED；未修改代理、原生权限、金融判断或生产版本指针；不归档、提交、推送。
