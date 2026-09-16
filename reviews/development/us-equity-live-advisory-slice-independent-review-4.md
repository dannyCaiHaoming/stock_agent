# 第四次独立只读差异复核

`CHANGE_REVIEW: PASS`

## 结论

当前实现满足现有 Delta Spec 与 Tasks 2.2、2.3、2.4、4.1–4.3、5.1–5.3 的收尾要求。

- Task 5.3 可完成。
- Task 5.4 仍需用户明确人工批准，Reviewer PASS 不能代替批准。
- 本结论不是 `Promotion PASS`，不批准归档、提交、推送或生产晋升。

## 关键核对

1. `validate_common_stock_source_bundle` 从逐证券 package 重验 source access、scoped portfolio、snapshot、calendar、SourceSelection、身份、PIT、Evidence、conflicts、data gaps 和失败状态，再通过 canonical constructor 重建完整 Gate 与 preparation 并逐对象比较。
   - `model_calls=0`、`provider_requests_completed_before_freeze=true` 等固定字段来自重建结果，不能只靠重签 preparation hash 改变。
   - 失败项须有一致 `failure_code`；存在 `collection-error.json` 时，其完整内容 hash 和内部 `failure_code` 均须匹配。
   - benchmark、macro、options 会重新读取并校验 snapshot hash、范围和 PIT 后参与最终全量比较；peer candidate pool 只作为候选资料绑定，不提升为 Evidence。
2. `common_stock_stage.py` 在创建 Codex 进程前校验 run manifest，并从当前 Handoff、Gate、Agent、Skill、模型重建 stage、coverage、holding request、invocation、packet、task 和 dispatch index；live package 会再次调用底层 source-bundle validator。
3. Handoff 到 `live-portfolio/2.0.0`、再到当前 v4 的路径没有固定三股产品上限；实际采集逐证券隔离失败。
4. 旧 host `--profile live-us-equity` 和三个 batch CLI 已退役；必要共享实现、多维能力和历史读取未误删。
5. `us-equity-live-advisory-slice-final-focused-tests.json` 中声明的 34 个文件在复核时均存在且 SHA-256 匹配。记录结果为 `Ran 301 tests in 2.084s`、`OK (skipped=10)`、OpenSpec strict validate PASS；只能解释为离线确定性范围。

## 复核快照 SHA-256

```text
e1431ba034ca52e91523944370114c783c3869e791267ef78abef16a0d3db3fd  proposal.md
3ff05e75fa6cb3e62bb7934d5a2f16a0d939239971914f3f0916c516883433cd  design.md
0cca5084c44b0d57e41aff70fe6d9e46a540343020e99a3f177cda0130cf066f  tasks.md
9ca8ac74b62363044dc825e54a6ea695d1e8d2742905fe20913cc385fd31b849  delta spec
6b899c9097e2e1f2e5711aa35b56b3614fbe6e8401c391d5769fbc0803b72fa0  common_stock_data.py
e62e66fbfd46a2e0bde19f2bbf7e6290efec410818d489755bf3bb4f3097955f  common_stock_stage.py
31990cbaec95bc07f6033aee3698f1126caee7091e196f4d54aadedd2806c27c  common_stock_research.py
2646e232b99b8ae6255ba20e3267fdefa502dd62f39274c6d3ad7bcdf49668b3  collection.py
469ed6f5e3109986e93e71b17529d3f812f4e72fcbe7f656b4e6f3e0b2e8be45  cli.py
e53e0a746637cd2c281ccae558bc4fa5d9ab188f1873a162405eea41c932d537  run-product-smoke.sh
625152e883e07022c44bdc47969cfbc2c150ae9610104fa039f369d4449479ff  live-snapshot-v4.schema.json
a5fcecc2c492bb63b9a1b736af6f6f7a4d2c5486a9188949187d056257a39c15  live-source-access-v4.schema.json
3ef5a32a91688a595ff03ddaaf7138f9f69b1454243aea63ad03ecec027cba98  live-portfolio-v2.schema.json
da03140ad6f5ea71ed05eec88c663a02555376cbe8d2d1d9ba4933c18481df7d  portfolio-handoff-v3.schema.json
ea10c888f417bb370a63377936646fff478539694a47f3cb3aa4182a88141c11  personal-research-approval.json
698cce75e254fe90e9459e07300a11632ee6aa501fe8ec4c267f83cb7af0e181  version-manifest.json
ed69a4603d431b5b7d4576c917021987e03719dc97bef772e9e3a1b22e345095  portfolio-council/SKILL.md
de7de23e2cd01a032fe6781d3ced1dffdfca050c3f28627cf4ad2d92dd0fe104  test_common_stock_research_contracts.py
bbb51ed841b51223b4397f0e90e808d00cfd6b72739b09701a2f29e31bef4f55  final-focused-tests.json
94f651f5fc176f84ff9941721546bb5e5f0d63fdc9a61ddbc778429c9d5b972d  cleanup inventory
```

批准记录 canonical hash：`84f7f933a5107a2948315ad66ff424b44f6db8773d691668a86a5eb4850f2960`。

## 非阻断风险和证明边界

- 历史 live profile/Schema 仍含三股限制，但当前 host 产品入口明确拒绝该路径。
- 批次请求量随普通股数量线性增长，不代表固定持仓上限，也不证明无限吞吐。
- 工作区包含多个 Change 的混合修改，本次复核依靠以上完整 hash 锁定对象。
- version manifest 中两项 Runtime Eval assurance hash 存在跨 Change 漂移，不被本 Change 的数据准备或 Agent 前校验读取；后续 Promotion 需单独协调。
- 不要求外部签名或不可变信任根，也不证明攻击者同步替换全部源码、产物和 hash 时仍可检测。
- 本复核不证明真实 Provider 当前可用、研究资料充分、Company Analyst 质量、完整 Council、Risk、Regression、Release Gate 或 Promotion。
