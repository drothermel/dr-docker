"""Container cleanup utilities for Docker subprocess execution."""

import re
import subprocess
from pathlib import Path

from .cidfile import is_private_cidfile_dir

_CID_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.IGNORECASE)


def _is_valid_container_id(identifier: str) -> bool:
    return _CID_PATTERN.fullmatch(identifier) is not None


def _docker_rm(identifier: str) -> None:
    try:
        subprocess.run(
            ["docker", "rm", "-f", identifier],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (
        FileNotFoundError,
        OSError,
        subprocess.SubprocessError,
    ):
        return


def cleanup_container_from_cidfile(cidfile: Path) -> None:
    """Remove the container referenced by cidfile, then clean up the file."""
    try:
        cid = cidfile.read_text(encoding="utf-8").strip()
    except OSError:
        cid = ""
    if cid and _is_valid_container_id(cid):
        _docker_rm(cid)
    cidfile.unlink(missing_ok=True)
    parent_dir = cidfile.parent
    if is_private_cidfile_dir(parent_dir):
        try:
            parent_dir.rmdir()
        except OSError:
            pass
