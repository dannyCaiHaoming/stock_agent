# 新 Specialist 草案契约：三股真实验收

2026-09-11，当前 Change `us-equity-live-advisory-slice`，用户要求继续刷新插件并执行三股验收。使用合成持仓及既有来源批准/预算；未下单、未修改代理、未重跑完整 Gate。

## 版本与执行

- 插件由既有 `stock-agent-local` 本地市场更新，未新建市场或手改市场配置。
- 实际安装：`0.3.0+codex.20260911004112`。
- plugin.json SHA-256：`20c94cf1cc7b6a4bb9bd0ca37029c7c810641b93469deaccd736bdd25d62b5c3`。
- 既有 protected-source snapshot：`dda20007ea09f389689f2ea4900389bdb5c81332d5e544d36be43e91ecbd59ad`，不是全进程隔离证明或全工作区快照。
- 批次：`live-batch-71d79069-4a70-4a41-af32-7ba769bef92c`。
- Batch manifest canonical hash：`60e9c8fa5461a2d4f4dc0c2eb7ae40df47587cb3725cab96e62786c535707132`。
- 数据 snapshot hash：`06e92fb0b472e32bd458d56dd6a005f9161ad313ba46a7932d9fcd20f525b2ac`。
- 共同 cutoff：`2026-09-11T00:42:16.098635Z`。
- 产物根目录：`/private/tmp/stock-agent-draft-three.cXRaDF`。

```sh
codex plugin add product@stock-agent-local --json
bash scripts/run-product-smoke.sh --profile live-us-equity \
 --portfolio /private/tmp/stock-agent-live-three.xcXLr5/portfolio.json \
 /private/tmp/stock-agent-draft-three.cXRaDF/smoke
```

宿主命令 PATH 使用 `/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin`；SourceAccess 及 SEC 联系信息由外置配置/环境传入，缓存沿用 `/private/tmp/stock-agent-nasdaq-tls.dZ9JbD/cache`，未提交私人身份或原始包。完整逐股调用参数、执行事件、加载证明、stderr 与进程结果在各自 invocation 和 batch/launch-logs。

源码与安装缓存中的 invocation、Hook recorder、execution proof、runtime eval、version manifest 均逐字一致。插件验证通过；更新版本绑定后20项 product-config/live-profile 测试通过，OpenSpec strict 通过；上轮95项接缝仅在对应实现未变的范围复用，不将配置测试当作模型证明。

## 三股产品运行：3/3 PASSED

| 证券 | run_id | 原生 Eval hash |
| --- | --- | --- |
| MSFT | live-bbab0d91-ccce-4598-a7ef-f66afa760f00 | 322157bcce5c44f7226704155cfe751cc92c66694e6cf57f1e008bd533d13fb0 |
| AAPL | live-4b15c513-b150-4a33-adb1-d6c5e6fe6c75 | 8cca5267b1c9cc610ac0a3d5671b47b8318ee5816f5ffa1c65eeffa5210daabc |
| NVDA | live-a4308743-049f-4384-af63-07186a74c2e6 | 7cbfc8dad9d362f4f12125d6cc71018c39d052b7d43583cff690002c6c25e2f3 |

三股均有独立 Analyst/Skeptic、CIO、Risk、decision.json、report.md、decision_trace.json 和原生 eval/result.json，合法终态均 SAFE_NO_TRADE。宿主批次退出0，但状态明确为 RUNTIME_SAFE_RESEARCH_UNASSESSED，不能据此勾选5.3。

已逐份重验六个 Specialist：原始 `.native.json` 均不含 skill_execution；其 canonical hash 与实际 SubagentStop 相同；从冻结 Invocation 仅增加技术字段后的对象与保存报告完全一致。MSFT 上一轮的 Skill hash 转抄阻断未复现。所有旧运行包原样保留。

## 独立研究质量评分

每股使用新的外置 Eval Job；运行 eval-prepare、保存固定 eval-smoke-prompt，使用现有 Terra dev_eval 独立子会话，再执行 eval-execution-proof --collect-native-output 与 eval-finalize。调用 Prompt、事件与 stderr 在 `semantic-<ticker>-invocation/`；评分及执行证明在 `semantic-<ticker>/`。未因失败重评。

### MSFT：PASS

作业 `live-draft-semantic-bbab0d91`，五维度均 PASS/3，实际执行证明及 `verify_runtime_eval_job` 底层重算通过。

- Eval hash：`d3dd2b3bc78f66ad71323208f0a818188cc0921d4f1cc808886e0aaddc5b062f`。
- 执行证明 hash：`e4fab5116d44d86df94669968cc5d4bb50060a5c9da29c9c81fd1710b88154c9`。

### AAPL：评分交接 FAIL，未形成正式 Eval

作业 `live-draft-semantic-4b15c513`；父会话 `01a08df4-9078-78f0-8d87-554800443b2c`，子会话 `01a08df4-db9b-7ed3-ae07-770633321d8a`。

实际子会话最后消息是已将结果写入文件的说明，而非单个 JSON；子 Agent 自行写入 semantic-result.json（内容版本为 semantic-rubric-draft/1.0.0），违反本次只返回原生 JSON、不写文件的输出契约。执行证明命令返回 CHILD_STRUCTURED_OUTPUT_MISSING:dev_eval；未执行 finalize。协调进程退出0不代表评分通过。

未从文件猜测/补回最终输出，未转换为旧契约或补写 hash。此问题属于评分输出方式，不是三股研究运行失败，也不是已验证的研究质量 FAIL；不能用未验证草案宣称通过。

### NVDA：PASS

作业 `live-draft-semantic-a4308743`，五维度均 PASS/3。真实独立评分、原生结果交接、执行证明、finalize 及 verify_runtime_eval_job 底层重验均通过。

- Eval hash：`a6db62bdafe0ed0846a5f5615a3b3246564ed615c5964a0031a31c21084ec69b`。
- 执行证明 hash：`9521fc2fb242733fb8310b9c8abeeb45776a860fb29c34aa8fc4717fd688ef97`。

### 最终批次汇总

仅将 MSFT/NVDA 有效评分作业放入外置 semantic-index.json，未将 AAPL 自写草案冒充完成的 Eval。实际执行：

```sh
/private/tmp/stock-agent-live-combined.jtbR6l/venv/bin/python -B -m product.runtime.cli summarize-live-batch \
 --repo /Users/caihaoming/Documents/stock_agent \
 --batch-dir /private/tmp/stock-agent-draft-three.cXRaDF/smoke/batch \
 --semantic-index /private/tmp/stock-agent-draft-three.cXRaDF/semantic-index.json \
 --output-dir /private/tmp/stock-agent-draft-three.cXRaDF/summary
```

返回5、状态 FAILED：MSFT/NVDA PASSED，AAPL 为 LIVE_CHILD_SEMANTIC_EVAL_MISSING，汇总 action=null，不把未通过研究验收的动作发布为已验证建议。summary_hash=`24aedada3e8fbe3a988da3d54066509088d7a0a9c2b0240e93230672e27ee294`。最终汇总 manifest hash=`048874cabcadc71497c3f30bd2d6df349919698be4cfdc39e8445ccd608e8d6f`；它包含执行状态更新，不与最初 prepare manifest hash 混淆。

所有本轮模型进程已结束；未自动重试评分。结束时 protected-source snapshot 仍为 `dda20007ea09f389689f2ea4900389bdb5c81332d5e544d36be43e91ecbd59ad`，git diff --check 通过。只剩 AAPL 的合法评分交接证据缺口，不需要把已完成三股产品运行当作失败重跑。

## 完成边界

Task 5.3仍需三个子运行分别通过真实研究质量验收；AAPL 已明确缺少合格评分产物，因此当前不启动已知前置缺失的5.4独立收尾复核，不勾选5.3/5.4/5.5。全进程隔离 UNVERIFIED；未归档、提交、推送。
