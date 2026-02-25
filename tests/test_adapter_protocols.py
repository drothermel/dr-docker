from dr_docker import (
    DockerRuntimeRequest,
    DockerRuntimeResult,
    RuntimeAdapter,
    SubprocessDockerAdapter,
)


class _RuntimeOnly:
    def execute_in_runtime(self, request: DockerRuntimeRequest) -> DockerRuntimeResult:
        del request
        return DockerRuntimeResult(ok=True, exit_code=0)


def test_runtime_protocol_runtime_checkable() -> None:
    assert isinstance(_RuntimeOnly(), RuntimeAdapter)


def test_subprocess_adapter_satisfies_protocol() -> None:
    adapter = SubprocessDockerAdapter()
    assert isinstance(adapter, RuntimeAdapter)
