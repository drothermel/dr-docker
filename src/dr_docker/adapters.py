"""Adapter protocol and error type for runtime primitive consumers."""

from typing import Protocol, runtime_checkable

from .docker_contract import DockerRuntimeRequest, DockerRuntimeResult
from .errors import ErrorEnvelope


class RuntimePrimitiveError(Exception):
    """Raised when a primitive operation fails with a typed infra envelope."""

    def __init__(self, error: ErrorEnvelope) -> None:
        super().__init__(error.message)
        self.error = error


@runtime_checkable
class RuntimeAdapter(Protocol):
    """Primitive Docker runtime executor."""

    def execute_in_runtime(
        self, request: DockerRuntimeRequest
    ) -> DockerRuntimeResult: ...
