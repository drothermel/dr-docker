"""Container ID file management for Docker subprocess execution."""

import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path

PRIVATE_CID_DIR_PREFIX = "dr_docker_cid_dir_"
_LOGGER = logging.getLogger(__name__)


def is_private_cidfile_dir(path: Path) -> bool:
    """Return True when path is a managed private cidfile directory."""
    temp_root = Path(tempfile.gettempdir()).resolve()
    candidate = path.resolve(strict=False)
    return candidate.parent == temp_root and candidate.name.startswith(
        PRIVATE_CID_DIR_PREFIX
    )


def new_cidfile_path(
    *,
    prefix: str = "dr_docker_cid_",
    suffix: str = ".txt",
) -> Path:
    """Return a unique cidfile path that does not already exist."""
    private_dir: Path | None = None
    try:
        private_dir = Path(tempfile.mkdtemp(prefix=PRIVATE_CID_DIR_PREFIX))
        private_dir.chmod(0o700)
    except OSError:
        _LOGGER.exception("Failed to create secure CID temporary directory")
        if private_dir is not None:
            with suppress(OSError):
                private_dir.rmdir()
        raise

    cidfile_fd = -1
    if private_dir is None:
        raise RuntimeError("Private CID directory was not created")
    cidfile_path = private_dir / f"{prefix}pending{suffix}"
    try:
        # Allocate temp file; clean up dir on failure.
        try:
            cidfile_fd, cidfile_name = tempfile.mkstemp(
                prefix=prefix,
                suffix=suffix,
                dir=private_dir,
                text=True,
            )
            cidfile_path = Path(cidfile_name)
        except BaseException:
            _LOGGER.exception(
                "Failed to allocate CID file in temporary directory: %s",
                private_dir,
            )
            with suppress(OSError):
                private_dir.rmdir()
            raise
    finally:
        if cidfile_fd >= 0:
            os.close(cidfile_fd)

    try:
        cidfile_path.unlink()
    except OSError:
        _LOGGER.exception(
            "Failed to unlink placeholder CID file: %s",
            cidfile_path,
        )
        with suppress(OSError):
            private_dir.rmdir()
        raise

    return cidfile_path
