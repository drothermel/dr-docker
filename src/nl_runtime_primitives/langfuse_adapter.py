"""Concrete Langfuse-backed PromptProvider and TraceEmitter adapters."""

from __future__ import annotations

import os
from inspect import Parameter, signature
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
    # Langfuse currently does not expose stable typed exceptions for all failure
    # modes, so we classify by message tokens as a pragmatic compatibility layer.
    text = str(exc).lower()
    details: dict[str, object] = {
        "operation": operation,
        "exception_type": type(exc).__name__,
    }

    auth_tokens = ("401", "403", "unauthorized", "forbidden", "api key", "auth ")
    auth_phrases = (" auth", "authentication", "invalid key", "missing key")
    if any(token in text for token in auth_tokens) or any(
        phrase in text for phrase in auth_phrases
    ):
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
            "service unavailable",
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
            text = str(exc).lower()
            if any(
                token in text
                for token in (
                    "langfuse_public_key",
                    "langfuse_secret_key",
                    "missing key",
                    "invalid key",
                    "api key",
                    " auth",
                    "authentication",
                    "unauthorized",
                    "forbidden",
                )
            ):
                err = _error(
                    ErrorCode.AUTH,
                    "Langfuse credentials are missing or invalid",
                    retriable=False,
                    details={"operation": "langfuse_client_init"},
                )
            else:
                err = _error(
                    ErrorCode.MALFORMED_REQUEST,
                    "Langfuse client configuration is invalid",
                    retriable=False,
                    details={"operation": "langfuse_client_init"},
                )
        return _ClientResolution(init_error=err)


def _compile_prompt_template(prompt: Any, variables: dict[str, object]) -> Any:
    compile_fn = getattr(prompt, "compile", None)
    if not callable(compile_fn):
        return prompt

    try:
        params = list(signature(compile_fn).parameters.values())
    except (TypeError, ValueError):
        return compile_fn(**variables)

    accepts_keyword_args = any(param.kind == Parameter.VAR_KEYWORD for param in params)
    if not accepts_keyword_args and variables:
        accepted_names = {
            param.name
            for param in params
            if param.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
        }
        unknown = sorted(name for name in variables if name not in accepted_names)
        if unknown:
            unknown_display = ", ".join(unknown)
            raise TypeError(
                "Langfuse prompt.compile does not accept variables: "
                f"{unknown_display}"
            )

    return compile_fn(**variables)


def _create_event_request_kwargs(event: TraceEventRequest) -> dict[str, object]:
    kwargs: dict[str, object] = {"name": event.event_name}
    if event.metadata:
        kwargs["metadata"] = event.metadata

    input_payload: dict[str, object] = {}
    if event.tags:
        input_payload["tags"] = event.tags
    if event.session_id is not None:
        input_payload["session_id"] = event.session_id
    if input_payload:
        kwargs["input"] = input_payload
    return kwargs


def _normalize_text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            text = _normalize_text_content(item)
            if text:
                parts.append(text)
        return "\n".join(parts)
    if isinstance(value, dict):
        text_value = value.get("text")
        if isinstance(text_value, str):
            return text_value
        content_value = value.get("content")
        if isinstance(content_value, str):
            return content_value
    return ""


def _extract_prompt_content(raw_prompt: Any) -> tuple[str | None, str]:
    source = raw_prompt
    if hasattr(raw_prompt, "prompt"):
        source = raw_prompt.prompt
    elif isinstance(raw_prompt, dict) and "prompt" in raw_prompt:
        source = raw_prompt["prompt"]

    if isinstance(source, str):
        task_content = source.strip()
        if task_content:
            return None, task_content

    if isinstance(source, list):
        system_parts: list[str] = []
        task_parts: list[str] = []
        for msg in source:
            if not isinstance(msg, dict):
                continue
            content = _normalize_text_content(msg.get("content"))
            if not content:
                continue
            role = str(msg.get("role", "")).lower()
            if role == "system":
                system_parts.append(content)
            else:
                task_parts.append(content)
        task_content = "\n".join(task_parts).strip()
        if task_content:
            system_content = "\n".join(system_parts).strip() or None
            return system_content, task_content

    if isinstance(source, dict):
        system = _normalize_text_content(source.get("system_content")).strip() or None
        task = _normalize_text_content(source.get("task_content")).strip()
        if task:
            return system, task

    system_attr = getattr(raw_prompt, "system_content", None)
    task_attr = getattr(raw_prompt, "task_content", None)
    system = _normalize_text_content(system_attr).strip() or None
    task = _normalize_text_content(task_attr).strip()
    if task:
        return system, task

    raise RuntimePrimitiveError(
        _error(
            ErrorCode.INTERNAL_ERROR,
            "Langfuse prompt is missing required task_content",
            retriable=False,
            details={"operation": "fetch_prompt", "reason": "missing_task_content"},
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
            compiled = _compile_prompt_template(prompt, request.variables)
            system_content, task_content = _extract_prompt_content(compiled)
            labels = getattr(prompt, "labels", None)
            resolved_label = request.label
            if resolved_label is None and isinstance(labels, list) and labels:
                first_label = labels[0]
                if isinstance(first_label, str):
                    resolved_label = first_label
            if resolved_label is None:
                prompt_label = getattr(prompt, "label", None)
                if isinstance(prompt_label, str):
                    resolved_label = prompt_label

            return PromptPayload(
                prompt_name=request.prompt_name,
                system_content=system_content,
                task_content=task_content,
                label=resolved_label,
                version=getattr(prompt, "version", request.version),
            )
        except RuntimePrimitiveError:
            raise
        except Exception as exc:
            raise RuntimePrimitiveError(
                _map_exception(exc, operation="fetch_prompt")
            ) from exc


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
            if not hasattr(client, "create_event"):
                raise RuntimeError(
                    "Langfuse client is missing required create_event API"
                )
            client.create_event(**_create_event_request_kwargs(event))
            get_trace_id = getattr(client, "get_current_trace_id", None)
            if callable(get_trace_id):
                trace_id = get_trace_id()
            flush = getattr(client, "flush", None)
            if callable(flush):
                flush()
            return TraceAck(accepted=True, trace_id=trace_id)
        except Exception as exc:
            return TraceAck(
                accepted=False,
                error=_map_exception(exc, operation="emit_trace"),
            )
