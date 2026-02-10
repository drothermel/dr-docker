from nl_runtime_primitives import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
    PromptFetchRequest,
    PromptPayload,
    PromptProvider,
    RuntimeAdapter,
    TraceAck,
    TraceEmitter,
    TraceEventRequest,
)


class _RuntimeOnly:
    def execute_in_runtime(
        self, request: DockerRuntimeRequest
    ) -> DockerRuntimeResult:
        del request
        return DockerRuntimeResult(ok=True, exit_code=0)


class _PromptOnly:
    def fetch_prompt(self, request: PromptFetchRequest) -> PromptPayload:
        return PromptPayload(
            prompt_name=request.prompt_name,
            system_content="sys",
            task_content="task",
            label=request.label,
            version=request.version,
        )


class _TraceOnly:
    def emit_trace(self, event: TraceEventRequest) -> TraceAck:
        del event
        return TraceAck(accepted=True, trace_id="trace_123")


def test_runtime_protocol_runtime_checkable() -> None:
    assert isinstance(_RuntimeOnly(), RuntimeAdapter)


def test_prompt_protocol_runtime_checkable() -> None:
    assert isinstance(_PromptOnly(), PromptProvider)


def test_trace_protocol_runtime_checkable() -> None:
    assert isinstance(_TraceOnly(), TraceEmitter)
