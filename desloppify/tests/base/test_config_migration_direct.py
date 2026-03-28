"""Direct coverage for config migration helpers."""

from __future__ import annotations

import json
from pathlib import Path

import desloppify.base.config.migration as migration_mod


def test_merge_config_value_deduplicates_lists_and_keeps_existing_dict_keys() -> None:
    config = {
        "ignore": ["a"],
        "zone_overrides": {"keep.py": "script"},
    }
    migration_mod._merge_config_value(config, "ignore", ["a", "b"])
    migration_mod._merge_config_value(
        config,
        "zone_overrides",
        {"keep.py": "vendor", "new.py": "test"},
    )

    assert config["ignore"] == ["a", "b"]
    assert config["zone_overrides"]["keep.py"] == "script"
    assert config["zone_overrides"]["new.py"] == "test"


def test_load_state_file_payload_rejects_non_dict_payloads(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(["not", "a", "dict"]))

    assert migration_mod._load_state_file_payload(path) is None


def test_migrate_from_state_files_merges_and_strips_state_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    state_file = tmp_path / "state-python.json"
    state_file.write_text(
        json.dumps(
            {
                "version": 1,
                "config": {
                    "ignore": ["smells::*"],
                    "exclude": ["dist"],
                    "unknown_key": "drop-me",
                },
                "issues": {},
            }
        )
    )

    captured: list[tuple[dict, Path]] = []

    def _save_config(config: dict, path: Path) -> None:
        captured.append((dict(config), path))

    result = migration_mod._migrate_from_state_files(
        config_path,
        save_config_fn=_save_config,
    )

    assert result["ignore"] == ["smells::*"]
    assert result["exclude"] == ["dist"]
    assert "unknown_key" not in result
    assert captured and captured[0][1] == config_path

    rewritten = json.loads(state_file.read_text())
    assert "config" not in rewritten


def test_migrate_from_state_files_returns_empty_when_state_dir_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "missing-dir" / "config.json"

    assert migration_mod._migrate_from_state_files(config_path) == {}
