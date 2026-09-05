"""Fail-closed filesystem permissions for learning-plane operations."""

from __future__ import annotations

from pathlib import Path


class LearningPermissionError(PermissionError):
    pass


class LearningPermissionPolicy:
    """Reflection may write learning artifacts only, never production state."""

    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root).resolve()
        self.learning_root = (self.repository_root / "learning").resolve()

    def can_write(self, path: str | Path) -> bool:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.repository_root / candidate
        candidate = candidate.resolve(strict=False)
        try:
            candidate.relative_to(self.learning_root)
        except ValueError:
            return False
        return candidate.name != "__init__.py"

    def assert_can_write(self, path: str | Path) -> None:
        if not self.can_write(path):
            raise LearningPermissionError(
                "learning plane cannot edit product Skills, Agent configs, Schemas, Risk Policy, "
                "default version pointers, or files outside learning/"
            )
