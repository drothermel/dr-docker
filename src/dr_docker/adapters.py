"""Adapter protocol and error type for runtime primitive consumers."""

from typing import Protocol, runtime_checkable

from .docker_contract import DockerRuntimeRequest, DockerRuntimeResult
from .errors import ErrorCode, ErrorEnvelope


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


def _invalid_runtime_result_error(
    *, message: str, contract_violation: str
) -> RuntimePrimitiveError:
    return RuntimePrimitiveError(
        ErrorEnvelope(
            code=ErrorCode.INTERNAL_ERROR,
            message=message,
            details={"contract_violation": contract_violation},
        )
    )


def execute_in_runtime_or_raise(
    adapter: RuntimeAdapter, request: DockerRuntimeRequest
) -> DockerRuntimeResult:
    """Execute one runtime request and raise on typed infra failure."""

    result = adapter.execute_in_runtime(request)
    if result.ok and result.error is not None:
        raise _invalid_runtime_result_error(
            message="RuntimeAdapter returned ok=True with an unexpected error envelope",
            contract_violation="ok_true_with_error",
        )
    if result.ok:
        return result

    error = result.error
    if error is None:
        raise _invalid_runtime_result_error(
            message="RuntimeAdapter returned ok=False without an error envelope",
            contract_violation="ok_false_without_error",
        )
    raise RuntimePrimitiveError(error)
