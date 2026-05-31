"""Verify the layered package structure imports cleanly and respects boundaries.

Failures here usually mean either a stub file was deleted or someone broke the
dependency rule (UI -> core -> domain; infra is a leaf).
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "healthsh"

# Packages that must exist after issue #2.
EXPECTED_PACKAGES = [
    "healthsh",
    "healthsh.domain",
    "healthsh.core",
    "healthsh.services",
    "healthsh.infra",
    "healthsh.infra.collectors",
    "healthsh.infra.threads",
    "healthsh.infra.db",
    "healthsh.ui",
    "healthsh.ui.theme",
    "healthsh.ui.widgets",
    "healthsh.ui.screens",
]


def test_all_expected_packages_import() -> None:
    """Every layer must import cleanly so stubs and __init__.py files are valid."""
    for name in EXPECTED_PACKAGES:
        importlib.import_module(name)


def test_every_module_in_package_imports() -> None:
    """Walk the healthsh package and ensure every submodule imports without error."""
    package = importlib.import_module("healthsh")
    failed: list[tuple[str, str]] = []
    for module_info in pkgutil.walk_packages(package.__path__, prefix="healthsh."):
        try:
            importlib.import_module(module_info.name)
        except Exception as exc:  # noqa: BLE001 — surface every failure
            failed.append((module_info.name, repr(exc)))
    assert not failed, f"Modules failed to import: {failed}"


def _imports_in(path: Path) -> set[str]:
    """Return the top-level dotted names imported by a single python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _layer_paths(layer: str) -> list[Path]:
    return sorted((PACKAGE_ROOT / layer).rglob("*.py"))


def test_domain_does_not_import_outward() -> None:
    """``healthsh.domain`` must not depend on ``core``, ``services``, ``infra``, or ``ui``."""
    forbidden = ("healthsh.core", "healthsh.services", "healthsh.infra", "healthsh.ui")
    offenders: list[tuple[str, str]] = []
    for file in _layer_paths("domain"):
        for imp in _imports_in(file):
            if any(imp == f or imp.startswith(f + ".") for f in forbidden):
                offenders.append((str(file.relative_to(PACKAGE_ROOT.parent)), imp))
    assert not offenders, f"domain layer must not import outward: {offenders}"


def test_core_only_imports_domain_from_project() -> None:
    """``healthsh.core`` may import only from ``healthsh.domain`` within the project."""
    forbidden = ("healthsh.services", "healthsh.infra", "healthsh.ui")
    offenders: list[tuple[str, str]] = []
    for file in _layer_paths("core"):
        for imp in _imports_in(file):
            if any(imp == f or imp.startswith(f + ".") for f in forbidden):
                offenders.append((str(file.relative_to(PACKAGE_ROOT.parent)), imp))
    assert not offenders, f"core layer must depend only on domain: {offenders}"


def test_infra_does_not_import_ui() -> None:
    """``healthsh.infra`` is a leaf relative to ``ui`` — it must not reach into the UI layer."""
    offenders: list[tuple[str, str]] = []
    for file in _layer_paths("infra"):
        for imp in _imports_in(file):
            if imp == "healthsh.ui" or imp.startswith("healthsh.ui."):
                offenders.append((str(file.relative_to(PACKAGE_ROOT.parent)), imp))
    assert not offenders, f"infra layer must not import ui: {offenders}"
