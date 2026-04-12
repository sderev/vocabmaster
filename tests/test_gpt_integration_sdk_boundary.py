from types import SimpleNamespace

import httpx
import pytest
from openai import RateLimitError

from vocabmaster import gpt_integration


class FakeStreamingResponse:
    def __init__(self, events, final_response):
        self._events = list(events)
        self._final_response = final_response

    def __iter__(self):
        return iter(self._events)

    def get_final_response(self):
        return self._final_response


class FakeStreamingContext:
    def __init__(self, stream_response=None, enter_error=None):
        self._stream_response = stream_response
        self._enter_error = enter_error

    def __enter__(self):
        if self._enter_error is not None:
            raise self._enter_error
        return self._stream_response

    def __exit__(self, exc_type, exc, exc_tb):
        return False


def test_chatgpt_request_non_streaming_uses_response_output_text():
    create_calls = []
    response = SimpleNamespace(output_text="bonjour\thello\texample")

    class FakeResponses:
        def create(self, **kwargs):
            create_calls.append(kwargs)
            return response

    client = SimpleNamespace(responses=FakeResponses())

    generated_text, response_time, raw_response = gpt_integration.chatgpt_request(
        prompt=[{"role": "user", "content": "Translate bonjour"}],
        stream=False,
        client=client,
    )

    assert generated_text == response.output_text
    assert response_time >= 0
    assert raw_response is response
    assert create_calls == [
        {
            "input": [{"role": "user", "content": "Translate bonjour"}],
            "model": gpt_integration.DEFAULT_MODEL,
            "temperature": 0.7,
            "stream": False,
        }
    ]


def test_chatgpt_request_streaming_uses_public_stream_api_and_filters_output(capsys):
    stream_calls = []
    final_response = SimpleNamespace(
        output_text="bonjour\tbon jour\thello\texample\nsalut\tsalut\thi\texample two\n"
    )
    stream_response = FakeStreamingResponse(
        events=[
            SimpleNamespace(type="response.created"),
            SimpleNamespace(type="response.output_text.delta", delta="bonjour\tbon jour\t"),
            SimpleNamespace(type="response.output_text.delta", delta="hello\texample\n"),
            SimpleNamespace(type="response.output_text.delta", delta="salut\tsalut\thi\t"),
            SimpleNamespace(type="response.output_text.delta", delta="example two\n"),
        ],
        final_response=final_response,
    )

    class FakeResponses:
        def stream(self, **kwargs):
            stream_calls.append(kwargs)
            return FakeStreamingContext(stream_response=stream_response)

    client = SimpleNamespace(responses=FakeResponses())

    generated_text, response_time, raw_response = gpt_integration.chatgpt_request(
        prompt=[{"role": "user", "content": "Translate bonjour and salut"}],
        stream=True,
        client=client,
    )

    captured = capsys.readouterr()

    assert generated_text == final_response.output_text
    assert response_time >= 0
    assert raw_response is final_response
    assert captured.out == "bonjour\thello\texample\nsalut\thi\texample two\n\n"
    assert stream_calls == [
        {
            "input": [{"role": "user", "content": "Translate bonjour and salut"}],
            "model": gpt_integration.DEFAULT_MODEL,
            "temperature": 0.7,
        }
    ]


def test_chatgpt_request_streaming_falls_back_to_final_output_text(capsys):
    final_response = SimpleNamespace(output_text="bonjour\tbon jour\thello\texample\n")
    stream_response = FakeStreamingResponse(
        events=[SimpleNamespace(type="response.completed")],
        final_response=final_response,
    )

    class FakeResponses:
        def stream(self, **kwargs):
            return FakeStreamingContext(stream_response=stream_response)

    client = SimpleNamespace(responses=FakeResponses())

    generated_text, _response_time, raw_response = gpt_integration.chatgpt_request(
        prompt=[{"role": "user", "content": "Translate bonjour"}],
        stream=True,
        client=client,
    )

    captured = capsys.readouterr()

    assert generated_text == final_response.output_text
    assert raw_response is final_response
    assert captured.out == "bonjour\thello\texample\n\n"


def test_chatgpt_request_streaming_propagates_public_status_errors():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request)
    rate_limit_error = RateLimitError("Too many requests", response=response, body=None)

    class FakeResponses:
        def stream(self, **kwargs):
            return FakeStreamingContext(enter_error=rate_limit_error)

    def forbidden_private_helper(_response):
        raise AssertionError("private OpenAI helper should not be used")

    client = SimpleNamespace(
        responses=FakeResponses(),
        _make_status_error_from_response=forbidden_private_helper,
    )

    with pytest.raises(RateLimitError):
        gpt_integration.chatgpt_request(
            prompt=[{"role": "user", "content": "Translate bonjour"}],
            stream=True,
            client=client,
        )
