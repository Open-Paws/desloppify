"""Split late-stage holistic review tests: dimensions, remediation, and structure."""

from __future__ import annotations

from desloppify.engine._scoring.policy.core import HOLISTIC_POTENTIAL
from desloppify.intelligence.review import (
    DIMENSION_PROMPTS,
    DIMENSIONS,
    build_holistic_context,
    generate_remediation_plan,
)
from desloppify.intelligence.review._prepare.helpers import (
    HOLISTIC_WORKFLOW as _HOLISTIC_WORKFLOW,
)
from desloppify.intelligence.review.prepare_batches_builders import (
    build_investigation_batches as _build_investigation_batches,
)
from desloppify.state import empty_state
from desloppify.tests.review.context.test_holistic_review import (
    _call_import_holistic_issues,
    _call_prepare_holistic_review,
    _make_file,
    _mock_lang,
)
# ===================================================================
# prepare_holistic_review: workflow and batches in output
# ===================================================================


class TestPrepareHolisticReviewEnriched:
    def test_workflow_field_present(self, tmp_path):
        f1 = _make_file(str(tmp_path), "module.py", lines=50)
        lang = _mock_lang([f1])
        state = empty_state()

        data = _call_prepare_holistic_review(tmp_path, lang, state, files=[f1])

        assert "workflow" in data
        assert isinstance(data["workflow"], list)
        assert len(data["workflow"]) == len(_HOLISTIC_WORKFLOW)
        assert "query.json" in data["workflow"][0]

    def test_investigation_batches_field_present(self, tmp_path):
        f1 = _make_file(str(tmp_path), "module.py", lines=50)
        lang = _mock_lang([f1])
        state = empty_state()

        data = _call_prepare_holistic_review(tmp_path, lang, state, files=[f1])

        assert "investigation_batches" in data
        assert isinstance(data["investigation_batches"], list)

    def test_full_codebase_sweep_not_present(self, tmp_path):
        f1 = _make_file(str(tmp_path), "module_a.py", lines=50)
        f2 = _make_file(str(tmp_path), "module_b.py", lines=50)
        lang = _mock_lang([f1, f2])
        state = empty_state()

        data = _call_prepare_holistic_review(tmp_path, lang, state, files=[f1, f2])

        full_sweep_batches = [
            b
            for b in data["investigation_batches"]
            if b["name"] == "Full Codebase Sweep"
        ]
        assert len(full_sweep_batches) == 0


# ===================================================================
# convention_outlier prompt update
# ===================================================================


class TestConventionOutlierPrompt:
    def test_sibling_behavior_in_look_for(self):
        prompt = DIMENSION_PROMPTS["convention_outlier"]
        look_for = " ".join(prompt["look_for"])
        assert "Sibling modules" in look_for
        assert "behavioral protocols" in look_for


# ===================================================================
# generate_remediation_plan
# ===================================================================


def _state_with_holistic_issues(*issues_args):
    """Create a state with holistic issues for plan testing."""
    state = empty_state()
    state["potentials"] = {"python": {"review": HOLISTIC_POTENTIAL}}
    state["objective_score"] = 45.0
    state["strict_score"] = 38.0
    for fid, conf, dim, summary in issues_args:
        state["work_items"][fid] = {
            "id": fid,
            "file": ".",
            "status": "open",
            "detector": "review",
            "confidence": conf,
            "detail": {
                "holistic": True,
                "dimension": dim,
                "related_files": ["src/a.py", "src/b.py"],
                "evidence": ["evidence line 1"],
                "suggestion": "do the thing",
                "reasoning": "because reasons",
            },
            "summary": summary,
        }
    return state


class TestGenerateRemediationPlan:
    def test_basic_plan_content(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "God module found",
            ),
        )

        plan = generate_remediation_plan(state, "python")

        assert "# Holistic Review: Remediation Plan" in plan
        assert "God module found" in plan
        assert "cross module architecture" in plan
        assert "45.0/100" in plan
        assert "resolve fixed" in plan

    def test_priority_ordering_by_weight(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::test::low1",
                "low",
                "test_strategy",
                "Low impact thing",
            ),
            (
                "review::.::holistic::arch::high1",
                "high",
                "cross_module_architecture",
                "High impact thing",
            ),
        )

        plan = generate_remediation_plan(state, "python")

        # High confidence should come first (Priority 1)
        high_pos = plan.index("High impact thing")
        low_pos = plan.index("Low impact thing")
        assert high_pos < low_pos

    def test_score_impact_shown(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Test issue",
            ),
        )

        plan = generate_remediation_plan(state, "python")

        # Should show estimated impact in pts
        assert "pts" in plan

    def test_resolve_command_included(self):
        fid = "review::.::holistic::arch::abc123"
        state = _state_with_holistic_issues(
            (fid, "high", "cross_module_architecture", "Issue X"),
        )

        plan = generate_remediation_plan(state, "python")

        assert f'resolve fixed "{fid}"' in plan

    def test_related_files_shown(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Issue",
            ),
        )

        plan = generate_remediation_plan(state, "python")

        assert "`src/a.py`" in plan
        assert "`src/b.py`" in plan

    def test_re_evaluate_section(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Issue",
            ),
        )

        plan = generate_remediation_plan(state, "python")

        assert "Re-evaluate" in plan
        assert "review --prepare" in plan
        assert "auto-resolve" in plan

    def test_how_to_use_section(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Issue",
            ),
        )

        plan = generate_remediation_plan(state, "python")

        assert "How to use this plan" in plan
        assert "priority order" in plan

    def test_empty_issues_returns_clean_plan(self):
        state = empty_state()
        state["objective_score"] = 95.0

        plan = generate_remediation_plan(state, "python")

        assert "No open holistic issues" in plan
        assert "95.0/100" in plan

    def test_resolved_issues_excluded(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Open one",
            ),
        )
        # Add a resolved issue that should NOT appear
        state["work_items"]["review::.::holistic::test::def"] = {
            "id": "review::.::holistic::test::def",
            "file": ".",
            "status": "fixed",
            "detector": "review",
            "confidence": "high",
            "detail": {"holistic": True, "dimension": "test_strategy"},
            "summary": "Resolved issue",
        }

        plan = generate_remediation_plan(state, "python")

        assert "Open one" in plan
        assert "Resolved issue" not in plan

    def test_writes_to_file(self, tmp_path):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Issue",
            ),
        )
        output = tmp_path / "plan.md"

        plan = generate_remediation_plan(state, "python", output_path=output)

        assert output.exists()
        assert output.read_text() == plan
        assert "Issue" in output.read_text()

    def test_lang_name_in_commands(self):
        state = _state_with_holistic_issues(
            (
                "review::.::holistic::arch::abc",
                "high",
                "cross_module_architecture",
                "Issue",
            ),
        )

        plan = generate_remediation_plan(state, "typescript")

        assert "--lang typescript" in plan


# ===================================================================
# New dimensions: authorization, ai_debt, migration (#57)
# ===================================================================


class TestNewHolisticDimensions:
    def test_authorization_consistency_prompt(self):
        assert "authorization_consistency" in DIMENSION_PROMPTS
        prompt = DIMENSION_PROMPTS["authorization_consistency"]
        assert "description" in prompt
        assert "look_for" in prompt
        assert "skip" in prompt

    def test_ai_generated_debt_prompt(self):
        assert "ai_generated_debt" in DIMENSION_PROMPTS
        prompt = DIMENSION_PROMPTS["ai_generated_debt"]
        assert "description" in prompt
        assert len(prompt["look_for"]) >= 3

    def test_incomplete_migration_prompt(self):
        assert "incomplete_migration" in DIMENSION_PROMPTS
        prompt = DIMENSION_PROMPTS["incomplete_migration"]
        assert "description" in prompt
        assert len(prompt["look_for"]) >= 3

    def test_new_dimensions_in_holistic_list(self):
        assert "authorization_consistency" in DIMENSIONS
        assert "ai_generated_debt" in DIMENSIONS
        assert "incomplete_migration" in DIMENSIONS

    def test_import_accepts_new_holistic_dimensions(self):
        state = empty_state()
        data = [
            {
                "dimension": "authorization_consistency",
                "identifier": "auth_gap",
                "summary": "Auth middleware missing on admin routes",
                "confidence": "high",
                "related_files": ["src/routes/admin.ts"],
                "evidence": ["Admin route tree bypasses auth middleware."],
                "suggestion": "Add auth middleware to admin routes",
            },
            {
                "dimension": "ai_generated_debt",
                "identifier": "ai_comments",
                "summary": "Restating comments across 12 files",
                "confidence": "medium",
                "related_files": ["src/services/a.ts", "src/services/b.ts"],
                "evidence": ["Comments repeat code behavior without additional intent."],
                "suggestion": "Remove restating comments",
            },
            {
                "dimension": "incomplete_migration",
                "identifier": "mixed_api",
                "summary": "Old axios + new fetch coexist in services/",
                "confidence": "high",
                "related_files": ["src/services/http.ts", "src/services/users.ts"],
                "evidence": ["Codebase mixes legacy axios wrappers and fetch helpers."],
                "suggestion": "Consolidate to fetch",
            },
        ]
        diff = _call_import_holistic_issues(data, state, "typescript")
        assert diff["new"] == 3

    def test_cross_module_prompt_includes_contract_drift_signal(self):
        look_for = DIMENSION_PROMPTS["cross_module_architecture"]["look_for"]
        joined = " ".join(look_for)
        assert "contracts drifting" in joined
        assert "Compatibility shim paths" in joined

    def test_high_level_prompt_includes_docs_runtime_alignment(self):
        look_for = DIMENSION_PROMPTS["high_level_elegance"]["look_for"]
        joined = " ".join(look_for)
        assert "reference docs match runtime reality" in joined


# ===================================================================
# New investigation batches: Authorization and AI Debt & Migrations
# ===================================================================


class TestNewInvestigationBatches:
    def test_authorization_batch_generated(self):
        """Batch for authorization_consistency appears in the dimension list."""
        ctx = {
            "architecture": {},
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {},
            "authorization": {
                "route_auth_coverage": {
                    "routes/admin.py": {
                        "handlers": 5,
                        "with_auth": 2,
                        "without_auth": 3,
                    },
                },
                "service_role_usage": ["lib/supabase.ts"],
            },
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        names = [b["name"] for b in batches]
        assert "authorization_consistency" in names
        auth_batch = next(b for b in batches if b["name"] == "authorization_consistency")
        assert "authorization_consistency" in auth_batch["dimensions"]
        assert "files_to_read" not in auth_batch

    def test_ai_debt_migration_batch_generated(self):
        """Batch for ai_generated_debt appears in the dimension list."""
        ctx = {
            "architecture": {},
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {},
            "ai_debt_signals": {
                "file_signals": {"bloated.py": {"comment_ratio": 0.5}},
            },
            "migration_signals": {
                "deprecated_markers": {
                    "total": 3,
                    "files": {"old_api.py": 2, "legacy.py": 1},
                },
                "migration_todos": [
                    {"file": "service.py", "text": "TODO: remove after migration"},
                ],
            },
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        names = [b["name"] for b in batches]
        assert "ai_generated_debt" in names
        debt_batch = next(b for b in batches if b["name"] == "ai_generated_debt")
        assert "ai_generated_debt" in debt_batch["dimensions"]
        assert "files_to_read" not in debt_batch

    def test_authorization_batch_always_present(self):
        """Authorization batch is always present (one batch per dimension)."""
        ctx = {
            "architecture": {},
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {},
            "authorization": {
                "route_auth_coverage": {
                    "routes/admin.py": {
                        "handlers": 5,
                        "with_auth": 5,
                        "without_auth": 0,
                    },
                },
            },
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        names = [b["name"] for b in batches]
        assert "authorization_consistency" in names

    def test_ai_debt_batch_always_present(self):
        """AI Debt batch is always present (one batch per dimension)."""
        ctx = {
            "architecture": {},
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {},
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        names = [b["name"] for b in batches]
        assert "ai_generated_debt" in names

    def test_one_batch_per_dimension(self):
        """With full context, one batch per dimension."""
        ctx = {
            "architecture": {
                "god_modules": [{"file": "core.py", "importers": 10, "excerpt": ""}],
            },
            "coupling": {
                "module_level_io": [
                    {"file": "init.py", "line": 5, "code": "open('f')"}
                ],
            },
            "conventions": {
                "sibling_behavior": {
                    "commands/": {
                        "shared_patterns": {
                            "compute_narrative": {"count": 6, "total": 7}
                        },
                        "outliers": [
                            {"file": "cmd.py", "missing": ["compute_narrative"]}
                        ],
                    }
                },
            },
            "errors": {
                "strategy_by_directory": {
                    "src/": {"try_catch": 5, "throws": 3, "returns_null": 2}
                }
            },
            "abstractions": {
                "util_files": [{"file": "utils.py", "loc": 200, "excerpt": ""}]
            },
            "dependencies": {
                "existing_cycles": 1,
                "cycle_summaries": ["cycle in graph.py"],
            },
            "testing": {"critical_untested": [{"file": "scoring.py", "importers": 8}]},
            "api_surface": {"sync_async_mix": ["api.py"]},
            "authorization": {
                "route_auth_coverage": {
                    "routes/admin.py": {
                        "handlers": 5,
                        "with_auth": 2,
                        "without_auth": 3,
                    },
                },
            },
            "ai_debt_signals": {
                "file_signals": {"bloated.py": {"comment_ratio": 0.5}},
            },
            "migration_signals": {
                "deprecated_markers": {"total": 1, "files": {"old.py": 1}},
            },
            "structure": {
                "root_files": [
                    {
                        "file": "viz.py",
                        "loc": 200,
                        "fan_in": 1,
                        "fan_out": 3,
                        "role": "peripheral",
                    },
                ],
                "directory_profiles": {
                    "commands/": {
                        "file_count": 8,
                        "files": ["scan.py", "show.py", "next.py"],
                        "total_loc": 1500,
                        "avg_fan_in": 2.0,
                        "avg_fan_out": 5.0,
                    },
                },
            },
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        # Each dimension with seed files gets its own batch
        names = [b["name"] for b in batches]
        # Each batch has exactly one dimension
        for batch in batches:
            assert len(batch["dimensions"]) == 1
            assert batch["name"] == batch["dimensions"][0]
        # Key dimensions should be present
        assert "cross_module_architecture" in names
        assert "convention_outlier" in names
        assert "abstraction_fitness" in names
        assert "test_strategy" in names
        assert "authorization_consistency" in names
        assert "ai_generated_debt" in names
        assert "package_organization" in names

    def test_each_batch_has_single_dimension(self):
        """Every batch has exactly one dimension matching its name."""
        ctx = {
            "architecture": {
                "god_modules": [{"file": "core.py", "importers": 10, "excerpt": "..."}],
            },
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {},
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        for batch in batches:
            assert len(batch["dimensions"]) == 1
            assert batch["name"] == batch["dimensions"][0]


# ===================================================================
# Structure context (section 12) — directory profiles, root files
# ===================================================================


class TestStructureContext:
    def test_structure_section_present(self, tmp_path):
        f1 = _make_file(str(tmp_path), "src/module_a.py", lines=50)
        f2 = _make_file(str(tmp_path), "src/module_b.py", lines=50)
        lang = _mock_lang([f1, f2])
        state = empty_state()

        ctx = build_holistic_context(tmp_path, lang, state, files=[f1, f2])

        assert "structure" in ctx
        structure = ctx["structure"]
        assert "directory_profiles" in structure

    def test_directory_profiles_computed(self, tmp_path):
        f1 = _make_file(str(tmp_path), "commands/scan.py", lines=100)
        f2 = _make_file(str(tmp_path), "commands/show.py", lines=80)
        f3 = _make_file(str(tmp_path), "commands/next.py", lines=60)
        files = [f1, f2, f3]
        lang = _mock_lang(files)
        state = empty_state()

        ctx = build_holistic_context(tmp_path, lang, state, files=files)

        profiles = ctx["structure"]["directory_profiles"]
        # Should have a profile for the commands directory
        matching = [k for k in profiles if "commands" in k]
        assert len(matching) >= 1
        profile = profiles[matching[0]]
        assert profile["file_count"] == 3
        assert profile["total_loc"] == 240  # 100+80+60

    def test_root_files_classified(self, tmp_path, monkeypatch):
        """Root-level files are classified as core (fan_in>=5) or peripheral."""
        from desloppify.base.discovery.source import (
            clear_source_file_cache_for_tests,
        )
        from desloppify.base.runtime_state import current_runtime_context

        monkeypatch.setattr(current_runtime_context(), "project_root", tmp_path)
        clear_source_file_cache_for_tests()

        f1 = _make_file(str(tmp_path), "utils.py", lines=200)
        f2 = _make_file(str(tmp_path), "scorecard.py", lines=100)
        files = [f1, f2]
        lang = _mock_lang(files)
        # Make utils.py a god module, scorecard.py peripheral
        lang.dep_graph = {
            f1: {"importers": {f"mod_{i}" for i in range(10)}, "imports": set()},
            f2: {"importers": {"scan.py"}, "imports": set()},
        }
        state = empty_state()

        ctx = build_holistic_context(tmp_path, lang, state, files=files)

        root_files = ctx["structure"].get("root_files", [])
        assert len(root_files) == 2
        # utils.py should be core (10 importers), scorecard.py peripheral (1 importer)
        utils_entry = [rf for rf in root_files if "utils" in rf["file"]]
        scorecard_entry = [rf for rf in root_files if "scorecard" in rf["file"]]
        assert utils_entry[0]["role"] == "core"
        assert scorecard_entry[0]["role"] == "peripheral"

    def test_empty_files_returns_empty_structure(self, tmp_path):
        lang = _mock_lang([])
        state = empty_state()

        ctx = build_holistic_context(tmp_path, lang, state, files=[])

        assert ctx["structure"]["directory_profiles"] == {}


# ===================================================================
# Package Organization dimension
# ===================================================================


class TestPackageOrganizationDimension:
    def test_dimension_in_holistic_list(self):
        assert "package_organization" in DIMENSIONS

    def test_dimension_has_prompt(self):
        assert "package_organization" in DIMENSION_PROMPTS
        prompt = DIMENSION_PROMPTS["package_organization"]
        assert "description" in prompt
        assert "look_for" in prompt
        assert "skip" in prompt
        assert len(prompt["look_for"]) >= 4

    def test_import_accepts_package_organization(self):
        state = empty_state()
        data = [
            {
                "dimension": "package_organization",
                "identifier": "straggler_files",
                "summary": "3 viz files at root should be in output/ subpackage",
                "confidence": "high",
                "related_files": ["visualize.py", "scorecard.py", "_scorecard_draw.py"],
                "evidence": ["Visualization modules sit at root with unrelated concerns."],
                "suggestion": "Move viz files into output/ subpackage",
            }
        ]
        diff = _call_import_holistic_issues(data, state, "python")
        assert diff["new"] == 1

    def test_investigation_batch_generated(self):
        """Package Organization batch is always present (one batch per dimension)."""
        ctx = {
            "architecture": {},
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {
                "root_files": [
                    {
                        "file": "visualize.py",
                        "loc": 300,
                        "fan_in": 1,
                        "fan_out": 3,
                        "role": "peripheral",
                    },
                ],
                "directory_profiles": {},
            },
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        names = [b["name"] for b in batches]
        assert "package_organization" in names
        pkg_batch = next(b for b in batches if b["name"] == "package_organization")
        assert "package_organization" in pkg_batch["dimensions"]
        assert "files_to_read" not in pkg_batch

    def test_batch_present_even_without_structure(self):
        """Package Organization batch present even when structure context is empty."""
        ctx = {
            "architecture": {},
            "coupling": {},
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {"util_files": []},
            "dependencies": {},
            "testing": {},
            "api_surface": {},
            "structure": {},
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        names = [b["name"] for b in batches]
        assert "package_organization" in names

    def test_mid_level_elegance_batch_present(self):
        ctx = {
            "architecture": {},
            "coupling": {
                "boundary_violations": [{"file": "app/orchestrator.py"}],
                "module_level_io": [{"file": "app/handlers.py"}],
            },
            "conventions": {},
            "errors": {"strategy_by_directory": {}},
            "abstractions": {
                "util_files": [],
                "pass_through_wrappers": [{"file": "app/facade.py"}],
                "one_impl_interfaces": [
                    {"declared_in": ["app/protocols.py"], "implemented_in": []}
                ],
            },
            "dependencies": {},
            "testing": {},
            "api_surface": {"sync_async_mix": ["app/api.py"]},
            "ai_debt_signals": {},
            "migration_signals": {},
            "structure": {},
        }
        lang = _mock_lang()

        batches = _build_investigation_batches(ctx, lang)

        mid_batch = next(b for b in batches if b["name"] == "mid_level_elegance")
        assert mid_batch["dimensions"] == ["mid_level_elegance"]
        assert "files_to_read" not in mid_batch
