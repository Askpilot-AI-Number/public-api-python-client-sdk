"""The request, the retries, the timeout, the headers, and the log lines.

Each test sends a request through a client on the mock transport and reads
what arrived, what the client did between the tries, and what it logged.
"""

# Python 3.9 evaluates the annotation of a function at run time, and it gives a
# TypeError for `X | Y`. This line makes each annotation of this file a string.
# `tests/conftest.py` holds the same line, for the same reason.
from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from importlib.metadata import PackageNotFoundError

import httpx
import pytest

import askpilot
from askpilot import _http
from askpilot._http import read_version
from askpilot.errors import APIError, APITimeoutError, ServerError
from tests.conftest import (
    API_KEY,
    ORGANIZATION_BODY,
    PAGE_BODY,
    START_BODY,
    WORKFLOW_ID,
    Recorder,
    error_body,
    json_response,
    make_async_client,
    make_client,
)

# ---------------------------------------------------------------------------
# The request.
# ---------------------------------------------------------------------------


def test_each_request_holds_the_4_headers() -> None:
    """Authorization, Accept, User-Agent, and X-Request-ID go on each request."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    client.organization.get()

    headers = recorder.request.headers
    assert headers["Authorization"] == f"Bearer {API_KEY}"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"] == (
        f"askpilot-python/{askpilot.__version__} "
        f"python/{sys.version_info.major}.{sys.version_info.minor} httpx/{httpx.__version__}"
    )
    assert uuid.UUID(headers["X-Request-ID"]).version == 4


def test_read_version_gives_the_fallback_without_the_package_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read gives the version of the metadata, and 0.0.0+unknown without the metadata.

    A frozen application has no package metadata, and the import of the SDK
    must not stop there.
    """
    assert read_version() == askpilot.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", read_version())

    def raise_not_found(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(_http, "version", raise_not_found)

    assert read_version() == "0.0.0+unknown"


def test_each_call_makes_a_new_request_id() -> None:
    """2 calls hold 2 different ids."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    client.organization.get()
    client.organization.get()

    first, second = (request.headers["X-Request-ID"] for request in recorder.requests)
    assert first != second


def test_the_url_is_absolute_and_holds_the_query() -> None:
    """The request goes to the base URL, with the path and the query parameters."""
    recorder = Recorder(json_response(200, PAGE_BODY))
    client = make_client(recorder)

    client.workflows.list(limit=10, search="a b")

    url = recorder.request.url
    assert url.scheme == "https"
    assert url.host == "api.askpilot.test"
    assert url.path == "/v1/workflows"
    assert dict(url.params) == {"limit": "10", "search": "a b"}


def test_a_get_sends_no_body_and_no_content_type() -> None:
    """A GET holds no body."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    client.organization.get()

    assert recorder.request.content == b""
    assert "Content-Type" not in recorder.request.headers


def test_a_post_sends_json_with_the_content_type() -> None:
    """A POST holds the JSON body and Content-Type: application/json."""
    recorder = Recorder(json_response(202, START_BODY))
    client = make_client(recorder)

    client.workflows.start(WORKFLOW_ID, context="New lead")

    assert recorder.request.method == "POST"
    assert recorder.request.headers["Content-Type"] == "application/json"
    assert json.loads(recorder.request.content) == {"context": "New lead"}


def test_the_timeout_goes_on_each_request() -> None:
    """The timeout of the client is on the request, so it applies to a client of the caller."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder, timeout=5.0)

    client.organization.get()

    assert recorder.request.extensions["timeout"] == httpx.Timeout(5.0).as_dict()


def test_the_default_timeout_is_30_seconds() -> None:
    """The default is 30 seconds for each phase of the request."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    client.organization.get()

    assert recorder.request.extensions["timeout"] == httpx.Timeout(30.0).as_dict()


def test_an_httpx_timeout_object_is_accepted() -> None:
    """A caller can give each phase its own value."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder, timeout=httpx.Timeout(10.0, connect=2.0))

    client.organization.get()

    assert recorder.request.extensions["timeout"]["connect"] == 2.0
    assert recorder.request.extensions["timeout"]["read"] == 10.0


def test_the_client_of_the_caller_does_not_add_its_own_credential() -> None:
    """The auth of a caller-made httpx client is not applied to the request."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    http = httpx.Client(transport=httpx.MockTransport(recorder), auth=("user", "pass"))
    client = askpilot.Askpilot(
        api_key=API_KEY, base_url="https://api.askpilot.test", http_client=http
    )

    client.organization.get()

    assert recorder.request.headers["Authorization"] == f"Bearer {API_KEY}"


# ---------------------------------------------------------------------------
# The retries.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [502, 503, 504])
def test_a_get_retries_after_a_gateway_status(status: int, sleeps: list[float]) -> None:
    """A GET is sent again after a 502, a 503, or a 504."""
    recorder = Recorder(httpx.Response(status), json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    organization = client.organization.get()

    assert organization.name == "Acme Estates"
    assert len(recorder.requests) == 2
    assert sleeps == [0.5]


@pytest.mark.parametrize(
    "failure",
    [httpx.ConnectError("no route"), httpx.ReadTimeout("slow"), httpx.PoolTimeout("busy")],
)
def test_a_get_retries_after_a_connection_error_or_a_timeout(
    failure: Exception, sleeps: list[float]
) -> None:
    """A GET is sent again when no answer arrived."""
    recorder = Recorder(failure, json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    organization = client.organization.get()

    assert organization.name == "Acme Estates"
    assert len(recorder.requests) == 2
    assert sleeps == [0.5]


@pytest.mark.parametrize("status", [500, 501, 400, 404, 422])
def test_a_get_does_not_retry_after_another_status(status: int, sleeps: list[float]) -> None:
    """Only 429, 502, 503, and 504 cause a retry of a GET."""
    recorder = Recorder(
        json_response(status, error_body("x")), json_response(200, ORGANIZATION_BODY)
    )
    client = make_client(recorder)

    with pytest.raises(APIError):
        client.organization.get()

    assert len(recorder.requests) == 1
    assert sleeps == []


def test_a_post_retries_after_a_429(sleeps: list[float]) -> None:
    """A 429 means that the service refused the request before any work."""
    recorder = Recorder(
        json_response(429, error_body("rate_limited"), {"Retry-After": "3"}),
        json_response(202, START_BODY),
    )
    client = make_client(recorder)

    start = client.workflows.start(WORKFLOW_ID, context="New lead")

    assert str(start.workflow_id) == WORKFLOW_ID
    assert len(recorder.requests) == 2
    assert sleeps == [3.0]


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(502),
        httpx.Response(503),
        httpx.Response(504),
        httpx.ConnectError("no route"),
        httpx.ReadTimeout("slow"),
    ],
)
def test_a_post_never_retries_for_another_cause(
    answer: httpx.Response | Exception, sleeps: list[float]
) -> None:
    """A start that reached the service may have started the workflow."""
    recorder = Recorder(answer, json_response(202, START_BODY))
    client = make_client(recorder)

    with pytest.raises(askpilot.AskpilotError):
        client.workflows.start(WORKFLOW_ID, context="New lead")

    assert len(recorder.requests) == 1
    assert sleeps == []


def test_max_retries_0_disables_the_retries(sleeps: list[float]) -> None:
    """With max_retries=0 the first try is the only try."""
    recorder = Recorder(httpx.Response(503), json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder, max_retries=0)

    with pytest.raises(ServerError):
        client.organization.get()

    assert len(recorder.requests) == 1
    assert sleeps == []


def test_the_default_is_2_retries_and_the_last_try_raises(sleeps: list[float]) -> None:
    """3 tries in all, then the exception of the third try."""
    recorder = Recorder(httpx.Response(503))
    client = make_client(recorder)

    with pytest.raises(ServerError) as raised:
        client.organization.get()

    assert raised.value.status_code == 503
    assert len(recorder.requests) == 3
    assert sleeps == [0.5, 1.0]


def test_the_waits_are_half_a_second_then_1_then_2(sleeps: list[float]) -> None:
    """The wait grows to 2 seconds and stays there."""
    recorder = Recorder(httpx.Response(503))
    client = make_client(recorder, max_retries=4)

    with pytest.raises(ServerError):
        client.organization.get()

    assert len(recorder.requests) == 5
    assert sleeps == [0.5, 1.0, 2.0, 2.0]


def test_retry_after_gives_the_wait_of_a_429(sleeps: list[float]) -> None:
    """The service says how long to wait."""
    recorder = Recorder(
        json_response(429, error_body("rate_limited"), {"Retry-After": "7"}),
        json_response(200, ORGANIZATION_BODY),
    )
    client = make_client(recorder)

    client.organization.get()

    assert sleeps == [7.0]


def test_retry_after_is_capped_at_60_seconds(sleeps: list[float]) -> None:
    """A wait longer than 60 seconds becomes 60."""
    recorder = Recorder(
        json_response(429, error_body("rate_limited"), {"Retry-After": "600"}),
        json_response(200, ORGANIZATION_BODY),
    )
    client = make_client(recorder)

    client.organization.get()

    assert sleeps == [60.0]


@pytest.mark.parametrize("headers", [{}, {"Retry-After": "soon"}, {"Retry-After": "-5"}])
def test_a_429_without_a_usable_retry_after_uses_the_backoff(
    headers: dict[str, str], sleeps: list[float]
) -> None:
    """A missing or unreadable header gives the normal wait."""
    recorder = Recorder(
        json_response(429, error_body("rate_limited"), headers),
        json_response(200, ORGANIZATION_BODY),
    )
    client = make_client(recorder)

    client.organization.get()

    assert sleeps == [0.5]


def test_the_request_id_stays_the_same_for_each_try() -> None:
    """The 3 tries of 1 call hold 1 X-Request-ID."""
    recorder = Recorder(
        httpx.Response(503), httpx.Response(503), json_response(200, ORGANIZATION_BODY)
    )
    client = make_client(recorder)

    client.organization.get()

    ids = {request.headers["X-Request-ID"] for request in recorder.requests}
    assert len(recorder.requests) == 3
    assert len(ids) == 1


def test_the_exception_of_the_last_try_is_raised() -> None:
    """A 503 and then a timeout give APITimeoutError."""
    recorder = Recorder(httpx.Response(503), httpx.ReadTimeout("slow"))
    client = make_client(recorder, max_retries=1)

    with pytest.raises(APITimeoutError):
        client.organization.get()

    assert len(recorder.requests) == 2


async def test_the_async_client_retries_the_same_way(sleeps: list[float]) -> None:
    """The async client sends a GET again after a 503, and waits with asyncio."""
    recorder = Recorder(httpx.Response(503), json_response(200, ORGANIZATION_BODY))
    client = make_async_client(recorder)

    organization = await client.organization.get()

    assert organization.name == "Acme Estates"
    assert len(recorder.requests) == 2
    assert sleeps == [0.5]


async def test_the_async_client_raises_after_the_last_try() -> None:
    """The async client gives the exception of the last try."""
    recorder = Recorder(httpx.ConnectError("no route"))
    client = make_async_client(recorder, max_retries=1)

    with pytest.raises(askpilot.APIConnectionError):
        await client.organization.get()

    assert len(recorder.requests) == 2


# ---------------------------------------------------------------------------
# The log lines.
# ---------------------------------------------------------------------------


def test_each_try_writes_1_debug_line(caplog: pytest.LogCaptureFixture) -> None:
    """The line holds the method, the path, the status, the time, the id, and the try."""
    caplog.set_level(logging.DEBUG, logger="askpilot")
    headers = {"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "59"}
    recorder = Recorder(httpx.Response(503), json_response(200, ORGANIZATION_BODY, headers))
    client = make_client(recorder)

    client.organization.get()

    lines = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    request_id = recorder.requests[0].headers["X-Request-ID"]
    assert len(lines) == 2
    assert "GET /v1/organization 503" in lines[0]
    assert "try 1/3" in lines[0]
    assert request_id in lines[0]
    assert " ms" in lines[0]
    assert "GET /v1/organization 200" in lines[1]
    assert "try 2/3" in lines[1]
    assert "59/60" in lines[1]


def test_a_try_with_no_answer_writes_a_debug_line_with_no_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A timeout has no status, and the line says so."""
    caplog.set_level(logging.DEBUG, logger="askpilot")
    recorder = Recorder(httpx.ReadTimeout("slow"))
    client = make_client(recorder, max_retries=0)

    with pytest.raises(APITimeoutError):
        client.organization.get()

    lines = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert len(lines) == 1
    assert "GET /v1/organization timeout" in lines[0]
    assert "try 1/1" in lines[0]


def test_a_retry_writes_1_warning_line_with_the_cause_and_the_wait(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The line names the cause and the wait, before the sleep."""
    caplog.set_level(logging.DEBUG, logger="askpilot")
    recorder = Recorder(
        httpx.Response(503),
        httpx.ConnectError("no route"),
        json_response(200, ORGANIZATION_BODY),
    )
    client = make_client(recorder)

    client.organization.get()

    warnings = [
        record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert len(warnings) == 2
    assert "status 503" in warnings[0]
    assert "0.5 s" in warnings[0]
    assert "connection error" in warnings[1]
    assert "1.0 s" in warnings[1]
    assert all(record.name == "askpilot" for record in caplog.records)


def test_no_log_line_holds_a_header_value_or_a_query_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The lines hold no key, no header value, and no query value."""
    caplog.set_level(logging.DEBUG, logger="askpilot")
    recorder = Recorder(
        httpx.Response(503, headers={"X-Secret": "header-secret"}),
        json_response(200, PAGE_BODY, {"X-Secret": "header-secret"}),
    )
    client = make_client(recorder)

    client.workflows.list(search="query-secret", cursor="cursor-secret")

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "/v1/workflows" in text
    assert "query-secret" not in text
    assert "cursor-secret" not in text
    assert "header-secret" not in text
    assert API_KEY not in text
    assert "Bearer" not in text


def test_the_logger_is_named_askpilot_and_holds_a_null_handler() -> None:
    """A library logger holds a NullHandler, so an app with no logging setup stays quiet."""
    logger = logging.getLogger("askpilot")

    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)
