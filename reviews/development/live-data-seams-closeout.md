# Live 数据接缝收尾与真实运行前置条件

日期：2026-09-10；Change：`us-equity-live-advisory-slice`。本记录为开发实施验收，不是独立 Review，也不是 Promotion PASS。

## 本轮修复

1. 主源的 fact 客户端/Schema 版本检查移动到可用性判断之前。以前错误版本叠加过期可能先触发备用，掩盖原始完整性错误；现在明确失败且备用调用为零。
2. Yahoo transport 升至 `yahoo-readonly-transport/1.2.0`。原先下载后才检查大小，现使用锁定 curl_cffi 的读取回调在超限块中止。实际库会忽略普通短返回值，因此采用 `CURL_WRITEFUNC_ERROR`，并以真实库 write_callback 验证传递，不能用简单 Python 回调替身冒充底层中止语义。
3. Yahoo 请求发送前拒绝 range=max、非日线/盘前盘后、缺失或非法起止、超过 366 天及重复歧义参数。读取超限记录明确错误、不重试、不触发备用；正文在限定成功后交还 SDK。
4. 增加备用源＋SEC 封面身份正负测试：market/ticker/版本/原文漂移、ADR、交易所、股类冲突及标点映射拒绝，不继承 Yahoo 身份字段。

## 任务与证据映射

| Task / Specs | 当前证据 | 判定 |
| --- | --- | --- |
| 2.1 / 行情身份、价格口径 | test_live_security_metadata（含新增四例）、test_live_collection 主/备身份原文重验及 prepare、test_live_market 和 test_live_eastmoney_market 未完成时段/口径 | 实施接缝完成；不证明真实上游身份材料可取得 |
| 2.4 / 批量、预算与缓存 | Yahoo 11 例含真实 SDK Session 与 curl 回调绑定、发送前范围、超限立即停止；Eastmoney transport/contracts 的预算、实际 send 计数、缓存时间、拒绝锁定；SEC client 和 NASDAQ 限长/分页测试 | 确定性验收完成；不声称真实请求可达 |
| 2.5 / 冻结→PIT→上下文/估值 | test_live_source_routing、test_live_contracts_gate、test_live_collection：单 cutoff、未来/过期、父闭包、同源估值、缺价不重新归一化、版本错误不回退 | 实施接缝完成；不改 fixture 时间规则 |
| 2.6 / 受控故障转移 | 来源选择、拒绝后零备用、无数据/过期、两源失败、不拼接、报告来源及失败原因的确定性测试已通过 | 实施部分齐全；实际主行情调用与 Task 5.2 合并，仍不勾选整项 |
| 5.1 / Design 1.2、7 的限定归集 | 当前 167 项 live 测试、Schema/SourceSelection/Profile/Trace/Risk/报告/Eval/宿主接缝、strict validate、相关源码/配置/输入 hash 与实际输出 | 限定确定性验收归集完成；不是全量 Gate |

NASDAQ 默认 20 行 / totalrecords=7139 仍仅为旧技术观察，不是全池采集验收。Task 1.5 的真实有界分页未执行。

## 实际执行与产物

```sh
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_security_metadata tests.test_live_source_routing -v
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_yahoo_transport tests.test_live_market tests.test_live_collection -v
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest tests.test_live_yahoo_transport -q
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -v
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

聚焦结果分别为 25、21、11 项通过；最终集合 **167/167、无跳过、6.220 秒、退出码 0**。strict validate 与已跟踪文件差异空白检查通过。未触发真实行情、Council、Regression、Calibration、Ablation 或完整 Gate。

执行证据：[live-data-seams-closeout-tests.json](live-data-seams-closeout-tests.json)，SHA-256：`52cc3acf414ebb43bdebdf2904ec59e717cebe502d24c973c9a372bd9ed7cacb`。包含命令、工作目录、工具返回的完整分段输出及 220 文件完整 hash。

hash 范围为 product/tests/scripts/evals/grading 的显式文件清单，加依赖/合成输入；不包含私人运行状态，不冒充全仓 Git 快照。输入样例内嵌于已锁定测试文件，外置临时测试包按测试清理；记录输出不是持久化真实运行包。依赖使用原合并锁，未安装或升级软件。

上轮 158 项记录及 36 项共享/fixture 接缝保持历史标识。主备路由、Yahoo transport 及新增身份测试受影响，使用当前结果替代其旧通过范围；未修改的 SEC/报告/Eval 等仍重新包含在本轮有限 live 集合中，不引用更早 59/105/131 计数宣称当前候选全链路通过。模型评分使用替身的测试仅证明绑定和失败传播，不是实际语义评分。

## 不能继续真实运行的具体前置条件

现行 Proposal、Design 1/1.1/7、live-us-equity-data Specs 和 Task 1.1 明确要求“来源准入确认后才正式采集”，并规定旧技术试拉不自动追加次数或转为产品 Evidence。现有来源记录仍未确认；用户说明个人自用，不应被写成上游已授权。因此本轮不构造 AUTHORIZED，也不让宿主通过空配置或试拉包启动。

这是一项项目验收契约前置条件，不是对用户用途作违法认定，也不是代理、权限或测试失败。若继续以个人研究方式推进，可供人工选择的调整是：将“项目内允许个人研究运行”与“上游许可核实状态”拆为独立字段，显式保留后者 UNVERIFIED；仍保留有限请求、拒绝/限流立即停止、身份/PIT/Evidence/Risk、隐私与真实研究验收。此方案尚未获专项批准，本轮未修改 Specs、访问门禁或增加新 profile。

或者，继续保留现有契约并提供可核实的来源准入依据。两种路径均不要求改代理配置，也不等于可绕过服务拒绝或无限抓取。

Task 1.1、1.5、2.6、5.2、5.3、5.4、5.5 保持未完成；当前 17/24，不具备人工完成批准条件。全进程隔离继续 UNVERIFIED；不归档、提交或推送。
