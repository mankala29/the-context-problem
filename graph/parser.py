"""
AST-based Python file parser.

Extracts:
  - Module docstring (used as the document summary)
  - Internal import dependencies (used to build the graph edges)
  - Class and function names (used to enrich the document representation)
"""

import ast
import os


def parse_file(file_path: str, base_dir: str) -> dict:
    """
    Parse a Python file and return a structured summary.

    Returns:
        doc_id        : relative path from base_dir
        docstring     : module-level docstring (or empty string)
        classes       : list of class names defined in the file
        functions     : list of top-level function names
        imports       : list of internal module paths this file depends on
    """
    rel_path = os.path.relpath(file_path, base_dir)
    try:
        with open(file_path) as f:
            source = f.read()
        tree = ast.parse(source)
    except Exception as e:
        return {"doc_id": rel_path, "docstring": "", "classes": [],
                "functions": [], "imports": [], "error": str(e)}

    docstring = ast.get_docstring(tree) or ""
    classes   = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    imports   = _extract_internal_imports(tree, base_dir)

    return {
        "doc_id":    rel_path,
        "docstring": docstring[:300],   # cap at 300 chars
        "classes":   classes,
        "functions": functions,
        "imports":   imports,
    }


def _extract_internal_imports(tree: ast.Module, base_dir: str) -> list:
    """Return relative paths of internal modules this file imports from."""
    deps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts    = node.module.split(".")
            candidate = os.path.join(base_dir, *parts) + ".py"
            if os.path.exists(candidate):
                deps.append(os.path.relpath(candidate, base_dir))
    return deps


def collect_python_files(base_dir: str, exclude: list = None) -> list:
    """Return absolute paths of all .py files under base_dir."""
    exclude = exclude or []
    files   = []
    for root, dirs, fnames in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in {".venv", "__pycache__", ".git"}]
        for fname in fnames:
            if fname.endswith(".py") and fname not in exclude:
                files.append(os.path.join(root, fname))
    return sorted(files)
