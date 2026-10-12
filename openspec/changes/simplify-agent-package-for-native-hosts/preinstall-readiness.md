# 安装前接缝补验与可审阅安装范围

- `source_id`: `native-preinstall-readiness:20261006`
- `as_of`: `2026-10-06`
- `retrieved_at`: `2026-10-06`
- 授权：用户已选择MRVL并允许本Change D5/D6内的接缝修复和确定性验证；实际安装、产品模型、来源网络和最终发布仍分别待批准。

## 本次完成的补验

102项受影响确定性检查通过，0失败/错误，耗时15.412秒；覆盖精确导出、操作方准备、原生资料、旧资料/同行消费者、研究补充事实与Memory。源码前后完整SHA-256一致。实际命令、原输出与完整hash见[preinstall-operator-check.json](preinstall-operator-check.json)。此前先跑的12项包含在本批中，不累加覆盖数。

三个临时测试导出包均实际导入业务MCP、prepare与material_preparation；操作方CLI创建合法合成连接/任务并验证错误授权拒绝。冻结同行复用以禁止Provider调用的边界完成，未加载nested_codex、codex_hook_recorder、common_stock_data或旧Stage。测试产物在临时目录中，不是三个宿主的实际安装或加载。

从common_stock_data拆出的错误类型、缓存闭包检查和补充事实合并，由旧消费者重导出并与新同行消费者共享；snapshot冻结与raw-record闭包保持原算法。对HEAD基线的8项函数/类比较中7项AST完全一致，另1项仅把raw-record验证依赖指向新纯业务模块，见[preinstall-extraction-recheck.json](preinstall-extraction-recheck.json)。旧算法负例仍受102项检查保护，不恢复控制器或用动态import隐藏缺依赖。

导出必须带操作方prepare、material_preparation、同行数据依赖及5份既有公开政策/Quote清单。缺任一所需入口/资源均在创建候选前拒绝；临时包实际从自身读取这些资源。加入资源只保证既有可选数据入口依赖完整，不授权调用Provider、OpenD或账户；未新增Provider、模型后端或Agent。

## 精确来源与外置安装提案

采用[acceptance-proposed-source-list-v2.json](acceptance-proposed-source-list-v2.json)中的270项文件/hash。来源清单SHA-256为`82c86bd39535ca00fafdbc76ca38aaccbd659ba478be8a24bb8e663bd74e4411`，计算规则在JSON中明示。相对原251项清单新增19项准备依赖/资源，prepare.py字节变化；原清单保留，不回签其旧hash或测试。

- 基线：HEAD `a23dc764b082591e3c47c8bb30e3569040bc18b8`；Intake初始化取该批准基线，其他269项取清单所列工作树字节，安装前再次验证漂移。
- 排除：并行broker实现、Tiger Intake/broker Schema、当前.claude、私有状态/凭据/会话/账本、原模型转录、未列出的dirty文件。既有独立交易模块/Skills保留，真实私人写入权限不随导出恢复。
- 来源闭包与导出器已有密钥模式检查通过。这是精确内容与确定性接缝核对，不是独立完整敏感审阅、人工安装批准、候选晋升或实际宿主支持。
- 新根：`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006`。本次只读检查该根尚不存在且无符号链接祖先；未创建。创建时仍须重验冲突。
- 解释器：现有`/Users/caihaoming/Documents/stock_agent/.venv/bin/python`，不安装新环境或改全局配置。

获安装批准后，仅在新根内物化source-reviewed及claude-code/codex/opencode三个product-workspace；生成各项目角色/Skills/MCP配置，按Claude Code→Codex→OpenCode实际核对。业务产物和私有grants分置源码外，不覆盖已有安装、用户配置或原备份。目标已存在、源漂移或同名冲突则停止对应写入。

本次安装提案可以独立批准为“外置安装准备，零产品模型/零来源网络”。宿主MCP启用、实际权限/隔离检查仍依对应产品会话的原生能力；不能用项目配置或事后hash替代全进程只读证明，不能由项目启动另一个宿主模型进程。

## MRVL样本重验与完整验收缺口

公共身份、8835条冻结Gate事实和ADI/MPWR同行绑定重验通过，原资料前后hash一致。业务范围/技术和市场数学在内存中按当前prepare_task的证券预筛选及能力规则核对，未创建实际任务、连接、token或新研究稿，见[mrvl-preinstall-sample-recheck.json](mrvl-preinstall-sample-recheck.json)。三宿主必须消费相同证券、cutoff和原事实，不从历史报告猜取证据。

| 原准备项 | 真实状态 | 选中正文 | 对本次验收的限制 |
| --- | --- | --- | --- |
| RESEARCH_REPORT_DISCOVERY | SOURCE_LIMITED | 0 | 不认证read_documents正向执行或独立研报正文齐全 |
| MACRO_RESEARCH_DISCOVERY | BLOCKED_CONFIGURATION | 0 | 不能省略该失败并声称完整Macro依赖就绪 |
| MARKET_RESEARCH_DISCOVERY | SOURCE_LIMITED | 0 | 保留原获取/选择范围及缺口 |
| PEER_SELECTION | READY | 0 | ADI/MPWR原事实物化已验证，不复制旧研究判断 |

原准备manifest不是新原生报告，material_inputs仍要求合法原生准备回执。安装闭包已经通过，与“旧样本完整原生研究就绪”分别判断。后续须按批准范围明确复用公开材料及原失败的合法交付方式；若需要重新准备或补取正文，先给出具体来源、任务和预算请求，不自动修复来源/配置、替模型选择资料、改Schema/hash转换旧稿或绕过Macro门禁。

当前可推进下一步是外置安装准备；完整产品执行须先解决样本准备血缘和阻断，再明确三个当前产品会话、实际模型、调用/时间上限与停止条件。不得把有限加载或拒绝检查当6.2–6.4完整研究通过。

## 当前状态

后续用户已在本会话批准“安装吧”。三个项目文件已按上述精确范围安装，入口说明在`/Users/caihaoming/Documents/stock-agent-native-acceptance/20261006/README.md`；实物hash、导入/未授权拒绝、保护源码及实际版本记录见[installation-evidence.json](installation-evidence.json)。本文件前面的“尚未创建/待安装批准”描述保留当时提案状态；目前只剩实际宿主加载/权限、样本准备与模型预算等对应缺口，不能把项目文件安装视为产品执行完成。

Change仍17/24。6.1仅完成准备部分；6.2–6.4真实宿主、7.x内容/人工完成和8.1归档发布未完成。模型、来源网络、账户调用、实际安装、专项Eval/Replay/Regression/Calibration/Ablation/Promotion均未运行；未新建/切换分支、归档、提交或推送。
