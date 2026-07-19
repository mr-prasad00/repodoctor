"""Generate and validate the one pytest reproduction test for a bug claim."""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Mapping


def generate_test(extracted: Mapping[str, Any]) -> str:
    """Return one minimal pytest test that asserts the claim's expected result."""
    function = extracted.get("function")
    inputs = extracted.get("inputs")
    expected = extracted.get("expected")

    if not isinstance(function, str) or not function.isidentifier():
        raise ValueError("Cannot generate a test: extracted function must be a valid function name.")
    if not isinstance(inputs, list):
        raise ValueError("Cannot generate a test: extracted inputs must be a list.")
    if expected is None:
        raise ValueError("Cannot generate a test: extracted expected value is required.")

    module_name = _find_module_for_function(function)
    arguments = ", ".join(repr(value) for value in inputs)

    # Check if expected is an exception
    is_exception = False
    exception_name = ""
    if isinstance(expected, str):
        cleaned_exp = expected.strip()
        if cleaned_exp in ("ValueError", "TypeError", "KeyError", "IndexError", "ZeroDivisionError", "Exception"):
            is_exception = True
            exception_name = cleaned_exp

    if is_exception:
        source = (
            f"import pytest\n"
            f"from {module_name} import {function}\n\n\n"
            f"def test_repro():\n"
            f"    with pytest.raises({exception_name}):\n"
            f"        {function}({arguments})\n"
        )
    else:
        source = (
            f"from {module_name} import {function}\n\n\n"
            f"def test_repro():\n"
            f"    assert {function}({arguments}) == {expected!r}\n"
        )

    validate_test_source(source)
    return source


def _find_module_for_function(function_name: str) -> str:
    """Scan files in target_repo/ to locate which module defines function_name."""
    fallback = "target_repo.billing"

    cur_dir = Path(__file__).resolve().parent
    target_repo_dir = cur_dir / "target_repo"
    if not target_repo_dir.exists():
        target_repo_dir = cur_dir.parent / "target_repo"
    if not target_repo_dir.exists():
        return fallback

    for file_path in target_repo_dir.glob("*.py"):
        if file_path.name == "__init__.py":
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    return f"target_repo.{file_path.stem}"
        except Exception:
            pass

    return fallback


def validate_test_source(test_source: str) -> None:
    """Reject test source that is not one valid target_repo pytest test."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError as error:
        raise ValueError(f"Generated test is not valid Python: {error.msg}.") from error

    if not _imports_target_repo(tree):
        raise ValueError("Generated test must import from target_repo.")

    test_functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]
    if len(test_functions) != 1:
        raise ValueError("Generated test must define exactly one test_* function.")


def _imports_target_repo(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "target_repo" or (node.module or "").startswith("target_repo."):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name == "target_repo" or alias.name.startswith("target_repo.") for alias in node.names):
                return True
    return False
