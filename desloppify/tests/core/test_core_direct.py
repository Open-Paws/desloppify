"""Direct tests for core helper modules with prior transitive-only coverage."""

from __future__ import annotations

import json
import logging

import desloppify.base.output.fallbacks as fallbacks_mod
import desloppify.base.search.query as query_mod


def test_write_query_injects_config_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(query_mod, "load_config", lambda: {"target_strict_score": 97})
    monkeypatch.setattr(
        query_mod,
        "config_for_query",
        lambda cfg: {"target_strict_score": cfg["target_strict_score"]},
    )
    query_path = tmp_path / "query.json"
    payload = {"command": "status"}

    result = query_mod.write_query(payload, query_file=query_path)

    saved = json.loads(query_path.read_text())
    assert saved["command"] == "status"
    assert saved["config"]["target_strict_score"] == 97
    assert result.ok is True
    assert result.status == "written"


def test_write_query_records_config_error(tmp_path, monkeypatch):
    def _raise_config_error():
        raise ValueError("invalid config")

    monkeypatch.setattr(query_mod, "load_config", _raise_config_error)
    query_path = tmp_path / "query.json"
    payload = {"command": "scan"}

    result = query_mod.write_query(payload, query_file=query_path)

    saved = json.loads(query_path.read_text())
    assert saved["command"] == "scan"
    assert "config_error" in saved
    assert "invalid config" in saved["config_error"]
    assert result.ok is True


def test_write_query_truncates_oversized_payload(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(query_mod, "QUERY_PAYLOAD_MAX_BYTES", 1200)
    monkeypatch.setattr(query_mod, "QUERY_ITEMS_SOFT_LIMIT", 5)
    monkeypatch.setattr(query_mod, "load_config", lambda: {})
    monkeypatch.setattr(query_mod, "config_for_query", lambda _cfg: {"source": "test"})

    query_path = tmp_path / "query.json"
    payload = {
        "command": "next",
        "queue": {"total": 500},
        "items": [
            {
                "id": f"security::src/f{i}.py::b101",
                "kind": "issue",
                "summary": "x" * 1200,
                "detail": {"blob": "y" * 1200},
            }
            for i in range(50)
        ],
        "narrative": {"hint": "z" * 5000},
    }

    result = query_mod.write_query(payload, query_file=query_path)

    saved = json.loads(query_path.read_text())
    stderr = capsys.readouterr().err

    assert result.ok is True
    assert "query_truncated" in saved
    assert saved["query_truncated"]["max_bytes"] == 1200
    assert saved["query_truncated"]["actual_bytes"] <= 1200
    assert "minimal" in saved["query_truncated"]["applied"]
    assert saved["config"]["source"] == "test"
    assert "payload exceeded budget" in stderr


def test_restore_files_best_effort_collects_failures():
    snapshots = {"a.txt": "A", "b.txt": "B"}
    restored: list[tuple[str, str]] = []

    def _write(path: str, content: str) -> None:
        if path == "b.txt":
            raise OSError("disk full")
        restored.append((path, content))

    failed = fallbacks_mod.restore_files_best_effort(snapshots, _write)
    assert restored == [("a.txt", "A")]
    assert failed == ["b.txt"]


def test_log_best_effort_failure_debugs(caplog):
    logger = logging.getLogger("desloppify.tests.core_direct")

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        fallbacks_mod.log_best_effort_failure(
            logger, "read cache", OSError("no access")
        )

    assert "Best-effort fallback failed while trying to read cache" in caplog.text


def test_warn_best_effort_uses_warning_style(monkeypatch, capsys):
    styles: list[str] = []
    monkeypatch.setattr(
        fallbacks_mod,
        "colorize",
        lambda text, style: styles.append(style) or text,
    )

    fallbacks_mod.warn_best_effort("partial fallback path in use")

    assert styles == ["yellow"]
    assert "WARNING: partial fallback path in use" in capsys.readouterr().err
