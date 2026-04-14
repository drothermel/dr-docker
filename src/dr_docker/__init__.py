"""Typed Docker runtime contracts and subprocess adapter."""

from .adapters import (
    RuntimeAdapter,
    RuntimePrimitiveError,
    execute_in_runtime_or_raise,
)
from .batching import execute_batch_in_container, run_batch_with_failure_isolation
from .docker_contract import (
    DockerMount,
    DockerRuntimeRequest,
    DockerRuntimeResult,
    ResourceLimits,
    SecurityProfile,
    TmpfsMount,
)
from .errors import ErrorCode, ErrorEnvelope
from .subprocess_adapter import SubprocessDockerAdapter
from .version import CONTRACT_VERSION, __version__
from .workers import (
    JsonWorkerExecutionConfig,
    MountedWorker,
    WorkerRuntimePolicy,
    build_mounted_worker_request,
    mount_worker_directory,
    mount_worker_file,
    parse_byte_size,
)

__all__ = [
    "CONTRACT_VERSION",
    "DockerMount",
    "DockerRuntimeRequest",
    "DockerRuntimeResult",
    "ErrorCode",
    "ErrorEnvelope",
    "JsonWorkerExecutionConfig",
    "MountedWorker",
    "parse_byte_size",
    "ResourceLimits",
    "RuntimeAdapter",
    "RuntimePrimitiveError",
    "SecurityProfile",
    "SubprocessDockerAdapter",
    "TmpfsMount",
    "WorkerRuntimePolicy",
    "build_mounted_worker_request",
    "execute_in_runtime_or_raise",
    "execute_batch_in_container",
    "mount_worker_directory",
    "mount_worker_file",
    "run_batch_with_failure_isolation",
    "__version__",
]
