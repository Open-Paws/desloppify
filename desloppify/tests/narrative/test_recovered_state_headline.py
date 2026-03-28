"""Narrative regression coverage for plan-reconstructed state."""

from __future__ import annotations

from desloppify.intelligence.narrative.core import NarrativeContext, compute_narrative
from desloppify.state_io import empty_state


def test_compute_narrative_does_not_claim_first_scan_for_reconstructed_state() -> None:
    state = empty_state()
    state["stats"] = {"open": 2}
    state["work_items"] = {
        "review::src/foo.ts::abcd1234": {
            "id": "review::src/foo.ts::abcd1234",
            "status": "open",
            "detector": "review",
            "tier": 2,
        },
        "review::src/bar.ts::efgh5678": {
            "id": "review::src/bar.ts::efgh5678",
            "status": "open",
            "detector": "review",
            "tier": 2,
        },
    }
    state["scan_metadata"] = {
        "source": "plan_reconstruction",
        "plan_queue_available": True,
        "reconstructed_issue_count": 2,
    }

    narrative = compute_narrative(state, NarrativeContext(command="status"))

    assert narrative["headline"] is not None
    assert "Scan metrics unavailable" in narrative["headline"]
    assert "First scan complete" not in narrative["headline"]
