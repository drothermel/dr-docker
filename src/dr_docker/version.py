"""Version constants for dr_docker."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re


def _version_from_pyproject() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"(?P<version>[^"]+)"\s*$', content)
    if match is None:
        raise RuntimeError(f"Unable to determine package version from {pyproject}")
    return match.group("version")


def _resolve_version() -> str:
    try:
        return version("dr-docker")
    except PackageNotFoundError:
        return _version_from_pyproject()


__version__ = _resolve_version()
CONTRACT_VERSION = __version__
