"""Typed primitive contracts for Docker and Langfuse runtime integrations."""

from .adapters import (
    PromptProvider,
    RuntimeAdapter,
    RuntimePrimitiveError,
    RuntimePrimitivesAdapter,
    TraceEmitter,
)
from .docker_contract import DockerMount, DockerRuntimeRequest, DockerRuntimeResult
from .errors import ErrorCode, ErrorEnvelope
from .langfuse_adapter import (
    LangfuseConfig,
    LangfusePromptProvider,
    LangfuseTraceEmitter,
)
from .langfuse_contract import (
    PromptFetchRequest,
    PromptPayload,
    TraceAck,
    TraceEventRequest,
)
from .local_subprocess import LocalSubprocessRuntimeAdapter
from .stubs import StubRuntimePrimitivesAdapter
from .version import CONTRACT_VERSION, __version__

__all__ = [
    "__version__",
    "CONTRACT_VERSION",
    "ErrorCode",
    "ErrorEnvelope",
    "DockerMount",
    "DockerRuntimeRequest",
    "DockerRuntimeResult",
    "PromptFetchRequest",
    "PromptPayload",
    "TraceEventRequest",
    "TraceAck",
    "RuntimePrimitiveError",
    "RuntimeAdapter",
    "PromptProvider",
    "TraceEmitter",
    "RuntimePrimitivesAdapter",
    "StubRuntimePrimitivesAdapter",
    "LocalSubprocessRuntimeAdapter",
    "LangfuseConfig",
    "LangfusePromptProvider",
    "LangfuseTraceEmitter",
]
