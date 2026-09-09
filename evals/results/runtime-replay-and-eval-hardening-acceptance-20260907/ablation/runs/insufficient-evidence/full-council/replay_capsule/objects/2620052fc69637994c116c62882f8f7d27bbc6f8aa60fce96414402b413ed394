"""Static boundary checks for the Codex-native product runtime.

The guard is intentionally syntactic.  It prevents an accidental Python LLM
orchestration backend from entering the product while leaving investment semantics
to the Agent/Skill layer.  The 0.1.0 reference state machine is explicitly
allowlisted only while it remains marked ``REFERENCE_ONLY = True``.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BANNED_MODEL_IMPORTS = (
    "anthropic",
    "google.generativeai",
    "langchain",
    "litellm",
    "openai",
)
REFERENCE_ALLOWLIST = {Path("council/orchestrator.py")}


@dataclass(frozen=True)
class BoundaryViolation:
    path: str
    line: int
    code: str
    detail: str


def _literal_dict(node: ast.Dict) -> dict[str, ast.AST]:
    result: dict[str, ast.AST] = {}
    for key, value in zip(node.keys, node.values):
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            result[key.value] = value
    return result


def inspect_python_source(source: str, *, path: str = "<memory>") -> list[BoundaryViolation]:
    tree = ast.parse(source, filename=path)
    violations: list[BoundaryViolation] = []

    for node in ast.walk(tree):
        imported: Iterable[str] = ()
        if isinstance(node, ast.Import):
            imported = (item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported = (node.module,)
        for module in imported:
            if module in BANNED_MODEL_IMPORTS or module.startswith(
                tuple(f"{prefix}." for prefix in BANNED_MODEL_IMPORTS)
            ):
                violations.append(
                    BoundaryViolation(path, node.lineno, "PYTHON_MODEL_SDK", module)
                )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parameter_names = {argument.arg for argument in node.args.args}
            simulated_roles = parameter_names & {
                "analyst_callback",
                "research_agent",
                "skeptic_callback",
                "synthesis",
            }
            if len(simulated_roles) >= 2:
                violations.append(
                    BoundaryViolation(
                        path,
                        node.lineno,
                        "MULTI_ROLE_CALLBACK_ORCHESTRATION",
                        ",".join(sorted(simulated_roles)),
                    )
                )

        if isinstance(node, ast.Dict):
            values = _literal_dict(node)
            subjective = {"thesis", "action", "confidence"}
            if subjective <= values.keys() and all(
                isinstance(values[key], ast.Constant) for key in subjective
            ):
                violations.append(
                    BoundaryViolation(
                        path,
                        node.lineno,
                        "HARDCODED_INVESTMENT_CONCLUSION",
                        "thesis/action/confidence are all literals",
                    )
                )

    return violations


def inspect_product_python(product_root: Path) -> list[BoundaryViolation]:
    product_root = product_root.resolve()
    violations: list[BoundaryViolation] = []
    for path in sorted(product_root.rglob("*.py")):
        relative = path.relative_to(product_root)
        source = path.read_text(encoding="utf-8")
        found = inspect_python_source(source, path=str(relative))
        if relative in REFERENCE_ALLOWLIST:
            tree = ast.parse(source, filename=str(relative))
            marked_reference = any(
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "REFERENCE_ONLY"
                    for target in node.targets
                )
                and isinstance(node.value, ast.Constant)
                and node.value.value is True
                for node in tree.body
            )
            if marked_reference:
                found = [
                    violation
                    for violation in found
                    if violation.code != "MULTI_ROLE_CALLBACK_ORCHESTRATION"
                ]
        violations.extend(found)
    return violations
