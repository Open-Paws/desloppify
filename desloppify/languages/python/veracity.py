"""Python veracity (de-hallucination) plugin."""

from __future__ import annotations

import ast
import importlib.util
import re
from typing import Any

from desloppify.intelligence.veracity import VeracityIssue, VeracityPlugin


class PythonVeracityPlugin(VeracityPlugin):
    """Verifies Python code blocks for hallucinated APIs."""

    def verify_suggestion(
        self,
        suggestion: str,
        *,
        project_root: str | None = None,
    ) -> list[VeracityIssue]:
        """Extract Python code blocks and verify method calls."""
        issues: list[VeracityIssue] = []
        code_blocks = self._extract_python_blocks(suggestion)

        for block in code_blocks:
            try:
                tree = ast.parse(block)
                issues.extend(self._check_tree(tree, block))
            except SyntaxError:
                # If the AI suggested invalid syntax, that's already slop,
                # but we'll focus on de-hallucination here.
                continue

        return issues

    def _extract_python_blocks(self, text: str) -> list[str]:
        """Extract code from ```python ... ``` blocks."""
        return re.findall(r"```python\s+(.*?)```", text, re.DOTALL)

    def _check_tree(self, tree: ast.AST, block: str) -> list[VeracityIssue]:
        """Inspect AST for potentially hallucinated calls."""
        issues: list[VeracityIssue] = []
        
        # Simple visitor to find attribute accesses
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                issue = self._verify_attribute_call(node, block)
                if issue:
                    issues.append(issue)
        
        return issues

    def _verify_attribute_call(self, node: ast.Attribute, block: str) -> VeracityIssue | None:
        """Check if an attribute exists on its base (if base is a known module)."""
        # Resolve the full module/object path (e.g. 'os.path')
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        
        if not isinstance(curr, ast.Name):
            return None
        
        base_name = curr.id
        # parts is [method, submodule], so reverse it and join
        attr_name = parts[0]
        submodules = parts[1:][::-1]
        
        module_path = ".".join([base_name] + submodules)

        # Check if it's a likely stdlib or installed module
        spec = importlib.util.find_spec(base_name)
        if not spec:
            return None

        try:
            # Safer than full import: just check if it's a common slop target
            if base_name in {"os", "sys", "pathlib", "json", "hashlib", "re"}:
                module = importlib.import_module(module_path)
                if not hasattr(module, attr_name):
                    return {
                        "method": attr_name,
                        "module": module_path,
                        "message": f"Hallucinated API detected: '{module_path}.{attr_name}' does not exist.",
                        "code_block": block
                    }
        except Exception:
            pass

        return None
