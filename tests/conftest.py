"""The fixtures of the suite.

Each test of a client uses `httpx.MockTransport`: no test connects to a network,
and no test waits. The 2 autouse fixtures below replace the sleep of the
clients and guard the API key of the fixtures: after each test, the key must
be in no log record and in no exception text.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from askpilot import _client
from askpilot._client import Askpilot, AsyncAskpilot
from askpilot.errors import AskpilotError

# The test vector of public-api. The key is not real, and it belongs to no
# organization.
API_KEY = "ask_0123456789abcdefghijklmnopqrstuvwxyzABCDEFG"
BASE_URL = "https://api.askpilot.test"

# Fixed ids for the tests. They are not real.
ORGANIZATION_ID = "2b1a0f9e-8d7c-4b6a-9f5e-4d3c2b1a0f9e"
WORKFLOW_ID = "018f2c1e-8a4b-7c3d-9e5f-1a2b3c4d5e6f"
SESSION_ID = "5e4f3a2b-1c0d-4e9f-8a7b-6c5d4e3f2a1b"
START_ID = "8b7c6d5e-4f3a-4b2c-9d1e-0f9a8b7c6d5e"
REQUEST_ID = "7c6d5e4f-3a2b-4c1d-8e9f-0a1b2c3d4e5f"

ORGANIZATION_BODY: dict[str, Any] = {"id": ORGANIZATION_ID, "name": "Acme Estates"}

# The workflow object of the API reference, with each of its 11 fields.
WORKFLOW_BODY: dict[str, Any] = {
    "id": WORKFLOW_ID,
    "name": "inbound-lead-handler",
    "description": "Qualifies inbound leads and books a viewing.",
    "scope": "company_wide",
    "is_active": True,
    "auto_run": {"enabled": True, "frequency": "daily"},
    "users": [{"email": "jane@acme-estates.example", "name": "Jane Doe"}],
    "triggers": [
        {
            "id": "6f5e4d3c-2b1a-4f9e-8d7c-6b5a4f3e2d1c",
            "name": "",
            "is_active": True,
            "trigger_source": {"slug": "api", "name": "API"},
            "events": [{"slug": "workflow.start_via_api", "name": "Start workflow via the API"}],
            "filters": None,
            "input_message": "",
            "subagent_sources": [
                {"id": "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d", "name": "API", "type": "api"},
                {
                    "id": "1e0f9a8b-7c6d-4e5f-9a3b-2c1d0e9f8a7b",
                    "name": "Street CRM",
                    "type": "street",
                },
                {"id": None, "name": "web-research", "type": "platform_internal"},
            ],
        }
    ],
    "files": [
        {"id": "2c1d0e9f-8a7b-4c6d-9e5f-4a3b2c1d0e9f", "name": "PROCESS.md", "path": []},
        {"id": "4a3b2c1d-0e9f-4a7b-8c6d-5e4f3a2b1c0d", "name": "faq.md", "path": ["reference"]},
    ],
    "created_at": "2026-09-01T09:12:33.418272Z",
    "updated_at": "2026-09-06T15:40:02.000913Z",
}

PAGE_BODY: dict[str, Any] = {
    "data": [WORKFLOW_BODY],
    "pagination": {"next_cursor": None, "has_more": False},
}

START_BODY: dict[str, Any] = {"id": START_ID, "workflow_id": WORKFLOW_ID, "session_id": SESSION_ID}


def error_body(
    code: str,
    message: str = "Something is not right.",
    request_id: str = REQUEST_ID,
    details: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Make the error envelope of the API.

    Args:
        code: The error code.
        message: The message for a person.
        request_id: The id of the request.
        details: The field errors of a 422, or None.

    Returns:
        The body, with `details` only when given.
    """
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details is not None:
        error["details"] = details
    return {"error": error}


def json_response(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    """Make a JSON answer for the mock transport.

    Args:
        status: The status code.
        body: The JSON body.
        headers: More headers, or None.

    Returns:
        The answer.
    """
    return httpx.Response(status, json=body, headers=headers)


class Recorder:
    """A handler for `httpx.MockTransport`.

    It keeps each request that arrives, and it gives the scripted answers in
    order. The last answer repeats. An answer that is an exception is raised,
    so a test can script a timeout or a connection error.
    """

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        """Keep the answers.

        Args:
            answers: The answers, in order. At least 1.
        """
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        """Keep the request and give the next answer.

        Args:
            request: The request of the client.

        Returns:
            The next scripted answer.

        Raises:
            Exception: The next scripted answer, when it is an exception.
        """
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def request(self) -> httpx.Request:
        """The only request, for a test that expects 1."""
        assert len(self.requests) == 1, f"{len(self.requests)} requests arrived, and not 1"
        return self.requests[0]


def make_client(recorder: Recorder, **kwargs: Any) -> Askpilot:
    """Make a sync client on the mock transport.

    Args:
        recorder: The handler of the transport.
        kwargs: More constructor arguments, `max_retries` for example.

    Returns:
        The client, with the fixture key and the fixture base URL.
    """
    transport = httpx.MockTransport(recorder)
    return Askpilot(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=httpx.Client(transport=transport),
        **kwargs,
    )


def make_client_with_handler(handler: Callable[[httpx.Request], httpx.Response]) -> Askpilot:
    """Make a sync client on a mock transport with a handler function.

    Args:
        handler: The function that answers each request.

    Returns:
        The client, with the fixture key and the fixture base URL.
    """
    return Askpilot(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def make_async_client(recorder: Recorder, **kwargs: Any) -> AsyncAskpilot:
    """Make an async client on the mock transport.

    Args:
        recorder: The handler of the transport.
        kwargs: More constructor arguments.

    Returns:
        The client, with the fixture key and the fixture base URL.
    """
    transport = httpx.MockTransport(recorder)
    return AsyncAskpilot(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=httpx.AsyncClient(transport=transport),
        **kwargs,
    )


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the 2 sleep functions of the clients, and record each wait.

    No test waits. A test of the retries reads the list.
    """
    waits: list[float] = []

    async def record_async(wait: float) -> None:
        waits.append(wait)

    monkeypatch.setattr(_client, "_sleep", waits.append)
    monkeypatch.setattr(_client, "_async_sleep", record_async)
    return waits


class _ListHandler(logging.Handler):
    """A log handler that keeps each record in a list."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def guarded_key() -> str:
    """The key that must reach no log line and no exception. The live tests give their own."""
    return API_KEY


@pytest.fixture(autouse=True)
def key_guard(monkeypatch: pytest.MonkeyPatch, guarded_key: str) -> Iterator[None]:
    """Make sure that the key reaches no log line and no exception.

    The fixture keeps each record of the logger `askpilot` at DEBUG, and each
    exception of the SDK that the test makes. After the test, it looks for the
    key in the message of each record and in the text of each exception.
    """
    handler = _ListHandler()
    logger = logging.getLogger("askpilot")
    logger.addHandler(handler)
    old_level = logger.level
    logger.setLevel(logging.DEBUG)

    raised: list[AskpilotError] = []
    original_init = AskpilotError.__init__

    def recording_init(self: AskpilotError, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)
        raised.append(self)

    monkeypatch.setattr(AskpilotError, "__init__", recording_init)

    yield

    logger.removeHandler(handler)
    logger.setLevel(old_level)
    texts = [record.getMessage() for record in handler.records]
    for error in raised:
        texts.extend((str(error), repr(error), repr(error.args)))
    leaks = [text for text in texts if guarded_key and guarded_key in text]
    assert leaks == [], f"The API key reached a log line or an exception text: {leaks}"
