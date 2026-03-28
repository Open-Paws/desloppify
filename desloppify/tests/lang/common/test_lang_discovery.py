"""Focused tests for language discovery state handling."""

from __future__ import annotations

import importlib

import pytest

import desloppify.base.registry as core_registry_mod
import desloppify.engine._scoring.policy.core as scoring_policy_mod
import desloppify.languages._framework.registry.discovery as discovery_mod
import desloppify.languages._framework.registry.state as registry_state
from desloppify.languages._framework.registry.discovery import load_all, raise_load_errors


def test_raise_load_errors_includes_module_name_and_exception_type(monkeypatch):
    monkeypatch.setattr(registry_state._STATE, "load_errors", {".dummy": ImportError("boom")})

    with pytest.raises(ImportError, match=r"\.dummy: ImportError: boom"):
        raise_load_errors()


def test_raise_load_errors_noop_when_no_errors(monkeypatch):
    monkeypatch.setattr(registry_state._STATE, "load_errors", {})
    raise_load_errors()
    assert registry_state.get_load_errors() == {}


def test_load_all_uses_plugin_file_naming_convention(monkeypatch, tmp_path):
    plugin_file = tmp_path / "plugin_rust.py"
    helper_file = tmp_path / "policy.py"
    plugin_file.write_text("# plugin placeholder\n")
    helper_file.write_text("# helper placeholder\n")

    imported: list[str] = []

    def fake_import_module(name, package=None):
        imported.append(name)
        return object()

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.setattr(discovery_mod, "__file__", str(tmp_path / "discovery.py"))
    registry_state.set_load_attempted(False)
    registry_state.set_load_errors({})

    load_all()
    assert ".plugin_rust" in imported
    assert ".policy" not in imported
    assert registry_state.was_load_attempted() is True
    assert registry_state.get_load_errors() == {}
    assert len(imported) == 1


def test_load_all_retries_when_prior_attempt_left_empty_registry(monkeypatch, tmp_path):
    plugin_file = tmp_path / "plugin_retry.py"
    plugin_file.write_text("# plugin placeholder\n")

    imported: list[str] = []

    def fake_import_module(name, package=None):
        imported.append(name)
        return object()

    saved_registry = dict(registry_state.all_items())
    saved_attempted = registry_state.was_load_attempted()
    saved_errors = dict(registry_state.get_load_errors())

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.setattr(discovery_mod, "__file__", str(tmp_path / "discovery.py"))

    try:
        registry_state.clear()
        registry_state.set_load_attempted(True)
        registry_state.set_load_errors({".stale": RuntimeError("old")})

        load_all()
        assert ".plugin_retry" in imported
        assert registry_state.was_load_attempted() is True
        assert registry_state.get_load_errors() == {}
    finally:
        registry_state.clear()
        for name, cfg in saved_registry.items():
            registry_state.register(name, cfg)
        registry_state.set_load_attempted(saved_attempted)
        registry_state.set_load_errors(saved_errors)


def test_load_all_calls_module_register_entrypoint(monkeypatch, tmp_path):
    pkg_dir = tmp_path / "python"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("# package placeholder\n")

    imported: list[str] = []
    registered: list[str] = []

    class _Module:
        def __init__(self, name: str) -> None:
            self._name = name

        def register(self) -> None:
            registered.append(self._name)

    def fake_import_module(name, package=None):
        imported.append(name)
        return _Module(name)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.setattr(discovery_mod, "__file__", str(tmp_path / "discovery.py"))
    registry_state.set_load_attempted(False)
    registry_state.set_load_errors({})

    load_all()
    assert ".python" in imported
    assert ".python" in registered


def test_load_all_force_reload_reimports_without_reset_side_effects(monkeypatch, tmp_path):
    plugin_file = tmp_path / "plugin_go.py"
    plugin_file.write_text("# plugin placeholder\n")

    imported: list[str] = []

    def fake_import_module(name, package=None):
        imported.append(name)
        return object()

    reset_calls: list[str] = []

    # Snapshot registry so we can restore after force_reload clears it.
    saved_registry = dict(registry_state.all_items())

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.setattr(discovery_mod, "__file__", str(tmp_path / "discovery.py"))
    monkeypatch.setattr(
        core_registry_mod,
        "reset_registered_detectors",
        lambda: reset_calls.append("detectors"),
    )
    monkeypatch.setattr(
        scoring_policy_mod,
        "reset_registered_scoring_policies",
        lambda: reset_calls.append("scoring"),
    )
    registry_state.set_load_attempted(True)
    registry_state.set_load_errors({".stale": RuntimeError("old")})

    try:
        load_all(force_reload=True)

        # force_reload should only clear/reload language discovery state;
        # registry resets are now explicit at call sites.
        assert reset_calls == []
        assert ".plugin_go" in imported
        assert registry_state.was_load_attempted() is True
        assert registry_state.get_load_errors() == {}
    finally:
        # Restore registry contents cleared by force_reload.
        for name, cfg in saved_registry.items():
            if not registry_state.is_registered(name):
                registry_state.register(name, cfg)


def test_discovery_module_exports_expected_callables():
    assert callable(discovery_mod.load_all)
    assert callable(discovery_mod.reload_all)
    assert callable(discovery_mod.raise_load_errors)
    assert isinstance(registry_state.get_load_errors(), dict)
    assert isinstance(registry_state.was_load_attempted(), bool)


def test_user_plugins_trusted_only_swallows_config_load_failures(monkeypatch):
    monkeypatch.delenv("DESLOPPIFY_TRUST_PLUGINS", raising=False)

    assert (
        discovery_mod._user_plugins_trusted(
            load_config_fn=lambda: (_ for _ in ()).throw(ValueError("bad config"))
        )
        is False
    )

    with pytest.raises(RuntimeError, match="boom"):
        discovery_mod._user_plugins_trusted(
            load_config_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )


def test_load_all_propagates_unexpected_user_plugin_errors(monkeypatch, tmp_path):
    plugins_dir = tmp_path / ".desloppify" / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "local_plugin.py").write_text("x = 1\n")

    monkeypatch.setattr(discovery_mod, "__file__", str(tmp_path / "discovery.py"))
    monkeypatch.setattr(discovery_mod, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(discovery_mod, "_user_plugins_trusted", lambda: (_ for _ in ()).throw(RuntimeError("plugin gate crash")))

    registry_state.set_load_attempted(False)
    registry_state.set_load_errors({})
    with pytest.raises(RuntimeError, match="plugin gate crash"):
        load_all()


def test_reset_runtime_state_clears_registry_and_hooks():
    saved_registry = {name: registry_state.get(name) for name in registry_state.all_keys()}
    saved_attempted = registry_state.was_load_attempted()
    saved_errors = dict(registry_state.get_load_errors())

    registry_state.register("python", object())
    registry_state.register_hook("python", "test_coverage", object())

    discovery_mod.reset_runtime_state()

    assert registry_state.all_keys() == []
    assert registry_state.get_hook("python", "test_coverage") is None

    # Restore original state so subsequent tests find all languages registered.
    for name, cfg in saved_registry.items():
        registry_state.register(name, cfg)
    registry_state.set_load_attempted(saved_attempted)
    registry_state.set_load_errors(saved_errors)
