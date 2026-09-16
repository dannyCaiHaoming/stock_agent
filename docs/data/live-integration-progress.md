# Live 集成采集与宿主入口：阶段三证据

日期：2026-09-10。Change：`us-equity-live-advisory-slice`。本轮继续实现，不创建新 Change，不请求 Yahoo/SEC，不运行真实模型、全量 Regression 或 Release Gate，不归档、提交或推送。

## 被测标识

- 基线 HEAD：`e512a6364e1a7f52dc25f715d8edae76229bc279`。
- 候选声明仍为 `0.3.0-candidate.2-live`，不是晋升版本；该声明不能单独区分本轮与上一轮，必须同时引用下面的增量清单。
- [73 个增量产品/入口/依赖/测试/合成输入文件的完整 SHA-256](live-offline-phase-3.sha256)。清单 SHA-256：`1398443cebf089f805d7fcf8a79a5616590c3adfb9bfe7515f6f6ba4ebf38558`。基线加本清单界定被测代码；不是全仓库文档快照，也不是已审阅发布包。
- 新的数据版本：`yahoo-eod-adapter/0.2.0`、`yahoo-readonly-transport/1.0.0`、`us-equity-security-metadata/1.0.0`、`live-collection/1.0.0`、`sec-sections/0.3.0`。运行 discovery 从实际模块常量写入 `data_adapters`，源文件另受 live resource hash 约束。
- 本地 SDK 文件与依赖隔离证据见 [SDK 契约记录](live-sdk-contract.md)。旧 phase-2 的 hash 只表示当时版本，不应再用于宣称当前源码一致。

## 本轮实现与对应任务

| 任务 | 实现与关闭依据 | 不能据此宣称 |
| --- | --- | --- |
| 1.2 | 可选安装锁、实际 SDK 签名/Session 类型、端点代码路径与基础 Python 隔离检查 | Yahoo 准入或联网成功 |
| 2.1 | 行情日线＋chart 身份；SEC 封面交叉确认普通股/股类/交易所，拒绝 ETF/ADR/OTC/币种及冲突 | 已验证具体真实 ticker |
| 2.4 | SDK 逐请求预算、限次重试、权限硬失败锁、原文追加缓存与身份索引；旧 SEC/行情缓存测试复用 | 免费无限访问、全市场吞吐 |
| 2.5 | 集合采集/规范化后冻结唯一 cutoff；原始选择排除详情留审计，不传给专业上下文；PIT 后估值 | 历史回测可知性 |
| 3.1 | live 独立 source/profile/数据版本/文件锁；真实 prepare 要求可从两来源原文重建身份，合成旧格式不可充当真实身份 | Execution Replay 扩展或生产晋升 |
| 3.2 | Gate-scoped 只读 MCP 与既有角色/Skill 按来源分流，跨 run/调用/ID 拒绝；无 Provider 查询入口 | 当前应用缓存或真实 LLM 已加载新配置 |
| 3.4 | 共享输入的批次准备/逐股调用，整批预检先于模型，重复执行拒绝；失败不补建议、不联合交易 | 真实三股研究通过 |
| 3.5 | 既有宿主 `--profile live-us-equity --portfolio` 接口、原 normal 与 prepared-run 保留；采集/准备/启动失败传播，自检禁止隐式启动 | 本机真实 live Smoke 已通过 |
| 4.1 | 中文事实、反证/假设、来源及时间；完整组合市值/权重由合格价格重算；二次风险否决保持原结果 hash 不变 | 研究内容质量已通过 |
| 4.3 | 更新宿主用法、来源配置/暂停、外置状态、隐私、批次评分与合成输入说明，Schema 测试通过 | 已获准恢复抓取 |

上述是实现及各自确定性接缝完成；加载行为改变所需的真实 Smoke 没有豁免，继续留在 Task 5.2/5.3。Task 4.2 尚未以完整 live 样例关闭语义验收；5.1 最终限定证据归集、真实 1→3、独立复核与人工批准仍未完成。

## 实际命令与最终结果

工作目录：仓库根；统一 `TMPDIR=/private/tmp`，临时目录允许写入。

```sh
env TMPDIR=/private/tmp /private/tmp/stock-agent-live-deps.cBmS73/venv/bin/python -B -m unittest discover -s tests -p 'test_live_*.py' -q
```

最终结果：**101 tests，OK，exit 0**。包含真实本地日历、SDK Session 类型检查、内存响应→实际解析→缓存→身份→冻结→批次 prepare；最终只到 `DISPATCH_REQUIRED`，不启动 LLM。批次启动测试使用替身命令；不能将此 101 项称为真实端到端研究验收。

```sh
env TMPDIR=/private/tmp python3 -B -m unittest tests.test_native_run_package tests.test_native_evidence_gate tests.test_native_invocation_validation tests.test_native_eval tests.test_native_trace tests.test_native_replay tests.test_runtime_eval_job tests.test_native_execution_proof tests.test_product_config tests.test_portfolio_council_skill tests.test_host_proxy_scripts tests.test_development_environment -q
```

最终结果：**131 tests，OK，exit 0**。基础 Python 没有 yfinance/exchange_calendars，证明 fixture/旧入口接缝仍不强制依赖 live 安装。这是受影响集合，不是全量测试或完整 Gate。输出中 `proof-failure` 是既有预期负向测试。

```sh
bash -n scripts/run-product-smoke.sh
openspec validate us-equity-live-advisory-slice --strict
git diff --check
```

已执行且通过；不代表真实研究质量或发布批准。

## 实际发现并修复的接缝问题

1. SDK 自行捕获错误可能将认证失败变成空结果：新增持久于本次 Session 的失败状态；替身测试证明 403 不触发第二次 HTTP，SDK 吞异常后仍失败。
2. 采集器使用结构化缺口，而已有 snapshot 的 `gaps` 是字符串数组：保留原契约，将适合专业输入的简明缺口显式序列化，原始排除详情留在采集审计，不放宽 Schema。
3. 批次汇总调用了错误的 Eval 参数及文件位置：改为 `verify_runtime_eval_job(eval_result_path=.../eval/result.json)`。替身改用 `autospec`，并增加实际评分作业的绑定/失败重验；测试评分是明确的合成注入，未冒充实际评分执行。
4. 旧 Eval Prompt 路径测试缺少真实 prepare 始终存在的 `run_dir`：首次 131 项中一项错误；补齐测试来源运行后，聚焦 6 项及最终 131 项通过。没有增加“缺字段就默认 fixture rubric”的降级。

## 完成边界

`CHANGE_REVIEW`：未执行；`CANDIDATE_PROMOTION`：未申请；`ISOLATION: UNVERIFIED`。

Yahoo 仍暂停，来源许可未确认；不要为了完成率填充已授权来源配置。已实现宿主入口不等于允许现在运行。尚需真实数据的单股/三股加载、研究与语义评分证据，再做独立复核与人工完成批准；不自动重复模型调用或扩建网络设施。
