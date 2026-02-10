"""Concrete Langfuse-backed PromptProvider and TraceEmitter adapters."""

from __future__ import annotations

import os
from inspect import Parameter, signature
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, JsonValue

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


class _CredentialsMissingError(ValueError):
    """Raised when required Langfuse credentials are unavailable."""


def _error(
    code: ErrorCode,
    message: str,
    *,
    retriable: bool,
    details: dict[str, JsonValue] | None = None,
) -> ErrorEnvelope:
    return ErrorEnvelope(
        code=code,
        message=message,
        retriable=retriable,
        details=details or {},
    )


def _map_exception(exc: Exception, *, operation: str) -> ErrorEnvelope:
    details: dict[str, JsonValue] = {
        "operation": operation,
        "exception_type": type(exc).__name__,
    }
    status_code = _extract_status_code(exc)
    if status_code in (401, 403):
        return _error(
            ErrorCode.AUTH,
            "Langfuse authentication failed",
            retriable=False,
            details={**details, "status_code": status_code},
        )
    if status_code in (400, 404, 409, 410, 422):
        return _error(
            ErrorCode.MALFORMED_REQUEST,
            "Langfuse request was rejected",
            retriable=False,
            details={**details, "status_code": status_code},
        )
    if status_code in (408, 425, 429, 500, 502, 503, 504):
        return _error(
            ErrorCode.UNAVAILABLE,
            "Langfuse is unavailable",
            retriable=True,
            details={**details, "status_code": status_code},
        )
    if _is_transport_exception(exc):
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


def _extract_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_code = getattr(response, "status_code", None)
    if isinstance(response_code, int):
        return response_code
    return None


def _is_transport_exception(exc: Exception) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (ConnectionError, TimeoutError)):
            return True
        request = getattr(current, "request", None)
        name = type(current).__name__.lower()
        if request is not None and any(
            token in name for token in ("timeout", "connect", "network")
        ):
            return True
        current = (
            current.__cause__
            if current.__cause__ is not None
            else current.__context__
        )
    return False


def _default_langfuse_client_factory(config: LangfuseConfig) -> Any:
    if not config.public_key or not config.secret_key:
        raise _CredentialsMissingError(
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
        elif isinstance(exc, _CredentialsMissingError):
            err = _error(
                ErrorCode.AUTH,
                "Langfuse credentials are missing or invalid",
                retriable=False,
                details={"operation": "langfuse_client_init"},
            )
        elif isinstance(exc, ValueError):
            err = _error(
                ErrorCode.MALFORMED_REQUEST,
                "Langfuse client configuration is invalid",
                retriable=False,
                details={"operation": "langfuse_client_init"},
            )
        return _ClientResolution(init_error=err)


def _malformed_request_error(
    message: str, *, reason: str, details: dict[str, JsonValue] | None = None
) -> ErrorEnvelope:
    return _error(
        ErrorCode.MALFORMED_REQUEST,
        message,
        retriable=False,
        details={
            "operation": "fetch_prompt",
            "reason": reason,
            **(details or {}),
        },
    )


def _compile_prompt_template(prompt: Any, variables: dict[str, JsonValue]) -> Any:
    compile_fn = getattr(prompt, "compile", None)
    if not callable(compile_fn):
        raise RuntimePrimitiveError(
            _malformed_request_error(
                "Langfuse prompt does not expose a callable compile method",
                reason="missing_compile_method",
            )
        )

    try:
        params = list(signature(compile_fn).parameters.values())
    except (TypeError, ValueError):
        try:
            return compile_fn(**variables)
        except TypeError as exc:
            raise RuntimePrimitiveError(
                _malformed_request_error(
                    "Langfuse prompt.compile rejected the provided variables",
                    reason="compile_invocation_type_error",
                    details={"exception": str(exc)},
                )
            ) from exc

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
            raise RuntimePrimitiveError(
                _malformed_request_error(
                    "Langfuse prompt.compile does not accept provided variables",
                    reason="unknown_compile_variables",
                    details={"unknown_variables": unknown_display},
                )
            )

    try:
        return compile_fn(**variables)
    except TypeError as exc:
        raise RuntimePrimitiveError(
            _malformed_request_error(
                "Langfuse prompt.compile rejected the provided variables",
                reason="compile_invocation_type_error",
                details={"exception": str(exc)},
            )
        ) from exc


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


def _extract_prompt_content(raw_prompt: Any) -> tuple[str, str]:
    if not isinstance(raw_prompt, list):
        raise RuntimePrimitiveError(
            _error(
                ErrorCode.MALFORMED_REQUEST,
                "Langfuse prompt must compile to a chat message list",
                retriable=False,
                details={"operation": "fetch_prompt", "reason": "invalid_prompt_shape"},
            )
        )

    system_parts: list[str] = []
    user_message_count = 0
    user_contents: list[str] = []
    for msg in raw_prompt:
        if not isinstance(msg, dict):
            raise RuntimePrimitiveError(
                _error(
                    ErrorCode.MALFORMED_REQUEST,
                    "Langfuse prompt message must be an object",
                    retriable=False,
                    details={
                        "operation": "fetch_prompt",
                        "reason": "invalid_message_shape",
                    },
                )
            )

        role = str(msg.get("role", "")).lower()
        content = _normalize_text_content(msg.get("content")).strip()
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if role == "user":
            user_message_count += 1
            if content:
                user_contents.append(content)
            continue
        raise RuntimePrimitiveError(
            _error(
                ErrorCode.MALFORMED_REQUEST,
                "Langfuse prompt contains unsupported message role",
                retriable=False,
                details={"operation": "fetch_prompt", "reason": "invalid_message_role"},
            )
        )

    if user_message_count != 1:
        raise RuntimePrimitiveError(
            _error(
                ErrorCode.MALFORMED_REQUEST,
                "Langfuse prompt must contain exactly one user message",
                retriable=False,
                details={
                    "operation": "fetch_prompt",
                    "reason": "invalid_user_message_count",
                },
            )
        )
    if len(user_contents) != 1:
        raise RuntimePrimitiveError(
            _error(
                ErrorCode.MALFORMED_REQUEST,
                "Langfuse prompt user message content must be non-empty",
                retriable=False,
                details={
                    "operation": "fetch_prompt",
                    "reason": "empty_user_message_content",
                },
            )
        )
    return "\n\n".join(system_parts), user_contents[0]


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
            client.create_event(**_create_event_request_kwargs(event))
        except Exception as exc:
            return TraceAck(
                accepted=False,
                error=_map_exception(exc, operation="emit_trace"),
            )

        trace_id: str | None = None
        get_trace_id = getattr(client, "get_current_trace_id", None)
        if callable(get_trace_id):
            try:
                maybe_trace_id = get_trace_id()
                if isinstance(maybe_trace_id, str):
                    trace_id = maybe_trace_id
            except Exception:
                pass

        flush = getattr(client, "flush", None)
        if callable(flush):
            try:
                flush()
            except Exception:
                pass

        return TraceAck(accepted=True, trace_id=trace_id)
