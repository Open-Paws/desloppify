"""Support helpers for C# dependency graph detection and CLI output."""

from __future__ import annotations

import argparse
import json
import logging
import re
import defusedxml.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from desloppify.base.discovery.file_paths import (

    rel,

    resolve_path,

)
from desloppify.base.output.terminal import colorize, print_table
from desloppify.engine.detectors.graph import (
    detect_cycles,
    finalize_graph,
    get_coupling_score,
)
from desloppify.languages.csharp.extractors import CSHARP_FILE_EXCLUSIONS

logger = logging.getLogger(__name__)

_USING_RE = re.compile(
    r"(?m)^\s*(?:global\s+)?using\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;"
)
_USING_ALIAS_RE = re.compile(
    r"(?m)^\s*(?:global\s+)?using\s+[A-Za-z_]\w*\s*=\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;"
)
_USING_STATIC_RE = re.compile(
    r"(?m)^\s*(?:global\s+)?using\s+static\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*;"
)
_NAMESPACE_RE = re.compile(
    r"(?m)^\s*namespace\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?:;|\{)"
)
_MAIN_METHOD_RE = re.compile(r"(?m)\bstatic\s+(?:async\s+)?(?:void|int)\s+Main\s*\(")
_MAUI_APP_FACTORY_RE = re.compile(r"(?m)\bCreateMauiApp\s*\(")
_PLATFORM_BASE_RE = re.compile(
    r"(?m)^\s*(?:public\s+)?(?:partial\s+)?class\s+\w+\s*:\s*"
    r".*\b(?:MauiUIApplicationDelegate|UIApplicationDelegate|UISceneDelegate|MauiWinUIApplication)\b"
)
_PLATFORM_REGISTER_RE = re.compile(r'(?m)\[Register\("AppDelegate"\)\]')

_ENTRY_FILE_HINTS = {
    "Program.cs",
    "Startup.cs",
    "Main.cs",
    "MauiProgram.cs",
    "MainActivity.cs",
    "AppDelegate.cs",
    "SceneDelegate.cs",
    "WinUIApplication.cs",
    "App.xaml.cs",
}
_ENTRY_PATH_HINTS = (
    "/Platforms/Android/",
    "/Platforms/iOS/",
    "/Platforms/MacCatalyst/",
    "/Platforms/Windows/",
)

_PROJECT_EXCLUSIONS = set(CSHARP_FILE_EXCLUSIONS) | {".git"}


def is_excluded_path(path: Path) -> bool:
    """True when path is under a known excluded directory."""
    return any(part in _PROJECT_EXCLUSIONS for part in path.parts)


def find_csproj_files(path: Path) -> list[Path]:
    """Find .csproj files under path, excluding build artifact directories."""
    found: list[Path] = []
    for candidate in path.rglob("*.csproj"):
        if is_excluded_path(candidate):
            continue
        found.append(candidate.resolve())
    return sorted(found)


def parse_csproj_references(csproj_file: Path) -> tuple[set[Path], str | None]:
    """Parse ProjectReference includes and optional RootNamespace."""
    refs: set[Path] = set()
    root_ns: str | None = None
    try:
        root = ET.parse(csproj_file).getroot()
    except (ET.ParseError, OSError):
        return refs, root_ns

    for elem in root.iter():
        tag = elem.tag.split("}", 1)[-1]
        if tag == "ProjectReference":
            include = elem.attrib.get("Include")
            if include:
                include_path = include.replace("\\", "/")
                refs.add((csproj_file.parent / include_path).resolve())
        elif tag == "RootNamespace":
            if elem.text and elem.text.strip():
                root_ns = elem.text.strip()
    return refs, root_ns


def resolve_project_ref_path(raw_ref: str, base_dirs: tuple[Path, ...]) -> Path | None:
    """Resolve a .csproj path against a list of base directories."""
    ref = (raw_ref or "").strip().strip('"').replace("\\", "/")
    if not ref or not ref.lower().endswith(".csproj"):
        return None

    ref_path = Path(ref)
    if ref_path.is_absolute():
        try:
            return ref_path.resolve()
        except OSError as exc:
            logger.debug(
                "Skipping unresolved absolute project reference %s: %s",
                ref_path,
                exc,
            )
            return None

    fallback: Path | None = None
    for base_dir in base_dirs:
        try:
            candidate = (base_dir / ref_path).resolve()
        except OSError as exc:
            logger.debug(
                "Skipping unresolved project reference %s under %s: %s",
                ref_path,
                base_dir,
                exc,
            )
            continue
        if candidate.exists():
            return candidate
        if fallback is None:
            fallback = candidate
    return fallback


def parse_project_assets_references(csproj_file: Path) -> set[Path]:
    """Parse project refs from obj/project.assets.json, if available."""
    assets_file = csproj_file.parent / "obj" / "project.assets.json"
    if not assets_file.exists():
        return set()
    try:
        payload = json.loads(assets_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, dict):
        return set()

    refs: set[Path] = set()
    base_dirs = (csproj_file.parent, assets_file.parent)

    libraries = payload.get("libraries")
    if isinstance(libraries, dict):
        for lib_meta in libraries.values():
            if not isinstance(lib_meta, dict):
                continue
            if str(lib_meta.get("type", "")).lower() != "project":
                continue
            for key in ("path", "msbuildProject"):
                raw_ref = lib_meta.get(key)
                if not isinstance(raw_ref, str):
                    continue
                resolved = resolve_project_ref_path(raw_ref, base_dirs)
                if resolved is not None:
                    refs.add(resolved)

    dep_groups = payload.get("projectFileDependencyGroups")
    if isinstance(dep_groups, dict):
        for deps in dep_groups.values():
            if not isinstance(deps, list):
                continue
            for dep in deps:
                if not isinstance(dep, str):
                    continue
                dep_token = dep.split(maxsplit=1)[0]
                resolved = resolve_project_ref_path(dep_token, base_dirs)
                if resolved is not None:
                    refs.add(resolved)

    refs.discard(csproj_file.resolve())
    return refs


def map_file_to_project(cs_files: list[str], projects: list[Path]) -> dict[str, Path]:
    """Assign each source file to the nearest containing .csproj directory."""
    project_dirs = sorted(
        (project.parent for project in projects),
        key=lambda directory: len(directory.parts),
        reverse=True,
    )
    mapping: dict[str, Path] = {}
    for filepath in cs_files:
        abs_file = Path(resolve_path(filepath))
        for proj_dir in project_dirs:
            try:
                abs_file.relative_to(proj_dir)
            except ValueError as exc:
                logger.debug(
                    "File %s is not under project directory %s: %s",
                    abs_file,
                    proj_dir,
                    exc,
                )
                continue
            match = next((project for project in projects if project.parent == proj_dir), None)
            if match is not None:
                mapping[str(abs_file)] = match
                break
    return mapping


def is_entrypoint_file(filepath: Path, content: str) -> bool:
    """Best-effort bootstrap detection for app delegates and platform entry files."""
    rel_path = rel(str(filepath)).replace("\\", "/")
    if filepath.name in _ENTRY_FILE_HINTS:
        return True
    is_platform_path = any(hint in rel_path for hint in _ENTRY_PATH_HINTS)
    if is_platform_path and (
        _PLATFORM_BASE_RE.search(content) or _PLATFORM_REGISTER_RE.search(content)
    ):
        return True
    if _MAIN_METHOD_RE.search(content):
        return True
    if _MAUI_APP_FACTORY_RE.search(content):
        return True
    if _PLATFORM_BASE_RE.search(content):
        return True
    if _PLATFORM_REGISTER_RE.search(content):
        return True
    return False


def parse_file_metadata(filepath: str) -> tuple[str | None, set[str], bool]:
    """Return (namespace, using_namespaces, is_entrypoint) for one C# file."""
    abs_path = Path(resolve_path(filepath))
    try:
        content = abs_path.read_text()
    except (OSError, UnicodeDecodeError):
        return None, set(), False

    namespace = None
    ns_match = _NAMESPACE_RE.search(content)
    if ns_match:
        namespace = ns_match.group(1)

    usings: set[str] = set()
    usings.update(_USING_RE.findall(content))
    usings.update(_USING_ALIAS_RE.findall(content))
    usings.update(_USING_STATIC_RE.findall(content))
    return namespace, usings, is_entrypoint_file(abs_path, content)


def expand_namespace_matches(
    using_ns: str,
    namespace_to_files: dict[str, set[str]],
) -> set[str]:
    """Resolve one using namespace to candidate target files."""
    out: set[str] = set()
    for namespace, files in namespace_to_files.items():
        if namespace == using_ns or namespace.startswith(using_ns + ".") or using_ns.startswith(namespace + "."):
            out.update(files)
    return out


def safe_resolve_graph_path(raw_path: str) -> str:
    try:
        return resolve_path(raw_path)
    except OSError:
        return raw_path


def build_graph_from_edge_map(edge_map: dict[str, set[str]]) -> dict[str, dict]:
    graph: dict[str, dict] = defaultdict(lambda: {"imports": set(), "importers": set()})
    for source, imports in edge_map.items():
        graph[source]
        for target in imports:
            if target == source:
                continue
            graph[source]["imports"].add(target)
            graph[target]["importers"].add(source)
    return finalize_graph(dict(graph))


def render_deps_for_graph(args: argparse.Namespace, *, graph: dict[str, dict]) -> None:
    """Show dependency info for a specific C# file or top coupled files."""
    if getattr(args, "file", None):
        coupling = get_coupling_score(args.file, graph)
        if getattr(args, "json", False):
            print(json.dumps({"file": rel(args.file), **coupling}, indent=2))
            return
        print(colorize(f"\nDependency info: {rel(args.file)}\n", "bold"))
        print(f"  Fan-in (importers):  {coupling['fan_in']}")
        print(f"  Fan-out (imports):   {coupling['fan_out']}")
        print(f"  Instability:         {coupling['instability']}")
        return

    by_importers = sorted(
        graph.items(),
        key=lambda item: (-item[1].get("importer_count", 0), rel(item[0])),
    )
    if getattr(args, "json", False):
        top = by_importers[: getattr(args, "top", 20)]
        print(
            json.dumps(
                {
                    "files": len(graph),
                    "entries": [
                        {
                            "file": rel(filepath),
                            "importers": entry.get("importer_count", 0),
                            "imports": entry.get("import_count", 0),
                        }
                        for filepath, entry in top
                    ],
                },
                indent=2,
            )
        )
        return

    print(colorize(f"\nC# dependency graph: {len(graph)} files\n", "bold"))
    rows = [
        [rel(filepath), str(entry.get("importer_count", 0)), str(entry.get("import_count", 0))]
        for filepath, entry in by_importers[: getattr(args, "top", 20)]
    ]
    if rows:
        print_table(["File", "Importers", "Imports"], rows, [70, 9, 7])


def render_cycles_for_graph(args: argparse.Namespace, *, graph: dict[str, dict]) -> None:
    """Show import cycles in C# source files."""
    cycles, _ = detect_cycles(graph)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "count": len(cycles),
                    "cycles": [
                        {"length": cycle["length"], "files": [rel(path) for path in cycle["files"]]}
                        for cycle in cycles
                    ],
                },
                indent=2,
            )
        )
        return

    if not cycles:
        print(colorize("No import cycles found.", "green"))
        return

    print(colorize(f"\nImport cycles: {len(cycles)}\n", "bold"))
    for cycle in cycles[: getattr(args, "top", 20)]:
        files = [rel(path) for path in cycle["files"]]
        print(
            f"  [{cycle['length']} files] {' -> '.join(files[:6])}"
            + (f" -> +{len(files) - 6}" if len(files) > 6 else "")
        )


__all__ = [
    "build_graph_from_edge_map",
    "render_cycles_for_graph",
    "render_deps_for_graph",
    "expand_namespace_matches",
    "find_csproj_files",
    "is_entrypoint_file",
    "map_file_to_project",
    "parse_csproj_references",
    "parse_file_metadata",
    "parse_project_assets_references",
    "resolve_project_ref_path",
    "safe_resolve_graph_path",
]
