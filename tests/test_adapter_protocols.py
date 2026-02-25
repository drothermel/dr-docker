from nl_runtime_primitives import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
    RuntimeAdapter,
)


class _RuntimeOnly:
    def execute_in_runtime(
        self, request: DockerRuntimeRequest
    ) -> DockerRuntimeResult:
        del request
        return DockerRuntimeResult(ok=True, exit_code=0)


def test_runtime_protocol_runtime_checkable() -> None:
    assert isinstance(_RuntimeOnly(), RuntimeAdapter)
