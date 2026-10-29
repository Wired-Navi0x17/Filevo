"""Codebase Examination Module for Document Generator.

Provides AST parsing, dependency mapping, pattern detection, and complexity
measurement for Python codebases. All outputs are structured for consumption
by the RL probabilistic model.
"""

import ast
import json
import math
import os
from collections import defaultdict
from pathlib import Path


# Directories to exclude from traversal
EXCLUDED_DIRS = frozenset({
    ".git", ".venv", ".cache", ".tox", ".mypy_cache", ".pytest_cache",
    "node_modules", "__pycache__", ".build", ".eggs", "dist", "build",
    "venv", "env", ".env", ".nox",
})


class CodebaseAnalyzer:
    """Examines a Python codebase and extracts structured insights.

    Fixes applied over prior version:
    - ClassDef uses node.body (not node.methods which doesn't exist)
    - AsyncFunctionDef is handled alongside FunctionDef
    - Directory exclusion list prevents scanning .venv, .git, etc.
    - self.complexity is actually populated per-function
    - self.patterns is populated via structural pattern detection
    """

    def __init__(self, path: str | None = None):
        self.path = Path(path) if path else Path.cwd()
        self.tree: ast.Module | None = None
        self.files_analyzed: int = 0
        self.files_failed: int = 0
        self.functions: dict = defaultdict(dict)
        self.classes: dict = defaultdict(dict)
        self.imports: dict = defaultdict(set)
        self.complexity: dict = defaultdict(list)   # file -> [complexity values]
        self.patterns: dict = defaultdict(int)      # pattern_name -> count

    def analyze(self) -> dict:
        """Run full codebase analysis and return structured insights."""
        insights = {
            "files": [],
            "functions": {},
            "classes": {},
            "imports": {},
            "complexity": {},
            "patterns": {},
        }

        for root, dirs, files in os.walk(self.path):
            # Exclude virtual envs, caches, and dependency directories
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            for fname in files:
                if fname.endswith(".py"):
                    fpath = Path(root) / fname
                    try:
                        result = self._analyze_file(fpath)
                        insights["files"].append(
                            {"path": str(fpath), "success": True, **result}
                        )
                        self.files_analyzed += 1
                    except Exception as e:
                        insights["files"].append(
                            {"path": str(fpath), "success": False, "error": str(e)}
                        )
                        self.files_failed += 1

        # Aggregate function data
        for fpath, funcs in self.functions.items():
            for func_name, fdata in funcs.items():
                key = f"{fpath}::{func_name}"
                insights["functions"][key] = {
                    "name": fdata.get("name", "unknown"),
                    "complexity": fdata.get("complexity", 1),
                    "docstring": fdata.get("docstring", ""),
                    "args": fdata.get("args", []),
                    "is_async": fdata.get("is_async", False),
                    "line": fdata.get("line", 0),
                }

        # Aggregate class data
        for fpath, classes in self.classes.items():
            for class_name, cdata in classes.items():
                key = f"{fpath}::{class_name}"
                insights["classes"][key] = {
                    "name": cdata.get("name", class_name),
                    "methods": cdata.get("methods", []),
                    "bases": cdata.get("bases", []),
                    "line": cdata.get("line", 0),
                }

        # Aggregate import data
        for imp_path, imp_set in self.imports.items():
            insights["imports"][imp_path] = {
                "modules": sorted(list(imp_set)),
            }

        # Aggregate complexity data
        for cpath, values in self.complexity.items():
            if values:
                insights["complexity"][cpath] = {
                    "values": values,
                    "average": sum(values) / len(values),
                    "max": max(values),
                    "min": min(values),
                }

        # Pattern detection results
        for pattern, count in self.patterns.items():
            insights["patterns"][pattern] = {
                "count": count,
                "density": round(count / max(self.files_analyzed, 1), 3),
            }

        return insights

    def _analyze_file(self, fpath: Path) -> dict:
        """Analyze a single Python file and return extracted data."""
        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()

        try:
            tree = ast.parse(source, filename=str(fpath))
        except SyntaxError as e:
            return {"errors": [str(e)], "imports": [], "functions": [], "classes": []}

        self.tree = tree
        results = {"imports": [], "functions": [], "classes": []}
        str_fpath = str(fpath)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports.setdefault(str_fpath, set()).add(alias.name)
                    results["imports"].append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self.imports.setdefault(str_fpath, set()).add(node.module)
                    results["imports"].append(node.module)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = self._compute_complexity(node)
                func_data = {
                    "name": node.name,
                    "complexity": cc,
                    "docstring": ast.get_docstring(node) or "",
                    "line": node.lineno,
                    "args": [a.arg for a in node.args.args],
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }
                self.functions[str_fpath][node.name] = func_data
                results["functions"].append(func_data)
                # Populate complexity tracking
                self.complexity[str_fpath].append(cc)

            elif isinstance(node, ast.ClassDef):
                # Extract methods from class body (not node.methods!)
                methods = []
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(child.name)

                # Extract base classes
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(ast.dump(base))

                self.classes[str_fpath][node.name] = {
                    "name": node.name,
                    "methods": methods,
                    "bases": bases,
                    "line": node.lineno,
                }
                results["classes"].append({"name": node.name, "methods": methods})

                # Pattern detection
                if len(methods) == 0:
                    self.patterns["empty_class"] += 1
                if "__init__" in methods and "__enter__" in methods and "__exit__" in methods:
                    self.patterns["context_manager"] += 1
                if any(m.startswith("test_") for m in methods):
                    self.patterns["test_class"] += 1
                if len(bases) > 0:
                    self.patterns["inheritance"] += 1
                if "__init__" in methods:
                    self.patterns["initialized_class"] += 1

        # File-level pattern detection
        has_decorators = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.decorator_list
            for node in ast.walk(tree)
        )
        if has_decorators:
            self.patterns["decorated_functions"] += 1

        return results

    @staticmethod
    def _compute_complexity(node: ast.AST) -> int:
        """Compute cyclomatic complexity for a function/method."""
        complexity = 1  # base complexity
        for child in ast.walk(node):
            if isinstance(
                child,
                (ast.If, ast.While, ast.For, ast.Try, ast.ExceptHandler,
                 ast.BoolOp, ast.Assert),
            ):
                complexity += 1
            # Count boolean operators (and/or add decision points)
            if isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def get_insights(self) -> dict:
        """Return aggregated insights suitable for model consumption."""
        insights = self.analyze()
        total = max(self.files_analyzed, 1)

        # Compute global complexity stats
        all_complexities = []
        for values in self.complexity.values():
            all_complexities.extend(values)

        avg_complexity = sum(all_complexities) / max(len(all_complexities), 1)
        max_complexity = max(all_complexities) if all_complexities else 0

        return {
            "file_count": self.files_analyzed,
            "files_failed": self.files_failed,
            "function_count": sum(len(v) for v in self.functions.values()),
            "class_count": sum(len(v) for v in self.classes.values()),
            "avg_complexity": round(avg_complexity, 2),
            "max_complexity": max_complexity,
            "pattern_count": sum(self.patterns.values()),
            "insights": insights,
        }

    def get_state_vector(self) -> list[float]:
        """Extract a normalized state vector for RL model consumption.

        Returns an 8-dimensional feature vector:
          s[0]: log10(1 + file_count)   — scale
          s[1]: func_to_class_ratio     — structure indicator
          s[2]: avg_complexity / 10     — normalized complexity
          s[3]: max_complexity / 20     — peak complexity
          s[4]: docstring_ratio         — documentation density
          s[5]: import_density          — dependency coupling
          s[6]: pattern_density         — structural patterns per file
          s[7]: 1.0                     — bias term
        """
        func_count = sum(len(v) for v in self.functions.values())
        class_count = sum(len(v) for v in self.classes.values())
        total_files = max(self.files_analyzed, 1)

        all_complexities = []
        for values in self.complexity.values():
            all_complexities.extend(values)
        avg_c = sum(all_complexities) / max(len(all_complexities), 1)
        max_c = max(all_complexities) if all_complexities else 0

        # Docstring ratio
        documented = 0
        total_symbols = 0
        for funcs in self.functions.values():
            for fdata in funcs.values():
                total_symbols += 1
                if fdata.get("docstring"):
                    documented += 1
        doc_ratio = documented / max(total_symbols, 1)

        # Import density
        total_imports = sum(len(v) for v in self.imports.values())
        import_density = total_imports / total_files

        # Pattern density
        pattern_total = sum(self.patterns.values())
        pattern_density = pattern_total / total_files

        return [
            min(math.log10(1 + total_files), 4.0) / 4.0,  # [0, 1]
            min(func_count / max(class_count, 1), 10.0) / 10.0,  # [0, 1]
            min(avg_c / 10.0, 1.0),  # [0, 1]
            min(max_c / 20.0, 1.0),  # [0, 1]
            min(doc_ratio, 1.0),  # [0, 1]
            min(import_density / 10.0, 1.0),  # [0, 1]
            min(pattern_density / 5.0, 1.0),  # [0, 1]
            1.0,  # bias
        ]