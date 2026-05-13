"""Persona rotation for parallel review batches."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """Reviewer attention bias for a batch prompt."""

    name: str
    bias: str
    key_question: str


PERSONAS: tuple[Persona, ...] = (
    Persona(
        name="Pragmatist",
        bias="Simplicity over cleverness and unnecessary ceremony",
        key_question="Would a new team member understand this in 30 seconds?",
    ),
    Persona(
        name="Architect",
        bias="Boundaries, coupling, API surface consistency, and layer discipline",
        key_question="Does this respect the system's structural contracts?",
    ),
    Persona(
        name="Bug Hunter",
        bias="Edge cases, races, missing awaits, error swallowing, and null handling",
        key_question="What fails under edge cases or concurrent access?",
    ),
    Persona(
        name="Migrator",
        bias="Deprecated patterns, half-migrated code, stale shims, and dual-path confusion",
        key_question="What should have been cleaned up already?",
    ),
)


def assign_personas(batch_count: int) -> list[Persona]:
    """Return round-robin persona assignments for *batch_count* batches."""
    if batch_count <= 0:
        return []
    return [PERSONAS[index % len(PERSONAS)] for index in range(batch_count)]


def resolve_persona(name: str) -> Persona | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    return next((persona for persona in PERSONAS if persona.name.lower() == normalized), None)


def render_persona_block(persona: Persona | None) -> str:
    """Render prompt guidance for *persona* without changing scoring rules."""
    if persona is None:
        return ""
    return (
        f"REVIEWER PERSONA: {persona.name}\n"
        f"Attention bias: {persona.bias}\n"
        f"Key question: {persona.key_question}\n\n"
        "The persona biases where you spend attention, not the scoring rules. "
        "Apply the same evidence and confidence thresholds as every other batch.\n"
    )


__all__ = [
    "PERSONAS",
    "Persona",
    "assign_personas",
    "render_persona_block",
    "resolve_persona",
]
