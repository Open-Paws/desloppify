"""Support helpers for C# dependency graph detection and CLI output.

Compatibility facade that re-exports focused support helpers.
"""

from __future__ import annotations

from .deps_support_metadata import (
    expand_namespace_matches,
    is_entrypoint_file,
    parse_file_metadata,
)
from .deps_support_projects import (
    find_csproj_files,
    map_file_to_project,
    parse_csproj_references,
    parse_project_assets_references,
    resolve_project_ref_path,
)
from .deps_support_render import (
    build_graph_from_edge_map,
    render_cycles_for_graph,
    render_deps_for_graph,
    safe_resolve_graph_path,
)

__all__ = [
    "build_graph_from_edge_map",
    "expand_namespace_matches",
    "find_csproj_files",
    "is_entrypoint_file",
    "map_file_to_project",
    "parse_csproj_references",
    "parse_file_metadata",
    "parse_project_assets_references",
    "render_cycles_for_graph",
    "render_deps_for_graph",
    "resolve_project_ref_path",
    "safe_resolve_graph_path",
]
