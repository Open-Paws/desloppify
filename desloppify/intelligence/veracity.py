"""Veracity verification interface for review suggested fixes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TypedDict


class VeracityIssue(TypedDict):
    """Hallucinated API finding details."""
    method: str
    module: str | None
    message: str
    code_block: str


class VeracityPlugin(ABC):
    """Abstract base for language-specific veracity (de-hallucination) auditors."""

    @abstractmethod
    def verify_suggestion(
        self,
        suggestion: str,
        *,
        project_root: str | None = None,
    ) -> list[VeracityIssue]:
        """Audit a suggestion string for hallucinated APIs.

        Should extract code blocks and verify them against the local environment.
        Returns a list of detected hallucination issues.
        """
        raise NotImplementedError
