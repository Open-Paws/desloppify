"""Detect web frontend frameworks in a project.

Used by persona QA to determine when browser-based testing is relevant
and to tailor default persona scenarios to the detected framework.
"""

from __future__ import annotations

import json
from pathlib import Path


def detect_web_frontend(scan_path: Path) -> dict | None:
    """Detect whether the project contains a web frontend.

    Returns a dict with framework info, or None if no frontend detected.
    """
    pkg_path = scan_path / "package.json"
    if pkg_path.exists():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            pkg = {}

        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }

        framework_map = {
            "next": "Next.js",
            "react": "React",
            "vue": "Vue",
            "@angular/core": "Angular",
            "svelte": "Svelte",
            "nuxt": "Nuxt",
            "gatsby": "Gatsby",
            "astro": "Astro",
            "remix": "Remix",
            "@solidjs/start": "SolidStart",
        }

        for dep_name, framework_label in framework_map.items():
            if dep_name in all_deps:
                return {
                    "framework": framework_label,
                    "entry": "package.json",
                    "dep": dep_name,
                }

    # Check for HTML files as a fallback
    html_files = list(scan_path.glob("**/*.html"))
    # Exclude node_modules, dist, etc.
    html_files = [
        f
        for f in html_files
        if not any(
            part in f.parts
            for part in ("node_modules", "dist", ".next", "build", "vendor")
        )
    ]
    if len(html_files) >= 3:
        return {"framework": "Static HTML", "entry": "*.html", "dep": None}

    return None
