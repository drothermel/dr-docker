from __future__ import annotations

from dataclasses import dataclass

import pytest

from nl_runtime_primitives import (
    ErrorCode,
    LangfuseConfig,
    LangfusePromptProvider,
    LangfuseTraceEmitter,
    PromptFetchRequest,
    RuntimePrimitiveError,
    TraceEventRequest,
)


@dataclass
class _PromptResult:
    prompt: list[dict[str, str]]
    labels: list[str] | None = None
    version: int = 7

    def compile(self, **variables: object):
        topic = str(variables.get("topic", ""))
        return [
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": f"Summarize {topic}."},
        ]


class _FakeLangfuseClient:
    def __init__(self) -> None:
        self.trace_flushed = False
        self._trace_id = "trace_123"

    def get_prompt(self, name: str, label: str | None = None, version: int | None = None) -> _PromptResult:
        del name, label, version
        return _PromptResult(
            prompt=[
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Summarize {{topic}}."},
            ],
            labels=["prod"],
        )

    def create_event(
        self,
        *,
        name: str,
        input: object | None = None,
        metadata: object | None = None,
    ):
        del name, input, metadata
        return object()

    def get_current_trace_id(self) -> str:
        return self._trace_id

    def flush(self) -> None:
        self.trace_flushed = True


def test_langfuse_config_from_env() -> None:
    cfg = LangfuseConfig.from_env(
        {
            "LANGFUSE_PUBLIC_KEY": "pk",
            "LANGFUSE_SECRET_KEY": "sk",
            "LANGFUSE_HOST": "https://cloud.langfuse.com",
        }
    )
    assert cfg.public_key == "pk"
    assert cfg.secret_key == "sk"
    assert cfg.host == "https://cloud.langfuse.com"


def test_prompt_provider_success_path() -> None:
    provider = LangfusePromptProvider(client=_FakeLangfuseClient())
    payload = provider.fetch_prompt(
        PromptFetchRequest(prompt_name="summarize", variables={"topic": "the incident"})
    )

    assert payload.prompt_name == "summarize"
    assert payload.system_content == "You are concise."
    assert payload.task_content == "Summarize the incident."
    assert payload.label == "prod"
    assert payload.version == 7


def test_prompt_provider_uses_request_label_when_set() -> None:
    provider = LangfusePromptProvider(client=_FakeLangfuseClient())
    payload = provider.fetch_prompt(
        PromptFetchRequest(
            prompt_name="summarize",
            label="staging",
            variables={"topic": "the incident"},
        )
    )

    assert payload.label == "staging"


def test_trace_emitter_success_path() -> None:
    client = _FakeLangfuseClient()
    emitter = LangfuseTraceEmitter(client=client)

    ack = emitter.emit_trace(
        TraceEventRequest(
            event_name="runtime.step",
            session_id="session-1",
            tags=["runtime"],
            metadata={"attempt": 1},
        )
    )

    assert ack.accepted is True
    assert ack.trace_id == "trace_123"
    assert ack.error is None
    assert client.trace_flushed is True


def test_prompt_provider_maps_auth_errors() -> None:
    class _AuthFailClient:
        def get_prompt(self, name: str, label: str | None = None, version: int | None = None):
            del name, label, version
            raise RuntimeError("401 unauthorized")

    provider = LangfusePromptProvider(client=_AuthFailClient())

    with pytest.raises(RuntimePrimitiveError) as exc_info:
        provider.fetch_prompt(PromptFetchRequest(prompt_name="x"))

    assert exc_info.value.error.code == ErrorCode.AUTH
    assert exc_info.value.error.retriable is False


def test_trace_emitter_maps_unavailable_errors() -> None:
    class _UnavailableClient:
        def create_event(
            self,
            *,
            name: str,
            input: object | None = None,
            metadata: object | None = None,
        ):
            del name, input, metadata
            raise RuntimeError("connection refused")

    emitter = LangfuseTraceEmitter(client=_UnavailableClient())
    ack = emitter.emit_trace(TraceEventRequest(event_name="runtime.step"))

    assert ack.accepted is False
    assert ack.error is not None
    assert ack.error.code == ErrorCode.UNAVAILABLE
    assert ack.error.retriable is True


def test_trace_emitter_rejects_client_without_create_event() -> None:
    class _TraceOnlyClient:
        def trace(
            self,
            *,
            name: str,
            session_id: str | None = None,
            tags: list[str] | None = None,
            metadata: dict[str, object] | None = None,
        ) -> object:
            del name, session_id, tags, metadata
            return object()

    emitter = LangfuseTraceEmitter(client=_TraceOnlyClient())
    ack = emitter.emit_trace(TraceEventRequest(event_name="runtime.step"))

    assert ack.accepted is False
    assert ack.error is not None
    assert ack.error.code == ErrorCode.INTERNAL_ERROR


def test_trace_emitter_maps_internal_errors() -> None:
    class _InternalClient:
        def create_event(
            self,
            *,
            name: str,
            input: object | None = None,
            metadata: object | None = None,
        ):
            del name, input, metadata
            raise RuntimeError("unexpected schema mismatch")

    emitter = LangfuseTraceEmitter(client=_InternalClient())
    ack = emitter.emit_trace(TraceEventRequest(event_name="runtime.step"))

    assert ack.accepted is False
    assert ack.error is not None
    assert ack.error.code == ErrorCode.INTERNAL_ERROR


def test_adapters_handle_missing_langfuse_package() -> None:
    def _missing_factory(config: LangfuseConfig):
        del config
        raise ModuleNotFoundError("langfuse")

    provider = LangfusePromptProvider(client_factory=_missing_factory)
    emitter = LangfuseTraceEmitter(client_factory=_missing_factory)

    with pytest.raises(RuntimePrimitiveError) as exc_info:
        provider.fetch_prompt(PromptFetchRequest(prompt_name="x"))

    assert exc_info.value.error.code == ErrorCode.UNAVAILABLE

    ack = emitter.emit_trace(TraceEventRequest(event_name="runtime.step"))
    assert ack.accepted is False
    assert ack.error is not None
    assert ack.error.code == ErrorCode.UNAVAILABLE


def test_prompt_provider_wraps_invalid_payload_shape_in_runtime_error() -> None:
    class _BadVersionClient:
        def get_prompt(
            self, name: str, label: str | None = None, version: int | None = None
        ):
            del name, label, version

            class _Prompt:
                prompt = "hello"
                version = "v1"

            return _Prompt()

    provider = LangfusePromptProvider(client=_BadVersionClient())

    with pytest.raises(RuntimePrimitiveError) as exc_info:
        provider.fetch_prompt(PromptFetchRequest(prompt_name="x"))

    assert exc_info.value.error.code == ErrorCode.INTERNAL_ERROR


def test_prompt_provider_does_not_mask_internal_compile_type_error() -> None:
    class _BadCompilePrompt:
        labels = ["prod"]
        version = 1

        def compile(self, *args: object, **kwargs: object) -> str:
            if kwargs:
                raise TypeError("template compile failed")
            del args
            return "incorrect-fallback-path"

    class _CompileTypeErrorClient:
        def get_prompt(
            self, name: str, label: str | None = None, version: int | None = None
        ) -> _BadCompilePrompt:
            del name, label, version
            return _BadCompilePrompt()

    provider = LangfusePromptProvider(client=_CompileTypeErrorClient())

    with pytest.raises(RuntimePrimitiveError) as exc_info:
        provider.fetch_prompt(
            PromptFetchRequest(prompt_name="summarize", variables={"topic": "incident"})
        )

    assert exc_info.value.error.code == ErrorCode.INTERNAL_ERROR
