"""任务使用的业务资源字节绑定；不选择宿主模型或改写历史锁。"""
from pathlib import Path

from product.runtime.hashing import file_hash
from product.tools.research_scope import CAPABILITY_BINDINGS
from product.tools.material_contracts import MATERIAL_ROLES

ROOT = Path(__file__).resolve().parents[1]


def resource_bindings(capability, role):
    skill = CAPABILITY_BINDINGS.get(capability, (None, None))[1]
    if skill is None:
        skill = {"COMPANY_RESEARCH": "company-research", "FIXTURE_COMPANY_RESEARCH": "company-research",
                 "INDEPENDENT_FIRST_PASS": "counter-thesis", "FIXTURE_COUNCIL_DECISION": "portfolio-council",
                 "RESEARCH_SYNTHESIS": "portfolio-council"}.get(capability, "research-report-analysis")
    names = {"version-manifest.json", "contracts/council-decision-contract.json", "mcp/research.py", "agents/" + role + ".md", "skills/" + skill + "/SKILL.md",
             "skills/evidence-grounding/SKILL.md", "deterministic/risk.py", "deterministic/policy.py"}
    names.update(str(p.relative_to(ROOT)) for p in (ROOT / "schemas/runtime").glob("*.json"))
    names.update(str(p.relative_to(ROOT)) for p in (ROOT / "tools").glob("*.py"))
    return {name: file_hash(ROOT / name) for name in sorted(names)}
