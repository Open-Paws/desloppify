"""Direct coverage smoke tests for remaining plan/review/scan/go split modules."""

from __future__ import annotations

import desloppify.app.commands.exclude as exclude_cmd_mod
import desloppify.app.commands.plan.shared.cluster_membership as plan_cluster_membership_mod
import desloppify.app.commands.plan.shared.patterns as plan_resolve_mod
import desloppify.app.commands.plan.cluster.dispatch as plan_cluster_handlers_mod
import desloppify.app.commands.plan.cmd as plan_cmd_mod
import desloppify.app.commands.plan.queue_render as plan_queue_render_mod
import desloppify.app.commands.plan.reorder_handlers as plan_reorder_handlers_mod
import desloppify.app.commands.resolve.apply as resolve_apply_mod
import desloppify.app.commands.resolve.cmd as resolve_cmd_mod
import desloppify.app.commands.helpers.attestation as attestation_mod
import desloppify.app.commands.resolve.selection as resolve_selection_mod
import desloppify.app.commands.review.assessment_integrity as assessment_integrity_mod
import desloppify.app.commands.review.batch.prompt_template as batch_prompt_template_mod
import desloppify.app.commands.review.merge as review_merge_mod
import desloppify.app.commands.scan.coverage as scan_coverage_mod
import desloppify.app.commands.scan.orchestrator as scan_orchestrator_mod
import desloppify.app.commands.scan.reporting.text as scan_reporting_text_mod
import desloppify.app.commands.scan.wontfix as scan_wontfix_mod
import desloppify.base.coercions as coercions_api_mod
import desloppify.base.enums as enums_mod
import desloppify.base.search.query_paths as query_paths_mod
import desloppify.engine.planning.scorecard_policy as scorecard_policy_mod
import desloppify.engine._plan.triage.core as planning_triage_mod
import desloppify.languages._framework.scaffold_move as scaffold_move_mod
import desloppify.languages.go.commands as go_commands_mod
import desloppify.languages.go.detectors.deps as go_deps_mod
import desloppify.languages.go.move as go_move_mod
import desloppify.languages.go.phases as go_phases_mod
import desloppify.languages.go.review as go_review_mod


def test_direct_coverage_scan_plan_go_modules_smoke():
    assert callable(review_merge_mod.do_merge)
    assert callable(exclude_cmd_mod.cmd_exclude)
    assert callable(plan_cluster_membership_mod.cluster_issue_ids)
    assert callable(plan_resolve_mod.resolve_ids_from_patterns)
    assert callable(plan_cluster_handlers_mod.cmd_cluster_dispatch)
    assert callable(plan_cmd_mod.cmd_plan)
    assert callable(plan_reorder_handlers_mod.cmd_plan_reorder)
    assert callable(plan_queue_render_mod.cmd_plan_queue)
    assert callable(assessment_integrity_mod.bind_scorecard_subjective_at_target)
    assert callable(batch_prompt_template_mod.render_batch_prompt)
    assert callable(scan_coverage_mod.persist_scan_coverage)
    assert callable(scan_orchestrator_mod.ScanOrchestrator)
    assert callable(scan_reporting_text_mod.build_workflow_guide)
    assert callable(scan_wontfix_mod.augment_with_stale_wontfix_issues)
    assert callable(coercions_api_mod.coerce_positive_int)
    assert callable(enums_mod.canonical_issue_status)
    assert callable(query_paths_mod.query_file_path)
    assert callable(scorecard_policy_mod._compose_scorecard_dimensions)
    assert callable(planning_triage_mod.collect_triage_input)
    assert callable(scaffold_move_mod.find_replacements)
    assert callable(go_commands_mod.get_detect_commands)
    assert callable(go_deps_mod.build_dep_graph)
    assert callable(go_move_mod.find_replacements)
    assert callable(go_phases_mod.phase_structural)
    assert callable(go_review_mod.api_surface)
    assert callable(resolve_apply_mod._resolve_all_patterns)
    assert callable(resolve_cmd_mod.cmd_resolve)
    assert callable(resolve_selection_mod._validate_resolve_inputs)
    assert callable(attestation_mod.validate_attestation)
