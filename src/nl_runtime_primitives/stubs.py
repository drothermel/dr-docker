"""Stub adapter implementations for integration wiring and local tests."""

from .adapters import RuntimePrimitiveError
from .docker_contract import DockerRuntimeRequest, DockerRuntimeResult
from .errors import ErrorCode, ErrorEnvelope
from .langfuse_contract import PromptFetchRequest, PromptPayload, TraceAck, TraceEventRequest


def _unavailable_error(operation: str) -> ErrorEnvelope:
    return ErrorEnvelope(
        code=ErrorCode.UNAVAILABLE,
        message=f"{operation} is unavailable in stub adapter",
        retriable=True,
    )


class StubRuntimePrimitivesAdapter:
    """Deterministic stub for early integration and contract testing."""

    def __init__(
        self,
        *,
        docker_result: DockerRuntimeResult | None = None,
        prompt_payload: PromptPayload | None = None,
        trace_ack: TraceAck | None = None,
    ) -> None:
        self._docker_result = docker_result
        self._prompt_payload = prompt_payload
        self._trace_ack = trace_ack

    def execute_in_runtime(
        self, request: DockerRuntimeRequest
    ) -> DockerRuntimeResult:
        del request
        if self._docker_result is not None:
            return self._docker_result
        err = _unavailable_error("execute_in_runtime")
        return DockerRuntimeResult(ok=False, error=err)

    def fetch_prompt(self, request: PromptFetchRequest) -> PromptPayload:
        del request
        if self._prompt_payload is not None:
            return self._prompt_payload
        raise RuntimePrimitiveError(_unavailable_error("fetch_prompt"))

    def emit_trace(self, event: TraceEventRequest) -> TraceAck:
        del event
        if self._trace_ack is not None:
            return self._trace_ack
        return TraceAck(
            accepted=False,
            error=_unavailable_error("emit_trace"),
        )

