# 开发环境：仅在配置、路径、权限或启动问题时读取

## 入口和路径

现有底层入口为 `python3 -m product.runtime.cli`（模块调用从仓库根），`nested-codex-smoke` 是宿主脚本消费的统一 LLM launcher，不是开发自检的直接模型入口。真实运行使用下文宿主方式，不复制旧管道命令或创建第二套 Python LLM 编排。旧 preflight 执行入口已退役，历史产物仅供读取。

路径无关转发入口为 `python3 <仓库路径>/scripts/council-dev.py <既有子命令> ...`。它复用底层 CLI 参数；普通命令省略 `--repo` 时从脚本位置定位，其他相对路径按调用时目录解析。`prepare-execution-replay` 仍由原实现物化密封快照，之后 `nested-codex-smoke --run-dir ...` 自动选择该运行 manifest 的冻结 workspace，最后调用原 `finalize-execution-replay`。Regression 仍显式消费 run-index，缺案例不会自动启动模型；已获授权的新案例先经 prepare 和同一 nested-codex-smoke 执行。

开发自检在当前 Codex 环境进行。`council-dev.py self-check check-run --run-dir ...` 或 `self-check trace-check ...` 仅转发确定性检查；其他命令拒绝。确定性单元测试直接按授权范围运行，不调用项目沙箱或完整 Council。

| 名称 | 来源与约束 |
|---|---|
| repo_root | 普通运行显式 `--repo`；Execution Replay 使用准备阶段返回的冻结 workspace，冲突时拒绝 |
| product_root | 对应 repo_root 下的 product；产品子进程和 MCP 必须使用该目录，不依赖操作者当前目录 |
| run_dir | 显式参数，对应唯一 run_id 与 manifest output_dir；新执行不得覆盖已有 invocation |
| state_dir | run_dir 下 `.codex-runtime`，每次运行独立 sqlite/logs/tmp，不共用 |

相对参数在入口按原调用 cwd 解析一次，随后传规范路径。活跃源码/模板禁止个人绝对路径；实际环境 manifest 中的绝对路径是审计事实，应保留。内容寻址并密封的 Replay Capsule 物化是合法重放，不等同于临时复制源码绕过加载。

兼容旧式会话证明时，`smoke-prompt` 与 `eval-smoke-prompt` 支持显式 `--sessions-root`；省略时仅解析 `CODEX_HOME/sessions`，未设置 CODEX_HOME 则解析用户主目录下的 `.codex/sessions`。模板生成不扫描或读取会话。统一 launcher 的正常运行仍使用 run-scoped 事件，不转回全局会话查找；需要读取旧会话时仅使用明确授权的目录。

## 权限与保证边界

- 开发只修改授权源码；保留当前 Codex 原生权限，不自动提权或修改系统配置。
- 独立 Reviewer 默认读取代码差异、规格和已有运行包。补跑只报告具体缺口，由用户授权宿主入口执行；不把独立性实现为新建沙箱。
- 全进程源码强制只读为 **UNVERIFIED**，经人工批准排除在当前 Change 完成保证之外。launcher、Hook、MCP 等进程可能写入原生权限允许的文件；hash 检查不能阻止写入。
- 历史隔离与 preflight 产物保留供审计，不授权当前启动；旧启动函数明确拒绝，不再根据外部沙箱声明关闭原生沙箱。原生权限、Hook、run-scoped 状态、Evidence/PIT/Risk 和 fail-closed 校验不变。
- 不重新排查代理、不修改 Shadowrocket 或域名、不关闭 network_proxy、不开放整个 CODEX_HOME、不复制认证或会话。
- 旧 --review、review-run/review-probe/nested-codex-probe、environment-preflight、permission-probe 和 --preflight-report 在薄入口及底层入口明确非零拒绝，不回退、不读取运行包、不创建产物或调用模型；直接旧启动 API 同样拒绝。
- preflight 不再执行；本机 doctor 仅按既有授权用途使用，不作为日常源码检查、证据读取的必需前置。缺少预备 run 或权限探针不是普通开发的阻断条件。

## 宿主代理与手动 Product Smoke

按本次用户授权，宿主 Terminal 可以运行 `bash <仓库路径>/scripts/run-product-smoke.sh`。
脚本每次调用 `detect-host-proxy.sh`，保存只读系统查询的原始输出与退出码，
优先使用 `scutil --proxy` 的生效 HTTP/HTTPS 设置；禁用服务中的旧端口和进程名称不作为代理依据。
HTTP/HTTPS 地址分别传递大小写代理环境变量；仅 SOCKS 时使用 `socks5h`，先由现有
`codex doctor` 验证 transport，未知结果或失败即停止，不猜 HTTP 端口。
已连接 VPN/隧道路由且没有显式代理时不新增代理变量；UNKNOWN 停止并保留证据。

默认产物位于新的系统临时目录，代理地址只保存在本地产物中，不写入业务配置或提交 Git。
脚本复用 `prepare → nested-codex-smoke → check-run`，保留已有 Codex 原生沙箱、Hook、
run-scoped 状态及严格完成判定；不启动额外外层沙箱，不修改代理/域名/源码权限配置。
这是一条用户授权的宿主产品启动方式，不是独立只读复核权限证明；不得将它冒充
Task 4.2 的全进程源码保护证据。TUN 网络下不再要求外层嵌套成功。
本次仅执行脚本聚焦测试与宿主只读检测，不自动调用模型或完整 Gate。

Execution Replay 的准备与 finalizer 仍复用既有确定性 CLI。准备完新运行后，仅在宿主 Terminal 使用：
`bash <仓库路径>/scripts/run-product-smoke.sh --prepared-run <新重放run目录> <新的外置调用证据目录>`。
该分支不重新 prepare，不强制使用当前工作树；现有转发器按 manifest 选择冻结根。
完成后按既有手册显式执行 finalize-execution-replay；check-run 不替代配置等价性 finalizer。

重放 prepare 必须经当前 council-dev.py，以保存外置 host-replay-source.json；
该来源指针不修改历史锁。宿主 transport 校验来源 manifest/Capsule 和冻结内容后，
给冻结 launcher 调用的 Codex 补 --skip-git-repo-check，实际命令及适配器 hash
存入 run/invocation/host-transport.json。普通运行不使用该参数；缺来源指针拒绝。
既有失败 run 不复用、不补写；使用原 source_run 和新的目录/run_id 重新 prepare。
本轮未执行 Replay，不能宣称这条重放链已有真实验收。

## 模型与消耗

模型偏好的权威来源为 [model-routing.json](../../product/model-routing.json)：普通开发、重复 Runtime、重大疑难分析分别使用其中对应值；不要在这里维护第二份 ID 清单。

模型由本机支持的配置或显式 `--model` 参数选择，而非 Prompt 自动切换。记录请求模型、配置来源及运行中实际模型；未知时标未确认，不把帮助包含 `--model` 当账户模型可用证明。Desktop 当前会话若无法由仓库配置改变，明确告知用户选择，不声称切换成功。重大争议升级保留原策略所需的争议 ID 和人工批准。

未变输入复用已验证缓存；真实运行次数按当前 Change 明确预算执行。失败保留事件并先定位，不重复调用 LLM 猜原因。

## 排障顺序与证据

先读取已有路径/manifest、命令与配置、加载事件和终态。只调用明确授权的确定性检查，不自动执行 doctor、网络探针或模型；需要补证先说明缺口。

区分 `DISCOVERED`（文件/hash）、`CONFIG_VALIDATED`（配置解析）与 `LOAD_VERIFIED`（真实加载事件）。静态检查不得输出加载成功，模型自述“已加载”不能替代执行证明。

指定失败 run 时读取 `invocation/prompt.txt`、invocation/environment manifest、Codex/Hook 事件、stderr、process-result 和终态产物，输出 FIRST_DIVERGENCE、ROOT_CAUSE 或证据不足。Codex 退出码为零不等于 Council 完成：仍须检查 Skill、Specialist、CIO、Risk、终态和场景要求的 decision/report/trace/eval。合法前置终止按原契约标阶段不适用，不伪造执行。

诊断默认不重跑、不修复、不归档、不推送。报告仅保留白名单字段、必要路径及 hash，不复制全局配置、Token 或用户消息。遇范围外问题只记录；验收升级需按 [开发流程](workflow.md) 请求批准。
