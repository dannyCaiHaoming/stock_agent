# 三股采集失败定位（2026-09-11）

对应 Task 5.3，仍未完成。未修改产品实现、历史数据或版本锁，未启动 Council 或语义评分，未归档、提交、推送。

## 实际执行与证据

- 输入：外置合成持仓 MSFT/AAPL/NVDA，各10股，现金10000 USD，不代表用户真实账户。
- 产物根：`/private/tmp/stock-agent-live-three.xcXLr5`。
- 实际入口：`bash scripts/run-product-smoke.sh --profile live-us-equity --portfolio /private/tmp/stock-agent-live-three.xcXLr5/portfolio.json /private/tmp/stock-agent-live-three.xcXLr5/batch-smoke`。通过既有 live Python 环境、既有外置来源批准和缓存运行；SEC 联系身份仅通过宿主环境传入，不存入本记录。
- 输入文件 SHA256：`a49c4df8510ffe4692c8f4b1ef7bd4b418ea6150acfb2c6fa2903bf7d9af8712`。
- 启动前既有保护范围的源码快照：`6617a8dbf838f940ae904ba4426bfaf8d9df959ce2f9a606a3e3e1996581af4c`，与已通过单股相同；不是全工作区快照或全进程隔离证明。
- 宿主退出码：2；`collect-live` 阶段 `SEC_COMPANY_COLLECTION / SEC_DOCUMENT_INVALID`。
- 原始错误产物：`batch-smoke/data/collection-error.json`，SHA256 `1eb326304e25d8f3a353970748e93db2552b5446a4717eabf3dd6a87bb7340eb`。
- 三股 Yahoo SourceSelection 均已成功：MSFT `b1a34146eaeee3ff0e47ebebc13a9c9a2ec0ff1fbd83d1cecb376083254a3f97`；AAPL `fd1f03a55a6a88be5e0564ed9f20405742993d1c6a1fb694b4db038427c13bdc`；NVDA `f8b8fc15c96cf6230fde6dd77f6c12047e879a96fac6767cf2f34977d666446b`。
- 未创建 batch，没有子 run_id、LLM 调用或决策产物；不能将行情成功视为三股验收通过。

## FIRST_DIVERGENCE / ROOT_CAUSE

SEC 两次响应均 HTTP 200。读取苹果历史页 `CIK0000320193-submissions-001.json` 后，本地解析失败。

原始缓存记录 `26c2144b57cd1e7d6f9399bbe4b6b1cadf87b9c7392beb849ec39af34ac0b604`；原文字节 SHA256 `25eca683c9774d8d92dcc4e3e2381ca1a89fc5ceb325e46dff6defee78380899`。该页1246行，其中109行不满足现有文档路径规则；已核对的失败示例为 `primaryDocument` 空字符串，包括 `0000912057-00-023442` 的2000年10-Q。

`collection.py` 固定获取一页历史；`sec_client.py` 将整页交给 `sec.py`；后者对任意空文档名抛错。缺少历史文档元数据与危险路径使用相同整页失败策略，导致当前研究也被旧记录阻断。不是行情不可用、403、代理或 LLM 非确定性。

## 待确认的最小契约调整

建议仅将历史索引中缺少主文档名的记录显式隔离，记录 accession、原因与原始页 hash，不构造 URL，不进入可用 filing/Evidence；关联财务数据继续按未核实公开来源隔离。非空非法路径、路径穿越、身份/时间/数组结构冲突仍严格失败。增加局部正负测试后再运行新的三股批次，不覆盖本次失败包。

这会改变现有“空文档名导致整页失败”的契约，尚未实施，不偷偷跳行、不替换股票来规避。已通过单股证据保持原适用范围。Task 5.3/5.4/5.5 未勾选；ISOLATION 仍为 UNVERIFIED。
