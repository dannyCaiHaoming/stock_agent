# 限定验收记录

日期：2026-10-01；范围：三个开发Skill、四个交付文件及本Change的验收记录。未修改产品实现、根开发指令、Agent配置、模型路由、权限、历史证据或版本锁。工作区已有其他Change修改，未暂存、提交或回退。

## 独立复核时的四文件内容标识

以下为文件原始字节SHA-256，用于本次独立复核绑定，不是产品版本锁，也不要求今后每次诊断计算它们。

| 文件（仓库相对路径） | 行数 | SHA-256 |
|---|---:|---|
| `.agents/skills/agent-handoff-development/SKILL.md` | 40 | `8dfc90c659615d652ab228d3e2e51b0248b9cb217881fc3d34acb3e7ff9b7b1b` |
| `.agents/skills/change-evidence-closeout/SKILL.md` | 43 | `1ee2852b3a2fc0cea437b220c8588635e4015ccb15c913d0e0ee5cd8420ac63c` |
| `.agents/skills/codex-development-diagnostics/SKILL.md` | 34 | `a9efd30d3cfd62c83b78f5db9bd8a70093d617f38af135cfffd90fd86eb0def4` |
| `.agents/skills/codex-development-diagnostics/references/research-handoff-diagnostics.md` | 33 | `9f7e313734a7efaf5f9dea12f288930c5ef419b98f7923928749fb2dda4bbf38` |

## 实际检查

工作目录为仓库根目录。既有验证器路径：`/Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py`。

| 检查 | 实际结果 | 对应任务 |
|---|---|---|
| 三个Skill的既有`quick_validate.py` | PASS：获临时依赖授权后逐个输出`Skill is valid!`，均退出0；首次缺依赖失败保留于下文 | 2.1完成 |
| 四文件相对链接、占位及尾随空白 | PASS：4文件、14个链接、0错误 | 2.1的已完成部分 |
| 已跟踪诊断文件差异空白检查 | PASS：`git diff --check`无输出，退出0；新文件另经上项检查 | 2.1的已完成部分 |
| 本Change OpenSpec strict | PASS：`Change 'codify-development-handoff-skills' is valid`，退出0 | 2.1的已完成部分 |
| 独立情境处理与规格复核 | PASS：同一独立Reviewer先判断S1–S8再对照规格，未发现实现问题；四交付文件hash不变，复用该复核；随后补齐的静态结果不是Reviewer重跑结果 | 2.2完成 |
| 产品LLM / Smoke / Replay / Regression / Gate | 未执行，非本次验收要求 | 不以未执行冒充PASS |

### 命令及环境错误

三个Skill分别执行，均在导入阶段失败，未安装依赖：

```sh
python3 /Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/agent-handoff-development
python3 /Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/change-evidence-closeout
python3 /Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/codex-development-diagnostics
```

系统`python3`解析为`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`。通过桌面依赖查询获得的既有Python为`/Users/caihaoming/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`；使用该绝对路径替换以上三个命令中的`python3`，逐个退出1，仍缺PyYAML。额外只读检查`/usr/bin/python3 -c 'import sys, yaml; print(sys.executable); print(yaml.__version__); print(yaml.__file__)'`也报同一缺依赖错误；`/usr/local/bin/python3`只是系统3.13的符号链接，不另行重复验证。

以下已实际执行通过：

```sh
git diff --check -- .agents/skills/codex-development-diagnostics/SKILL.md
openspec validate codify-development-handoff-skills --strict --no-interactive
```

链接/占位/空白及内容标识使用下面的一次性标准库检查，未增加仓库运行脚本；实际退出0，输出`files=4 links=14 errors=0`：

```sh
python3 - <<'PY'
from pathlib import Path
import hashlib, re
files = [Path('.agents/skills') / name / 'SKILL.md' for name in ('agent-handoff-development', 'change-evidence-closeout', 'codex-development-diagnostics')]
files.append(Path('.agents/skills/codex-development-diagnostics/references/research-handoff-diagnostics.md'))
errors = []
links = 0
for path in files:
    content = path.read_text()
    for line, text in enumerate(content.splitlines(), 1):
        if text.rstrip() != text:
            errors.append(f'{path}:{line}: trailing whitespace')
        if '[TODO:' in text or 'PLACEHOLDER' in text:
            errors.append(f'{path}:{line}: unfinished placeholder')
    for target in re.findall(r'\]\(([^)]+)\)', content):
        links += 1
        if not (path.parent / target.split('#')[0]).resolve().exists():
            errors.append(f'{path}: missing link {target}')
    print(f'{path}: lines={len(content.splitlines())} sha256={hashlib.sha256(path.read_bytes()).hexdigest()}')
print(f'files={len(files)} links={links} errors={len(errors)}')
for error in errors:
    print(error)
raise SystemExit(bool(errors))
PY
```

## 有限情境与证明范围

输入为[review-scenarios.md](review-scenarios.md)，独立返回保存于[independent-review.md](independent-review.md)。S1覆盖结构与授权继承；S2覆盖执行/收集与仅诊断；S3覆盖引用、任务归属信息不足与语义；S4覆盖证据复用及失效；S5覆盖无OpenSpec项目；S6覆盖不相关任务；S7覆盖共享修改与普通文件；S8覆盖环境路径及必要日志。均为合成材料下的处理判断，不是真实金融研究、自动发现测试、修复执行测试或节省token的实测。

## 当前停止点

Task 1.1–1.3、2.1和2.2已完成，原进度5/6。用户随后回答“是”，明确批准本Change完成及同步归档、限定提交推送，见[人工批准](human-approval.md)。Task 2.3的归档/发布正在执行，实际结束后更新；此前“继续授权推进”仍仅是临时校验依赖授权。收尾结果以[发布记录](publication.md)为准。

## 临时依赖授权与静态补证

在明确询问“是否允许仅将PyYAML安装到仓库外临时目录用于本次校验，不修改项目或系统Python依赖”后，用户回复“继续授权推进”。该回复作为本次明确授权，覆盖Task 2.1原不安装约束的单次例外；保留首次环境失败，未以手工解析替代验证器。

实际创建目录并安装，安装命令退出0：

```sh
mktemp -d /private/tmp/stock-agent-skill-validation.XXXXXX
python3 -m pip --isolated --disable-pip-version-check install --only-binary=:all: --no-deps --no-cache-dir --target '/private/tmp/stock-agent-skill-validation.kYbd7X' 'PyYAML==6.0.2'
```

安装产物只在`/private/tmp/stock-agent-skill-validation.kYbd7X`；系统和项目依赖未安装或修改。该临时目录未提交Git，保留供本地复核，可被系统清理。作用域仅为下列命令的`PYTHONPATH`，未持久化到项目配置。以下三个命令分别实际执行，均输出`Skill is valid!`并退出0：

```sh
PYTHONPATH='/private/tmp/stock-agent-skill-validation.kYbd7X' python3 '/Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py' '.agents/skills/agent-handoff-development'
PYTHONPATH='/private/tmp/stock-agent-skill-validation.kYbd7X' python3 '/Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py' '.agents/skills/change-evidence-closeout'
PYTHONPATH='/private/tmp/stock-agent-skill-validation.kYbd7X' python3 '/Users/caihaoming/.codex/skills/.system/skill-creator/scripts/quick_validate.py' '.agents/skills/codex-development-diagnostics'
```

实际依赖查询命令：

```sh
PYTHONPATH='/private/tmp/stock-agent-skill-validation.kYbd7X' python3 -c 'import sys, yaml; print(sys.executable); print(yaml.__version__); print(yaml.__file__)'
```

结果为系统Python3.13、PyYAML`6.0.2`及`/private/tmp/stock-agent-skill-validation.kYbd7X/yaml/__init__.py`，确认导入来自临时目录。

补证前实际执行`shasum -a 256`读取四个交付文件，全部仍匹配上表及独立Reviewer所核内容。因此复用已有独立复核及14链接检查，没有重跑情境或产品；本轮仅补齐原来缺失的静态验证器执行。同步本次授权记录及任务状态后，再执行相同OpenSpec strict与诊断文件diff检查，结果保存于上述检查表。开发Skill指导与静态通过不证明产品运行、实际token节省或生产晋升。

## 发布定位链接修正

限定提交检查发现三个定位链接对应其他Change未提交文件，故在本次授权范围内将源码定位改为已提交的Runtime入口和研究阶段。专用模块名称仅作为存在时可查询的候选位置，不要求提交其他Change源码；方法、授权及验证边界未改变。

原独立复核hash和结论保留，只复用未变的方法/情境判断，不宣称Reviewer复核过新字节。两处定位文档的最终hash、受影响静态重验和提交可用链接检查见发布记录；当前四文件共11个链接，实际工作区及限定提交均可解析。未重跑模型或增加独立复核轮次。
