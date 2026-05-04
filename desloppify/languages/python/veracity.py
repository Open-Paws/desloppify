"""Python veracity (de-hallucination) plugin."""

from __future__ import annotations

import ast
import importlib.util
import re
from typing import Any

from desloppify.intelligence.review.veracity import VeracityIssue, VeracityPlugin


class PythonVeracityPlugin(VeracityPlugin):
    """Verifies Python code blocks for hallucinated APIs."""

    # Common stdlib modules that are safe to import and often hallucinated
    SAFE_MODULES = {
        "os", "sys", "pathlib", "json", "hashlib", "re", "math", "collections",
        "datetime", "shutil", "subprocess", "tempfile", "urllib", "base64",
        "csv", "enum", "functools", "itertools", "logging", "random", "time",
        "typing", "uuid", "abc", "argparse", "glob", "inspect", "io", "pickle",
        "shlex", "socket", "struct", "threading", "traceback", "types"
    }

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
        
        # 1. Track imports
        import_map: dict[str, str] = {}  # alias -> full_module_path
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    import_map[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for alias in node.names:
                        name = alias.asname or alias.name
                        import_map[name] = f"{node.module}.{alias.name}"

        # 2. Find and verify attribute accesses
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                issue = self._verify_attribute_call(node, block, import_map)
                if issue:
                    issues.append(issue)
        
        return issues

    def _verify_attribute_call(
        self, 
        node: ast.Attribute, 
        block: str, 
        import_map: dict[str, str]
    ) -> VeracityIssue | None:
        """Check if an attribute exists on its base (if base is a known module)."""
        # Resolve the full module/object path
        parts = []
        curr = node
        while isinstance(curr, ast.Attribute):
            parts.append(curr.attr)
            curr = curr.value
        
        if not isinstance(curr, ast.Name):
            return None
        
        base_name = curr.id
        # parts is [method, submodule...], reverse it
        attr_name = parts[0]
        submodules = parts[1:][::-1]
        
        # Start with the imported name
        resolved_module = import_map.get(base_name, base_name)
        module_path = ".".join([resolved_module] + submodules)

        # Check if it's a likely stdlib or installed module
        root_package = module_path.split(".")[0]
        spec = importlib.util.find_spec(root_package)
        if not spec:
            return None

        try:
            # We check if it's in our safe list OR if it's already in sys.modules
            # (which means it's already loaded in this environment)
            import sys
            if root_package in self.SAFE_MODULES or root_package in sys.modules:
                # Try to import the specific module path
                try:
                    module = importlib.import_module(module_path)
                    if not hasattr(module, attr_name):
                        return {
                            "method": attr_name,
                            "module": module_path,
                            "message": f"Hallucinated API detected: '{module_path}.{attr_name}' does not exist.",
                            "code_block": block
                        }
                except ImportError:
                    # If we can't import the submodule, it might be a method call 
                    # on an object, which we don't handle well yet.
                    # e.g. os.path.join().exists()
                    # In that case, we try to import the parent and see if it has the attribute.
                    parent_path = ".".join(module_path.split(".")[:-1])
                    if parent_path:
                        try:
                            parent_module = importlib.import_module(parent_path)
                            actual_attr = module_path.split(".")[-1]
                            if hasattr(parent_module, actual_attr):
                                # The 'module_path' was actually parent.attr
                                obj = getattr(parent_module, actual_attr)
                                if not hasattr(obj, attr_name):
                                     return {
                                        "method": attr_name,
                                        "module": module_path,
                                        "message": f"Hallucinated API detected: '{module_path}.{attr_name}' does not exist.",
                                        "code_block": block
                                    }
                        except Exception:
                            pass
        except Exception:
            pass

        return None
