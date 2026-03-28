"""Direct tests for review packet snapshot redaction and prepare guardrails."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import desloppify.app.commands.review.coordinator as coordinator_mod
import desloppify.app.commands.review.external as external_mod
import desloppify.app.commands.review.prepare as prepare_mod
from desloppify.app.commands.review.batch.scope import require_batches
from desloppify.app.commands.review.prepare import do_prepare
from desloppify.app.commands.review.runner_packets import write_packet_snapshot
from desloppify.base.exception_sets import CommandError


def _colorize(text: str, _style: str) -> str:
    return text

def test_write_packet_snapshot_redacts_target_from_blind_packet(tmp_path):
    packet = {
        "command": "review",
        "config": {"target_strict_score": 98, "noise_budget": 10},
        "narrative": {"headline": "target score pressure"},
        "next_command": "desloppify scan",
        "dimensions": ["high_level_elegance"],
    }
    review_packet_dir = tmp_path / "review_packets"
    blind_path = tmp_path / "review_packet_blind.json"

    def _safe_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    packet_path, _ = write_packet_snapshot(
        packet,
        stamp="20260218_160000",
        review_packet_dir=review_packet_dir,
        blind_path=blind_path,
        safe_write_text_fn=_safe_write,
    )

    immutable_payload = json.loads(packet_path.read_text())
    blind_payload = json.loads(blind_path.read_text())

    assert immutable_payload["config"]["target_strict_score"] == 98
    assert "target_strict_score" not in blind_payload["config"]
    assert blind_payload["config"]["noise_budget"] == 10
    assert "narrative" not in blind_payload
    assert "next_command" not in blind_payload


_P_SETUP = "desloppify.app.commands.review.prepare.setup_lang_concrete"
_P_BUILD_PAYLOAD = "desloppify.app.commands.review.prepare.build_review_packet_payload"
_P_WRITE_QUERY = "desloppify.app.commands.review.prepare.write_query"


def _do_prepare_patched(*, total_files: int = 3, state: dict | None = None, config: dict | None = None):
    """Call do_prepare with mocked dependencies; return captured write_query payload."""
    args = SimpleNamespace(path=".", dimensions=None)
    captured: dict = {}

    def _fake_write_query(payload):
        captured.update(payload)

    with (
        patch(_P_SETUP, return_value=(SimpleNamespace(name="python"), [])),
        patch(
            _P_BUILD_PAYLOAD,
            side_effect=(
                lambda **_kwargs: (
                    (_ for _ in ()).throw(ValueError("no files found at path '.'. Nothing to review."))
                    if total_files == 0
                    else {
                        "total_files": total_files,
                        "investigation_batches": [],
                        "workflow": [],
                        "narrative": {"headline": "x"},
                        "config": {"noise_budget": (config or {}).get("noise_budget")},
                    }
                )
            ),
        ),
        patch(_P_WRITE_QUERY, side_effect=_fake_write_query),
    ):
        do_prepare(
            args,
            state=state or {},
            lang=SimpleNamespace(name="python"),
            _state_path=None,
            config=config or {},
        )
    return captured


def test_review_prepare_zero_files_exits_with_error(capsys):
    """Regression guard for issue #127: 0-file result must error, not silently succeed."""
    with pytest.raises(CommandError) as exc:
        _do_prepare_patched(total_files=0)
    assert exc.value.exit_code == 1
    assert "no files found" in exc.value.message.lower()


def test_review_prepare_zero_files_hints_scan_path(capsys):
    """When state has a scan_path, the error hint mentions it."""
    with pytest.raises(CommandError) as exc:
        _do_prepare_patched(total_files=0, state={"scan_path": "."})
    assert "--path" in exc.value.message


def test_review_prepare_query_redacts_target_score():
    captured = _do_prepare_patched(
        total_files=3,
        config={"target_strict_score": 98, "noise_budget": 10},
    )

    assert "config" in captured
    config = captured["config"]
    assert isinstance(config, dict)
    assert "target_strict_score" not in config
    assert config.get("noise_budget") == 10


def test_require_batches_guides_rebuild_when_packet_has_no_batches(capsys):
    with pytest.raises(CommandError) as exc:
        require_batches(
            {"investigation_batches": []},
            colorize_fn=_colorize,
            suggested_prepare_cmd="desloppify review --prepare --path src",
        )
    assert exc.value.exit_code == 1
    err = capsys.readouterr().err
    assert "no investigation_batches" in exc.value.message
    assert "Regenerate review context first" in err
    assert "follow your runner's review workflow" in err


def test_review_command_modules_avoid_package_level_review_facade_imports() -> None:
    package_root = Path(__file__).resolve().parents[3]
    review_root = package_root / "app" / "commands" / "review"
    offenders: list[str] = []
    banned = (
        "from desloppify.intelligence import review as",
        "from desloppify.intelligence.review import ",
        "import desloppify.intelligence.review as ",
    )
    for module_path in review_root.rglob("*.py"):
        text = module_path.read_text(encoding="utf-8")
        if any(token in text for token in banned):
            offenders.append(str(module_path.relative_to(package_root)))
    assert offenders == []


def test_intelligence_review_modules_do_not_import_app_review_commands() -> None:
    package_root = Path(__file__).resolve().parents[3]
    review_intel_root = package_root / "intelligence" / "review"
    offenders: list[str] = []
    for module_path in review_intel_root.rglob("*.py"):
        text = module_path.read_text(encoding="utf-8")
        if "desloppify.app.commands.review" in text:
            offenders.append(str(module_path.relative_to(package_root)))
    assert offenders == []


def test_review_packet_payload_ownership_is_centered_in_packet_build() -> None:
    prepare_src = inspect.getsource(prepare_mod)
    external_src = inspect.getsource(external_mod)
    coordinator_src = inspect.getsource(coordinator_mod)

    assert "from .coordinator import build_review_packet_payload" not in prepare_src
    assert "from .coordinator import (" not in external_src
    assert "from .packet.build import" in prepare_src
    assert "from .packet.build import" in external_src

    assert "def build_review_packet_payload(" not in coordinator_src
    assert "def write_review_packet_snapshot(" not in coordinator_src
