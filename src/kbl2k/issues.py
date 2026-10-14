"""검증 결과 표현."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Level = Literal["error", "warning"]


@dataclass(frozen=True, order=True)
class Issue:
    file: str
    path: str
    level: Level
    message: str

    def __str__(self) -> str:
        where = f"{self.file}:{self.path}" if self.path else self.file
        return f"[{self.level.upper()}] {where} — {self.message}"


def error(file: str, path: str, message: str) -> Issue:
    return Issue(file, path, "error", message)


def warning(file: str, path: str, message: str) -> Issue:
    return Issue(file, path, "warning", message)


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)
