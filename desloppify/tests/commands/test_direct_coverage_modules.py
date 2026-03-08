"""Direct coverage smoke tests for modules often covered only transitively."""

from __future__ import annotations

import desloppify.app.cli_support.parser as cli_parser
import desloppify.app.cli_support.parser_groups as cli_parser_groups
import desloppify.app.commands.config as config_cmd
import desloppify.app.commands.move.cmd as move_cmd_mod
import desloppify.app.commands.move.directory as move_directory
import desloppify.app.commands.move.reporting as move_reporting
import desloppify.app.commands.next.output as next_output
import desloppify.app.commands.next.render_support as next_render_support
import desloppify.app.commands.plan.cmd as plan_cmd_mod
import desloppify.app.commands.registry as cmd_registry
from desloppify.app.commands.review.batch import merge as review_batch_merge
import desloppify.app.commands.review.batch.execution as review_batches
import desloppify.app.commands.review.importing.cmd as review_import
import desloppify.app.commands.review.importing.helpers as review_import_helpers
import desloppify.app.commands.review.prepare as review_prepare
import desloppify.app.commands.review.runner_process as review_runner_helpers
import desloppify.app.commands.review.runtime.setup as review_runtime_setup
import desloppify.app.commands.scan.artifacts as scan_artifacts
import desloppify.app.commands.scan.cmd as scan_cmd_mod
import desloppify.app.commands.scan.reporting.presentation as scan_reporting_presentation
import desloppify.app.commands.scan.reporting.subjective as scan_reporting_subjective
import desloppify.app.commands.scan.workflow as scan_workflow
import desloppify.app.commands.status.cmd as status_cmd_mod
import desloppify.app.commands.status.render as status_render
import desloppify.app.commands.status.summary as status_summary
import desloppify.app.output._viz_cmd_context as viz_cmd_context
import desloppify.app.output.scorecard_parts.draw as scorecard_draw
import desloppify.app.output.scorecard_parts.left_panel as scorecard_left_panel
import desloppify.app.output.scorecard_parts.ornaments as scorecard_ornaments
import desloppify.app.output.tree_text as tree_text_mod
import desloppify.base.runtime_state as runtime_state
import desloppify.engine._state.noise as noise
import desloppify.engine._state.persistence as persistence
import desloppify.engine._state.resolution as state_resolution
import desloppify.engine.planning.helpers as plan_common
import desloppify.engine.planning.scan as plan_scan
import desloppify.engine.planning.select as plan_select
import desloppify.intelligence.integrity as subjective_review_integrity
import desloppify.intelligence.review._context.structure as review_context_structure
import desloppify.intelligence.review.dimensions.holistic as review_dimensions_holistic
import desloppify.intelligence.review.dimensions.validation as review_dimensions_validation
import desloppify.languages as lang_pkg
import desloppify.languages._framework.discovery as lang_discovery
import desloppify.languages._framework.scaffold_move as dart_move
import desloppify.languages._framework.scaffold_move as gdscript_move
import desloppify.languages.csharp.extractors as csharp_extractors
import desloppify.languages.csharp.extractors_classes as csharp_extractors_classes
import desloppify.languages.dart.commands as dart_commands
import desloppify.languages.dart.extractors as dart_extractors
import desloppify.languages.dart.phases as dart_phases
import desloppify.languages.dart.review as dart_review
import desloppify.languages.gdscript.commands as gdscript_commands
import desloppify.languages.gdscript.extractors as gdscript_extractors
import desloppify.languages.gdscript.phases as gdscript_phases
import desloppify.languages.gdscript.review as gdscript_review
import desloppify.languages.python.detectors.private_imports as private_imports
import desloppify.languages.python.detectors.smells_ast._dispatch as smells_ast_dispatch
import desloppify.languages.python.detectors.smells_ast._helpers as smells_ast_shared
import desloppify.languages.python.detectors.smells_ast._source_detectors as smells_ast_source_detectors
import desloppify.languages.python.detectors.smells_ast._tree_context_detectors as smells_ast_tree_context_detectors
import desloppify.languages.python.detectors.smells_ast._tree_quality_detectors as smells_ast_tree_quality_detectors
import desloppify.languages.python.detectors.smells_ast._tree_quality_detectors_types as smells_ast_tree_quality_detectors_types
import desloppify.languages.python.detectors.smells_ast._tree_safety_detectors as smells_ast_tree_safety_detectors
import desloppify.languages.python.detectors.smells_ast._tree_safety_detectors_runtime as smells_ast_tree_safety_detectors_runtime
import desloppify.languages.python.extractors_classes as py_extractors_classes
import desloppify.languages.python.extractors_shared as py_extractors_shared
import desloppify.languages.python.phases as py_phases
import desloppify.languages.python.phases_quality as py_phases_quality
import desloppify.languages.typescript.detectors._smell_detectors_safety as ts_smell_detectors_safety
import desloppify.languages.typescript.detectors.deps_runtime as ts_deps_runtime
import desloppify.languages.typescript.extractors_components as ts_extractors_components
from desloppify.intelligence.review import prepare_batches as review_prepare_batches
from desloppify.languages import resolution as lang_resolution
from desloppify.languages.csharp import move as csharp_move
from desloppify.languages.csharp import review as csharp_review
from desloppify.languages.typescript import review as ts_review


def _assert_all_callables(*targets) -> None:
    for target in targets:
        assert callable(target)


def test_smoke_parser():
    """Parser and CLI support modules."""
    _assert_all_callables(
        cli_parser.create_parser,
        cli_parser_groups._add_scan_parser,
    )


def test_smoke_planning():
    """Planning modules: common, scan, select."""
    _assert_all_callables(
        plan_common.is_subjective_phase,
        plan_scan.generate_issues,
        plan_select.get_next_items,
        plan_select.get_next_item,
    )


def test_smoke_commands():
    """App command modules: config, plan, move, scan, next, review, status."""
    _assert_all_callables(
        config_cmd.cmd_config,
        plan_cmd_mod.cmd_plan_output,
        move_directory.run_directory_move,
        move_reporting.print_file_move_plan,
        move_reporting.print_directory_move_plan,
        move_cmd_mod.cmd_move,
        scan_cmd_mod.cmd_scan,
        scan_artifacts.build_scan_query_payload,
        scan_artifacts.emit_scorecard_badge,
        scan_workflow.prepare_scan_runtime,
        scan_workflow.run_scan_generation,
        scan_workflow.merge_scan_results,
        next_output.serialize_item,
        next_output.build_query_payload,
        next_render_support.render_queue_header,
        review_batch_merge.merge_batch_results,
        review_batches.do_run_batches,
        review_import.do_import,
        review_import_helpers.load_import_issues_data,
        review_prepare.do_prepare,
        review_runner_helpers.run_codex_batch,
        review_runtime_setup.setup_lang,
        status_cmd_mod.cmd_status,
        status_render.show_tier_progress_table,
        status_summary.score_summary_lines,
        scan_reporting_presentation.show_score_model_breakdown,
        scan_reporting_presentation.show_detector_progress,
        scan_reporting_subjective.subjective_rerun_command,
        scan_reporting_subjective.subjective_integrity_followup,
        scan_reporting_subjective.build_subjective_followup,
    )
    assert isinstance(cmd_registry.get_command_handlers(), dict)
    assert "scan" in cmd_registry.get_command_handlers()
    runtime = runtime_state.current_runtime_context()
    assert isinstance(runtime.exclusions, tuple)
    assert isinstance(runtime.source_file_cache.max_entries, int)
    runtime.cache_enabled = True
    assert runtime.cache_enabled
    runtime.cache_enabled = False


def test_smoke_engine():
    """Engine modules: state internals, python detectors."""
    # state internals
    _assert_all_callables(
        persistence.load_state,
        persistence.save_state,
        state_resolution.match_issues,
        state_resolution.resolve_issues,
        noise.resolve_issue_noise_budget,
        noise.resolve_issue_noise_global_budget,
        noise.resolve_issue_noise_settings,
    )

    # python detector modules
    _assert_all_callables(
        private_imports.detect_private_imports,
        private_imports._is_dunder,
        smells_ast_dispatch.detect_ast_smells,
        smells_ast_shared._looks_like_path_var,
        smells_ast_source_detectors.detect_duplicate_constants,
        smells_ast_source_detectors.detect_vestigial_parameter,
        smells_ast_tree_context_detectors._detect_hardcoded_path_sep,
        smells_ast_tree_quality_detectors._detect_optional_param_sprawl,
        smells_ast_tree_quality_detectors_types._detect_optional_param_sprawl,
        smells_ast_tree_safety_detectors._detect_silent_except,
        smells_ast_tree_safety_detectors_runtime._detect_silent_except,
        py_extractors_classes.extract_py_classes,
        py_extractors_shared.extract_py_params,
        py_phases_quality.phase_smells,
        py_phases_quality.phase_dict_keys,
        ts_smell_detectors_safety._detect_swallowed_errors,
        ts_deps_runtime.build_dynamic_import_targets,
        ts_extractors_components.extract_ts_components,
    )
    assert private_imports._is_dunder("__all__")
    assert isinstance(py_phases.PY_ENTRY_PATTERNS, list)
    assert isinstance(py_phases.PY_COMPLEXITY_SIGNALS, list)
    assert isinstance(py_phases.PY_GOD_RULES, list)


def test_smoke_lang_plugins():
    """Language plugin modules: package, discovery, resolution, per-lang."""
    # lang package/discovery/resolution
    _assert_all_callables(
        lang_pkg.register_lang,
        lang_pkg.available_langs,
        lang_discovery.load_all,
        lang_discovery.raise_load_errors,
        lang_resolution.make_lang_config,
        lang_resolution.get_lang,
        lang_resolution.auto_detect_lang,
        csharp_extractors.find_csharp_files,
        csharp_extractors.extract_csharp_functions,
        csharp_extractors_classes.extract_csharp_classes,
        dart_commands.get_detect_commands,
        dart_extractors.find_dart_files,
        dart_extractors.extract_functions,
        dart_review.module_patterns,
        dart_review.api_surface,
        gdscript_commands.get_detect_commands,
        gdscript_extractors.find_gdscript_files,
        gdscript_extractors.extract_functions,
        gdscript_review.module_patterns,
        gdscript_review.api_surface,
    )

    # csharp
    assert isinstance(csharp_move.VERIFY_HINT, str)
    assert "dotnet build" in csharp_move.VERIFY_HINT
    assert csharp_move.find_replacements("a.cs", "b.cs", {}) == {}
    assert csharp_move.find_self_replacements("a.cs", "b.cs", {}) == []
    assert csharp_move.filter_intra_package_importer_changes(
        "a.cs", [("a", "b")], set()
    ) == [("a", "b")]
    assert csharp_move.filter_directory_self_changes("a.cs", [("a", "b")], set()) == [
        ("a", "b")
    ]
    assert isinstance(csharp_review.module_patterns("public class A {}"), list)
    assert csharp_review.api_surface({"A.cs": "public class A {}"}) == {}

    # typescript
    assert isinstance(ts_review.module_patterns("export default function A() {}"), list)
    assert ts_review.api_surface({"a.ts": "export function f() {}"}) == {}

    # dart
    assert isinstance(dart_move.get_verify_hint(), str)
    assert dart_move.find_replacements("a.dart", "b.dart", {}) == {}
    assert dart_move.find_self_replacements("a.dart", "b.dart", {}) == []
    assert isinstance(dart_commands.get_detect_commands(), dict)
    assert isinstance(dart_phases.DART_COMPLEXITY_SIGNALS, list)
    assert callable(dart_phases.phase_structural)
    assert callable(dart_phases.phase_coupling)
    assert isinstance(dart_review.HOLISTIC_REVIEW_DIMENSIONS, list)

    # gdscript
    assert isinstance(gdscript_move.get_verify_hint(), str)
    assert gdscript_move.find_replacements("a.gd", "b.gd", {}) == {}
    assert gdscript_move.find_self_replacements("a.gd", "b.gd", {}) == []
    assert isinstance(gdscript_commands.get_detect_commands(), dict)
    assert isinstance(gdscript_phases.GDSCRIPT_COMPLEXITY_SIGNALS, list)
    assert callable(gdscript_phases.phase_structural)
    assert callable(gdscript_phases.phase_coupling)
    assert isinstance(gdscript_review.HOLISTIC_REVIEW_DIMENSIONS, list)


def test_smoke_intelligence():
    """Intelligence modules: review dimensions, context, prepare, integrity."""
    assert isinstance(review_dimensions_holistic.DIMENSIONS, list)
    assert "cross_module_architecture" in review_dimensions_holistic.DIMENSIONS
    _assert_all_callables(
        review_prepare_batches.build_investigation_batches,
        review_context_structure.compute_structure_context,
        review_dimensions_validation.parse_dimensions_payload,
        subjective_review_integrity.subjective_review_open_breakdown,
        scorecard_draw.draw_left_panel,
        scorecard_draw.draw_right_panel,
        scorecard_draw.draw_ornament,
        scorecard_left_panel.draw_left_panel,
        scorecard_ornaments.draw_ornament,
        viz_cmd_context.load_cmd_context,
        tree_text_mod._aggregate,
    )


# ---------------------------------------------------------------------------
# Behavioral tests for key functions (beyond assert callable)
# ---------------------------------------------------------------------------


def test_noise_budget_defaults():
    """resolve_issue_noise_budget returns default for None config."""
    assert noise.resolve_issue_noise_budget(None) == 10
    assert noise.resolve_issue_noise_budget({}) == 10


def test_noise_budget_from_config():
    """resolve_issue_noise_budget reads the config value."""
    assert noise.resolve_issue_noise_budget({"issue_noise_budget": 5}) == 5
    assert noise.resolve_issue_noise_budget({"issue_noise_budget": 0}) == 0


def test_noise_settings_invalid_config():
    """resolve_issue_noise_settings returns warning for invalid values."""
    per, glob, warning = noise.resolve_issue_noise_settings(
        {"issue_noise_budget": "bad"}
    )
    assert per == 10  # default
    assert warning is not None
    assert "Invalid" in warning


def test_serialize_item_minimal():
    """serialize_item extracts expected fields from a minimal item dict."""
    item = {
        "id": "smells::foo.py::1",
        "kind": "issue",
        "tier": 2,
        "confidence": "high",
        "detector": "smells",
        "file": "foo.py",
        "summary": "Unused import",
        "status": "open",
    }
    result = next_output.serialize_item(item)
    assert result["id"] == "smells::foo.py::1"
    assert result["kind"] == "issue"
    assert result["confidence"] == "high"
    assert result["detector"] == "smells"
    assert result["file"] == "foo.py"
    assert "explain" not in result
    # Non-workflow items omit blocked_by/is_blocked
    assert "blocked_by" not in result
    assert "is_blocked" not in result


def test_serialize_item_includes_blocked_by_for_workflow_stage():
    """serialize_item includes blocked_by and is_blocked for workflow_stage items."""
    item = {
        "id": "triage::reflect",
        "kind": "workflow_stage",
        "confidence": "high",
        "detector": "triage",
        "file": ".",
        "summary": "Planning: reflect",
        "status": "open",
        "blocked_by": ["triage::observe"],
        "is_blocked": True,
    }
    result = next_output.serialize_item(item)
    assert result["blocked_by"] == ["triage::observe"]
    assert result["is_blocked"] is True


def test_serialize_item_omits_blocked_by_when_empty():
    """serialize_item omits blocked_by/is_blocked when not blocked."""
    item = {
        "id": "triage::observe",
        "kind": "workflow_stage",
        "confidence": "high",
        "detector": "triage",
        "file": ".",
        "summary": "Planning: observe",
        "status": "open",
        "blocked_by": [],
        "is_blocked": False,
    }
    result = next_output.serialize_item(item)
    assert "blocked_by" not in result
    assert "is_blocked" not in result


def test_serialize_cluster_item_caps_member_payload():
    """Cluster serialization should cap nested members and strip heavy metadata."""
    sibling_ids = [f"security::src/f{i}.py::B101::{i}" for i in range(80)]
    members = [
        {
            "id": f"security::src/f{i}.py::B101::{i}",
            "kind": "issue",
            "confidence": "high",
            "detector": "security",
            "file": f"src/f{i}.py",
            "summary": "Security issue",
            "status": "open",
            "primary_command": "desloppify plan resolve ...",
            "plan_cluster": {
                "name": "auto/security",
                "sibling_ids": sibling_ids,
            },
        }
        for i in range(80)
    ]
    cluster = {
        "id": "auto/security",
        "kind": "cluster",
        "action_type": "refactor",
        "summary": "Fix security issues",
        "member_count": len(members),
        "members": members,
        "cluster_name": "auto/security",
        "cluster_auto": True,
        "detector": "security",
        "primary_command": "desloppify next --cluster auto/security --count 10",
    }

    result = next_output.serialize_item(cluster)
    assert result["kind"] == "cluster"
    assert result["member_count"] == 80
    assert len(result["members"]) == 25
    assert result["members_truncated"] is True
    assert result["members_sample_limit"] == 25
    assert "plan_cluster" not in result["members"][0]


def test_build_query_payload_structure():
    """build_query_payload returns well-formed dict with queue metadata."""
    items = [{"id": "f1", "kind": "issue", "tier": 1}]
    queue = {"tier_counts": {1: 1}, "total": 1}
    payload = next_output.build_query_payload(
        queue, items, command="next", narrative=None
    )
    assert payload["command"] == "next"
    assert len(payload["items"]) == 1
    assert payload["queue"]["total"] == 1
    assert payload["narrative"] is None


def test_private_imports_is_dunder():
    """_is_dunder correctly identifies dunder names."""
    assert private_imports._is_dunder("__all__") is True
    assert private_imports._is_dunder("__init__") is True
    assert private_imports._is_dunder("_private") is False
    assert private_imports._is_dunder("public") is False


def test_command_registry_has_core_commands():
    """get_command_handlers includes scan, status, next, plan."""
    handlers = cmd_registry.get_command_handlers()
    for cmd in ("scan", "status", "next", "plan"):
        assert cmd in handlers, f"Missing command handler: {cmd}"
        assert callable(handlers[cmd])
