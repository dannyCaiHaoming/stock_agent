"""可替换的 Demo Tool Port；底层复用现有 Gate-scoped MCP 语义。"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from product.runtime.fixture_mcp import GateScopedFixtureTools


class EvidenceQueryPort:
    """只暴露当前 run 与 invocation 的 Gate 合格 Evidence。"""

    def __init__(self, tools: GateScopedFixtureTools) -> None:
        self._tools = tools

    def query(self, *, evidence_ids: Sequence[str]) -> dict[str, Any]:
        return self._tools.query(
            run_id=self._tools.run_id,
            agent=self._tools.agent,
            invocation_id=self._tools.invocation_id,
            evidence_ids=evidence_ids,
        )

    @property
    def events(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._tools.events)


class DeterministicMathPort:
    """只基于 Gate 合格 Evidence 执行声明的确定性计算。"""

    def __init__(self, tools: GateScopedFixtureTools) -> None:
        self._tools = tools

    def calculate(
        self,
        *,
        calculation_id: str,
        operation: str,
        evidence_ids: Sequence[str],
    ) -> dict[str, Any]:
        return self._tools.calculate(
            run_id=self._tools.run_id,
            agent=self._tools.agent,
            invocation_id=self._tools.invocation_id,
            calculation_id=calculation_id,
            operation=operation,
            evidence_ids=evidence_ids,
        )

    @property
    def events(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._tools.events)
