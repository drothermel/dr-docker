"""Typed primitive contracts for Docker and Langfuse runtime integrations."""

from .adapters import (
    PromptProvider,
    RuntimeAdapter,
    RuntimePrimitiveError,
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
from .version import CONTRACT_VERSION, __version__

__all__ = [
    "CONTRACT_VERSION",
    "DockerMount",
    "DockerRuntimeRequest",
    "DockerRuntimeResult",
    "ErrorCode",
    "ErrorEnvelope",
    "LangfuseConfig",
    "LangfusePromptProvider",
    "LangfuseTraceEmitter",
    "PromptFetchRequest",
    "PromptPayload",
    "PromptProvider",
    "RuntimeAdapter",
    "RuntimePrimitiveError",
    "TraceAck",
    "TraceEmitter",
    "TraceEventRequest",
    "__version__",
]
