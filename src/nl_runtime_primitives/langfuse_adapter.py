"""Concrete Langfuse-backed PromptProvider and TraceEmitter adapters."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel

from .adapters import RuntimePrimitiveError
from .errors import ErrorCode, ErrorEnvelope
from .langfuse_contract import PromptFetchRequest, PromptPayload, TraceAck, TraceEventRequest

LANGFUSE_PUBLIC_KEY_ENV = "LANGFUSE_PUBLIC_KEY"
LANGFUSE_SECRET_KEY_ENV = "LANGFUSE_SECRET_KEY"
LANGFUSE_HOST_ENV = "LANGFUSE_HOST"


class LangfuseConfig(BaseModel):
    """Minimal Langfuse connection config."""

    public_key: str | None = None
    secret_key: str | None = None
    host: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LangfuseConfig":
        environ = os.environ if env is None else env
        return cls(
            public_key=environ.get(LANGFUSE_PUBLIC_KEY_ENV),
            secret_key=environ.get(LANGFUSE_SECRET_KEY_ENV),
            host=environ.get(LANGFUSE_HOST_ENV),
        )


@dataclass(frozen=True)
class _ClientResolution:
    client: Any | None = None
    init_error: ErrorEnvelope | None = None


def _error(
    code: ErrorCode,
    message: str,
    *,
    retriable: bool,
    details: dict[str, object] | None = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        code=code,
        message=message,
        retriable=retriable,
        details=details or {},
    )


def _map_exception(exc: Exception, *, operation: str) -> ErrorEnvelope:
    text = str(exc).lower()
    details: dict[str, object] = {
        "operation": operation,
        "exception_type": type(exc).__name__,
    }

    if any(token in text for token in ("401", "403", "unauthorized", "forbidden", "api key", "auth")):
        return _error(
            ErrorCode.AUTH,
            "Langfuse authentication failed",
            retriable=False,
            details=details,
        )

    if any(
        token in text
        for token in (
            "connection",
            "timeout",
            "temporar",
            "unavailable",
            "refused",
            "dns",
            "429",
            "rate limit",
            "service",
        )
    ):
        return _error(
            ErrorCode.UNAVAILABLE,
            "Langfuse is unavailable",
            retriable=True,
            details=details,
        )

    return _error(
        ErrorCode.INTERNAL_ERROR,
        "Langfuse integration failed",
        retriable=False,
        details=details,
    )


def _default_langfuse_client_factory(config: LangfuseConfig) -> Any:
    if not config.public_key or not config.secret_key:
        raise ValueError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required for Langfuse adapters"
        )

    try:
        from langfuse import Langfuse  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via adapter behavior
        raise ModuleNotFoundError(
            "langfuse package is not installed"
        ) from exc

    kwargs: dict[str, object] = {
        "public_key": config.public_key,
        "secret_key": config.secret_key,
    }
    if config.host:
        kwargs["host"] = config.host
    return Langfuse(**kwargs)


def _resolve_client(
    *,
    client: Any | None,
    config: LangfuseConfig,
    client_factory: Callable[[LangfuseConfig], Any],
) -> _ClientResolution:
    if client is not None:
        return _ClientResolution(client=client)

    try:
        return _ClientResolution(client=client_factory(config))
    except Exception as exc:
        err = _map_exception(exc, operation="langfuse_client_init")
        if isinstance(exc, (ModuleNotFoundError, ImportError)):
            err = _error(
                ErrorCode.UNAVAILABLE,
                "Langfuse client package is unavailable",
                retriable=True,
                details={"operation": "langfuse_client_init", "reason": "package_unavailable"},
            )
        elif isinstance(exc, ValueError):
            err = _error(
                ErrorCode.AUTH,
                "Langfuse credentials are missing or invalid",
                retriable=False,
                details={"operation": "langfuse_client_init"},
            )
        return _ClientResolution(init_error=err)


def _render_text(template: str, variables: dict[str, object]) -> str:
    if not variables:
        return template
    try:
        return template.format(**variables)
    except Exception:
        return template


def _extract_prompt_content(raw_prompt: Any, variables: dict[str, object]) -> tuple[str, str]:
    source = raw_prompt
    if hasattr(raw_prompt, "prompt"):
        source = raw_prompt.prompt
    elif isinstance(raw_prompt, dict) and "prompt" in raw_prompt:
        source = raw_prompt["prompt"]

    if isinstance(source, str):
        return "", _render_text(source, variables)

    if isinstance(source, list):
        system_parts: list[str] = []
        task_parts: list[str] = []
        for msg in source:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            rendered = _render_text(content, variables)
            role = str(msg.get("role", "")).lower()
            if role == "system":
                system_parts.append(rendered)
            else:
                task_parts.append(rendered)
        return "\n".join(system_parts), "\n".join(task_parts)

    if isinstance(source, dict):
        system = source.get("system_content")
        task = source.get("task_content")
        if isinstance(system, str) and isinstance(task, str):
            return _render_text(system, variables), _render_text(task, variables)

    system_attr = getattr(raw_prompt, "system_content", None)
    task_attr = getattr(raw_prompt, "task_content", None)
    if isinstance(system_attr, str) and isinstance(task_attr, str):
        return _render_text(system_attr, variables), _render_text(task_attr, variables)

    raise RuntimePrimitiveError(
        _error(
            ErrorCode.INTERNAL_ERROR,
            "Langfuse prompt shape is unsupported",
            retriable=False,
            details={"operation": "fetch_prompt"},
        )
    )


class LangfusePromptProvider:
    """Prompt provider implementation backed by Langfuse."""

    def __init__(
        self,
        *,
        config: LangfuseConfig | None = None,
        client: Any | None = None,
        client_factory: Callable[[LangfuseConfig], Any] | None = None,
    ) -> None:
        self._config = config or LangfuseConfig.from_env()
        self._client_factory = client_factory or _default_langfuse_client_factory
        self._client_resolution = _resolve_client(
            client=client,
            config=self._config,
            client_factory=self._client_factory,
        )

    def fetch_prompt(self, request: PromptFetchRequest) -> PromptPayload:
        if self._client_resolution.init_error is not None:
            raise RuntimePrimitiveError(self._client_resolution.init_error)

        client = self._client_resolution.client
        assert client is not None

        try:
            prompt = client.get_prompt(
                request.prompt_name,
                label=request.label,
                version=request.version,
            )
            system_content, task_content = _extract_prompt_content(prompt, request.variables)
        except RuntimePrimitiveError:
            raise
        except Exception as exc:
            raise RuntimePrimitiveError(_map_exception(exc, operation="fetch_prompt")) from exc

        return PromptPayload(
            prompt_name=request.prompt_name,
            system_content=system_content,
            task_content=task_content,
            label=getattr(prompt, "label", request.label),
            version=getattr(prompt, "version", request.version),
        )


class LangfuseTraceEmitter:
    """Trace emitter implementation backed by Langfuse."""

    def __init__(
        self,
        *,
        config: LangfuseConfig | None = None,
        client: Any | None = None,
        client_factory: Callable[[LangfuseConfig], Any] | None = None,
    ) -> None:
        self._config = config or LangfuseConfig.from_env()
        self._client_factory = client_factory or _default_langfuse_client_factory
        self._client_resolution = _resolve_client(
            client=client,
            config=self._config,
            client_factory=self._client_factory,
        )

    def emit_trace(self, event: TraceEventRequest) -> TraceAck:
        if self._client_resolution.init_error is not None:
            return TraceAck(accepted=False, error=self._client_resolution.init_error)

        client = self._client_resolution.client
        assert client is not None

        try:
            trace_id: str | None = None
            if hasattr(client, "create_event"):
                input_payload: dict[str, object] = {}
                if event.tags:
                    input_payload["tags"] = event.tags
                if event.session_id is not None:
                    input_payload["session_id"] = event.session_id
                create_event_kwargs: dict[str, object] = {
                    "name": event.event_name,
                    "metadata": event.metadata,
                }
                if input_payload:
                    create_event_kwargs["input"] = input_payload
                client.create_event(**create_event_kwargs)
                get_trace_id = getattr(client, "get_current_trace_id", None)
                if callable(get_trace_id):
                    trace_id = get_trace_id()
            elif hasattr(client, "trace"):
                trace = client.trace(
                    name=event.event_name,
                    session_id=event.session_id,
                    tags=event.tags,
                    metadata=event.metadata,
                )
                trace_id = getattr(trace, "id", None) or getattr(
                    trace, "trace_id", None
                )
            else:
                raise RuntimeError(
                    "Langfuse client is missing both create_event and trace APIs"
                )
            flush = getattr(client, "flush", None)
            if callable(flush):
                flush()
            return TraceAck(accepted=True, trace_id=trace_id)
        except Exception as exc:
            return TraceAck(
                accepted=False,
                error=_map_exception(exc, operation="emit_trace"),
            )
