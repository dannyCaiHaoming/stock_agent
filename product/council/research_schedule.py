"""多维研究的有界依赖调度状态机；实际 Subagent 生命周期由 Codex 持有。"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


TERMINAL_STATES = {"COMPLETED", "FAILED", "TIMEOUT", "BLOCKED"}


class ResearchScheduleError(ValueError):
    pass


@dataclass(slots=True)
class DependencyResearchScheduler:
    tasks: Sequence[Mapping[str, Any]]
    max_concurrency: int = 3
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if type(self.max_concurrency) is not int or self.max_concurrency < 1:
            raise ResearchScheduleError("RESEARCH_SCHEDULE_CONCURRENCY_INVALID")
        copied = [copy.deepcopy(dict(item)) for item in self.tasks]
        identifiers = [item.get("task_id") for item in copied]
        if any(not isinstance(item, str) or not item for item in identifiers):
            raise ResearchScheduleError("RESEARCH_SCHEDULE_TASK_ID_INVALID")
        if len(identifiers) != len(set(identifiers)):
            raise ResearchScheduleError("RESEARCH_SCHEDULE_TASK_DUPLICATE")
        known = set(identifiers)
        for item in copied:
            dependencies = item.get("depends_on", [])
            security_ids = item.get("security_ids", [])
            if (
                not isinstance(dependencies, list)
                or set(dependencies) - known
                or item["task_id"] in dependencies
                or not isinstance(security_ids, list)
                or len(security_ids) != len(set(security_ids))
            ):
                raise ResearchScheduleError("RESEARCH_SCHEDULE_DEPENDENCY_INVALID")
            item["status"] = item.get("status", "WAITING")
            if item["status"] not in {"WAITING", "RUNNING", *TERMINAL_STATES}:
                raise ResearchScheduleError("RESEARCH_SCHEDULE_STATUS_INVALID")
            item.setdefault("report_ref", None)
            item.setdefault("failure_code", None)
        self.tasks = copied
        self._assert_acyclic()

    def _assert_acyclic(self) -> None:
        dependencies = {item["task_id"]: set(item["depends_on"]) for item in self.tasks}
        remaining = set(dependencies)
        resolved: set[str] = set()
        while remaining:
            ready = {task_id for task_id in remaining if dependencies[task_id] <= resolved}
            if not ready:
                raise ResearchScheduleError("RESEARCH_SCHEDULE_CYCLE")
            resolved.update(ready)
            remaining -= ready

    def _task(self, task_id: str) -> dict[str, Any]:
        matches = [item for item in self.tasks if item["task_id"] == task_id]
        if len(matches) != 1:
            raise ResearchScheduleError("RESEARCH_SCHEDULE_TASK_UNKNOWN")
        return matches[0]

    def _block_failed_dependents(self) -> None:
        by_id = {item["task_id"]: item for item in self.tasks}
        changed = True
        while changed:
            changed = False
            for item in self.tasks:
                failed_dependencies = [
                    task_id for task_id in item["depends_on"]
                    if by_id[task_id]["status"] in {"FAILED", "TIMEOUT", "BLOCKED"}
                ]
                if item["status"] == "WAITING" and failed_dependencies:
                    item["status"] = "BLOCKED"
                    item["failure_code"] = "DEPENDENCY_FAILED:" + ",".join(sorted(failed_dependencies))
                    self.events.append({
                        "event": "BLOCKED",
                        "task_id": item["task_id"],
                        "failed_dependencies": sorted(failed_dependencies),
                    })
                    changed = True

    def ready_tasks(self) -> list[dict[str, Any]]:
        self._block_failed_dependents()
        by_id = {item["task_id"]: item for item in self.tasks}
        active = sum(item["status"] == "RUNNING" for item in self.tasks)
        slots = max(0, self.max_concurrency - active)
        ready = [
            item for item in self.tasks
            if item["status"] == "WAITING"
            and all(by_id[task_id]["status"] == "COMPLETED" for task_id in item["depends_on"])
        ]
        return [copy.deepcopy(item) for item in ready[:slots]]

    def record_started(self, task_id: str, *, invocation_id: str) -> None:
        ready_ids = {item["task_id"] for item in self.ready_tasks()}
        if task_id not in ready_ids:
            raise ResearchScheduleError("RESEARCH_SCHEDULE_START_INVALID")
        item = self._task(task_id)
        item["status"] = "RUNNING"
        item["invocation_id"] = invocation_id
        self.events.append({"event": "STARTED", "task_id": task_id, "invocation_id": invocation_id})

    def record_completed(self, task_id: str, *, report_ref: str) -> None:
        item = self._task(task_id)
        if item["status"] != "RUNNING" or not report_ref:
            raise ResearchScheduleError("RESEARCH_SCHEDULE_COMPLETION_INVALID")
        item["status"] = "COMPLETED"
        item["report_ref"] = report_ref
        self.events.append({"event": "REPORT_AVAILABLE", "task_id": task_id, "report_ref": report_ref})

    def record_failed(self, task_id: str, *, failure_code: str, timeout: bool = False) -> None:
        item = self._task(task_id)
        if item["status"] != "RUNNING" or not failure_code:
            raise ResearchScheduleError("RESEARCH_SCHEDULE_FAILURE_INVALID")
        item["status"] = "TIMEOUT" if timeout else "FAILED"
        item["failure_code"] = failure_code
        self.events.append({"event": item["status"], "task_id": task_id, "failure_code": failure_code})
        self._block_failed_dependents()

    def progress(self) -> dict[str, Any]:
        counts = {status: 0 for status in ("WAITING", "RUNNING", *sorted(TERMINAL_STATES))}
        for item in self.tasks:
            counts[item["status"]] += 1
        return {
            "total": len(self.tasks),
            "counts": counts,
            "reports_available": [
                item["report_ref"] for item in self.tasks if item["report_ref"] is not None
            ],
            "terminal": all(item["status"] in TERMINAL_STATES for item in self.tasks),
        }
