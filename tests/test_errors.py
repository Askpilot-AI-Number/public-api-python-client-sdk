"""The exceptions of the SDK.

Each test sends 1 request through a client on the mock transport, so the tests
show what a caller sees: the class, the fields, and the text of the exception.
"""

import copy
import json
import pickle
from collections.abc import Callable

import httpx
import pytest

from askpilot.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AskpilotError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
)
from askpilot.models import FieldError
from tests.conftest import (
    API_KEY,
    ORGANIZATION_BODY,
    REQUEST_ID,
    Recorder,
    error_body,
    json_response,
    make_client,
    make_client_with_handler,
)


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (ConfigurationError, AskpilotError),
        (APIConnectionError, AskpilotError),
        (APITimeoutError, APIConnectionError),
        (APIError, AskpilotError),
        (InvalidRequestError, APIError),
        (AuthenticationError, APIError),
        (PermissionDeniedError, APIError),
        (NotFoundError, APIError),
        (ConflictError, APIError),
        (RateLimitError, APIError),
        (ServerError, APIError),
        (UnexpectedResponseError, APIError),
    ],
)
def test_the_hierarchy_holds_each_parent(child: type, parent: type) -> None:
    """Each class of the SDK is under AskpilotError, in the documented tree."""
    assert issubclass(child, parent)
    assert issubclass(child, AskpilotError)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, InvalidRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (422, InvalidRequestError),
        (429, RateLimitError),
        (500, ServerError),
        (503, ServerError),
        (599, ServerError),
    ],
)
def test_each_status_gives_its_class(status: int, expected: type[APIError]) -> None:
    """The class comes from the status code, and not from the error code."""
    client = make_client(Recorder(json_response(status, error_body("some_code"))), max_retries=0)

    with pytest.raises(expected) as raised:
        client.organization.get()

    assert type(raised.value) is expected
    assert raised.value.status_code == status


@pytest.mark.parametrize("status", [405, 418, 451])
def test_an_unmapped_4xx_gives_the_base_api_error(status: int) -> None:
    """A 4xx with no class of its own gives APIError, and the code stays on it."""
    client = make_client(Recorder(json_response(status, error_body("method_not_allowed"))))

    with pytest.raises(APIError) as raised:
        client.organization.get()

    assert type(raised.value) is APIError
    assert raised.value.code == "method_not_allowed"


def test_the_envelope_fields_reach_the_exception() -> None:
    """code, message, request_id, and body come from the answer; details is empty."""
    body = error_body("not_found", "The resource does not exist.")
    client = make_client(Recorder(json_response(404, body)))

    with pytest.raises(NotFoundError) as raised:
        client.organization.get()

    error = raised.value
    assert error.status_code == 404
    assert error.code == "not_found"
    assert error.message == "The resource does not exist."
    assert error.request_id == REQUEST_ID
    assert error.details == []
    assert json.loads(error.body) == body


def test_str_gives_the_status_the_code_the_message_and_the_request_id() -> None:
    """str(error) is '<status> <code>: <message> (request_id=<id>)'."""
    client = make_client(
        Recorder(json_response(404, error_body("not_found", "The resource does not exist.")))
    )

    with pytest.raises(NotFoundError) as raised:
        client.organization.get()

    assert str(raised.value) == (
        f"404 not_found: The resource does not exist. (request_id={REQUEST_ID})"
    )


def test_the_details_of_a_422_become_field_errors() -> None:
    """InvalidRequestError.details holds 1 FieldError for each entry."""
    details = [{"field": "context", "code": "string_too_short", "message": "Too short."}]
    client = make_client(
        Recorder(json_response(422, error_body("validation_error", details=details)))
    )

    with pytest.raises(InvalidRequestError) as raised:
        client.organization.get()

    assert raised.value.details == [
        FieldError(field="context", code="string_too_short", message="Too short.")
    ]


def test_a_409_code_stays_on_conflict_error() -> None:
    """A caller matches error.code on a ConflictError."""
    client = make_client(Recorder(json_response(409, error_body("workflow_inactive"))))

    with pytest.raises(ConflictError) as raised:
        client.organization.get()

    assert raised.value.code == "workflow_inactive"


def test_invalid_cursor_gives_invalid_request_error() -> None:
    """A 422 with the code invalid_cursor gives InvalidRequestError with no details."""
    client = make_client(Recorder(json_response(422, error_body("invalid_cursor"))))

    with pytest.raises(InvalidRequestError) as raised:
        client.organization.get()

    assert raised.value.code == "invalid_cursor"
    assert raised.value.details == []


def test_the_body_is_cut_at_1000_characters() -> None:
    """The body excerpt is for a support request, and it is not the full answer."""
    long_text = "x" * 5000
    client = make_client(Recorder(httpx.Response(502, text=long_text)))

    with pytest.raises(ServerError) as raised:
        client.organization.get()

    assert len(raised.value.body) == 1000
    assert raised.value.body == "x" * 1000


def test_an_error_body_that_is_not_the_envelope_gives_code_none() -> None:
    """A proxy page gives the class of the status, code None, and a fixed message."""
    client = make_client(Recorder(httpx.Response(502, text="<html>Bad gateway</html>")))

    with pytest.raises(ServerError) as raised:
        client.organization.get()

    error = raised.value
    assert error.code is None
    assert error.message == "The server returned an unexpected response (status 502)."
    assert error.body == "<html>Bad gateway</html>"
    assert str(error) == (
        f"502: The server returned an unexpected response (status 502). "
        f"(request_id={error.request_id})"
    )


def test_an_empty_error_body_gives_code_none() -> None:
    """An empty body is not the envelope."""
    client = make_client(Recorder(httpx.Response(404)))

    with pytest.raises(NotFoundError) as raised:
        client.organization.get()

    assert raised.value.code is None
    assert raised.value.body == ""


def test_request_id_comes_from_the_envelope_first() -> None:
    """The envelope wins over the header."""
    client = make_client(
        Recorder(
            json_response(
                404,
                error_body("not_found", request_id="from-body"),
                {"X-Request-ID": "from-header"},
            )
        )
    )

    with pytest.raises(NotFoundError) as raised:
        client.organization.get()

    assert raised.value.request_id == "from-body"


def test_request_id_comes_from_the_header_when_the_body_is_not_the_envelope() -> None:
    """The header wins over the id that the SDK sent."""
    client = make_client(
        Recorder(httpx.Response(502, text="nope", headers={"X-Request-ID": "from-header"}))
    )

    with pytest.raises(ServerError) as raised:
        client.organization.get()

    assert raised.value.request_id == "from-header"


def test_request_id_is_the_id_sent_when_the_answer_holds_none() -> None:
    """Without an envelope and without the header, the id of the request stays."""
    recorder = Recorder(httpx.Response(502, text="nope"))
    client = make_client(recorder)

    with pytest.raises(ServerError) as raised:
        client.organization.get()

    assert raised.value.request_id == recorder.requests[0].headers["X-Request-ID"]


def test_rate_limit_error_reads_the_4_headers() -> None:
    """retry_after, limit, remaining, and reset come from the headers."""
    headers = {
        "Retry-After": "38",
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "1788527160",
    }
    client = make_client(
        Recorder(json_response(429, error_body("rate_limited"), headers)), max_retries=0
    )

    with pytest.raises(RateLimitError) as raised:
        client.organization.get()

    error = raised.value
    assert error.code == "rate_limited"
    assert error.retry_after == 38
    assert error.limit == 60
    assert error.remaining == 0
    assert error.reset == 1788527160


def test_rate_limit_error_gives_none_for_a_missing_or_bad_header() -> None:
    """A header that is missing or not a number gives None, and never an exception."""
    headers = {"Retry-After": "soon", "X-RateLimit-Limit": "60"}
    client = make_client(
        Recorder(json_response(429, error_body("rate_limited"), headers)), max_retries=0
    )

    with pytest.raises(RateLimitError) as raised:
        client.organization.get()

    error = raised.value
    assert error.retry_after is None
    assert error.limit == 60
    assert error.remaining is None
    assert error.reset is None


# ---------------------------------------------------------------------------
# Unexpected answers. The SDK raises an AskpilotError for each failure, and never
# a pydantic, httpx, or json exception.
# ---------------------------------------------------------------------------


def test_a_2xx_body_that_is_not_json_gives_unexpected_response_error() -> None:
    """A 200 with HTML gives UnexpectedResponseError with the status and the excerpt."""
    client = make_client(Recorder(httpx.Response(200, text="<html>Sign in</html>")))

    with pytest.raises(UnexpectedResponseError) as raised:
        client.organization.get()

    assert raised.value.status_code == 200
    assert raised.value.code is None
    assert raised.value.body == "<html>Sign in</html>"


def test_a_2xx_body_that_the_model_refuses_gives_unexpected_response_error() -> None:
    """A 200 with a JSON object that lacks a field gives UnexpectedResponseError."""
    client = make_client(Recorder(json_response(200, {"id": "not-a-uuid"})))

    with pytest.raises(UnexpectedResponseError) as raised:
        client.organization.get()

    assert raised.value.status_code == 200
    assert '"not-a-uuid"' in raised.value.body


def test_an_empty_2xx_body_gives_unexpected_response_error() -> None:
    """A 204 with no body cannot give a model."""
    client = make_client(Recorder(httpx.Response(204)))

    with pytest.raises(UnexpectedResponseError) as raised:
        client.organization.get()

    assert raised.value.status_code == 204


def test_a_1xx_gives_unexpected_response_error() -> None:
    """The service never gives a 1xx."""
    client = make_client(Recorder(httpx.Response(101)))

    with pytest.raises(UnexpectedResponseError) as raised:
        client.organization.get()

    assert raised.value.status_code == 101


def test_a_3xx_gives_unexpected_response_error_and_no_redirect() -> None:
    """The service redirects nothing, so the SDK follows nothing."""
    recorder = Recorder(httpx.Response(302, headers={"Location": "https://elsewhere.test/"}))
    client = make_client(recorder)

    with pytest.raises(UnexpectedResponseError) as raised:
        client.organization.get()

    assert raised.value.status_code == 302
    assert len(recorder.requests) == 1


def test_a_timeout_gives_api_timeout_error() -> None:
    """An httpx timeout becomes APITimeoutError, with the request id."""
    recorder = Recorder(httpx.ReadTimeout("the read timed out"))
    client = make_client(recorder, max_retries=0)

    with pytest.raises(APITimeoutError) as raised:
        client.organization.get()

    assert isinstance(raised.value, APIConnectionError)
    assert raised.value.request_id == recorder.requests[0].headers["X-Request-ID"]
    assert isinstance(raised.value.__cause__, httpx.ReadTimeout)


def test_a_connection_error_gives_api_connection_error() -> None:
    """Each other httpx transport error becomes APIConnectionError."""
    client = make_client(Recorder(httpx.ConnectError("no route to host")), max_retries=0)

    with pytest.raises(APIConnectionError) as raised:
        client.organization.get()

    assert not isinstance(raised.value, APITimeoutError)
    assert isinstance(raised.value.__cause__, httpx.ConnectError)


def test_a_decoding_error_gives_api_connection_error() -> None:
    """An httpx error that is not a transport error still becomes an SDK error."""
    client = make_client(Recorder(httpx.DecodingError("bad gzip")), max_retries=0)

    with pytest.raises(APIConnectionError):
        client.organization.get()


# ---------------------------------------------------------------------------
# Security. The key reaches no exception text and no log line.
# ---------------------------------------------------------------------------


def test_the_key_never_reaches_the_text_of_an_exception(caplog: pytest.LogCaptureFixture) -> None:
    """A server that echoes the credential still gives an exception with no key in its text."""

    def echo(request: httpx.Request) -> httpx.Response:
        credential = request.headers["Authorization"]
        return httpx.Response(
            500, json={"echo": credential}, headers={"X-Echo": credential, "X-Request-ID": "r"}
        )

    client = make_client_with_handler(echo)

    with pytest.raises(ServerError) as raised:
        client.organization.get()

    error = raised.value
    assert API_KEY not in str(error)
    assert API_KEY not in repr(error)
    assert API_KEY not in error.message
    assert all(API_KEY not in record.getMessage() for record in caplog.records)
    assert API_KEY in error.body  # The server sent it back; the excerpt is the answer as it is.


def test_an_exception_holds_no_reference_to_the_answer() -> None:
    """No attribute of the exception is an httpx object, so the credential is not reachable."""
    client = make_client(Recorder(json_response(404, error_body("not_found"))))

    with pytest.raises(NotFoundError) as raised:
        client.organization.get()

    values = list(vars(raised.value).values())
    assert not any(isinstance(value, (httpx.Response, httpx.Request)) for value in values)
    assert not any(isinstance(value, httpx.Headers) for value in values)


def test_configuration_error_is_an_askpilot_error() -> None:
    """A caller can catch every error of the SDK with 1 class."""
    assert issubclass(ConfigurationError, AskpilotError)


def test_a_success_gives_the_model() -> None:
    """The control case: a 200 with the envelope of a success gives no exception."""
    client = make_client(Recorder(json_response(200, ORGANIZATION_BODY)))

    organization = client.organization.get()

    assert organization.name == "Acme Estates"


# ---------------------------------------------------------------------------
# pickle and copy. A caller who runs SDK calls in a process pool gets the
# exception back through pickle, and a framework can copy 1. The constructor
# of APIError takes status_code as a required keyword, so the default
# BaseException rebuild would fail.
# ---------------------------------------------------------------------------


def _not_found() -> NotFoundError:
    """Make a NotFoundError with each attribute set, details included."""
    return NotFoundError(
        "The resource does not exist.",
        status_code=404,
        code="not_found",
        request_id=REQUEST_ID,
        details=[FieldError(field="workflow_id", code="not_found", message="No such workflow.")],
        body='{"error": {"code": "not_found"}}',
    )


def _rate_limited() -> RateLimitError:
    """Make a RateLimitError with the 4 header values set."""
    return RateLimitError(
        "There are too many requests.",
        status_code=429,
        code="rate_limited",
        request_id=REQUEST_ID,
        body='{"error": {"code": "rate_limited"}}',
        retry_after=38,
        limit=60,
        remaining=0,
        reset=1788527160,
    )


def _assert_equal_error(clone: APIError, original: APIError) -> None:
    """Assert that a rebuilt exception holds the class and each attribute of the original."""
    assert clone is not original
    assert type(clone) is type(original)
    assert clone.status_code == original.status_code
    assert clone.code == original.code
    assert clone.message == original.message
    assert clone.request_id == original.request_id
    assert clone.details == original.details
    assert clone.body == original.body
    assert clone.args == original.args
    assert str(clone) == str(original)
    assert vars(clone) == vars(original)
    if isinstance(original, RateLimitError):
        assert isinstance(clone, RateLimitError)
        assert clone.retry_after == original.retry_after
        assert clone.limit == original.limit
        assert clone.remaining == original.remaining
        assert clone.reset == original.reset


@pytest.mark.parametrize("make_error", [_not_found, _rate_limited])
def test_an_api_error_survives_a_pickle_round_trip(make_error: Callable[[], APIError]) -> None:
    """pickle.loads(pickle.dumps(error)) gives an equal exception of the same class."""
    original = make_error()

    clone = pickle.loads(pickle.dumps(original))

    _assert_equal_error(clone, original)


@pytest.mark.parametrize("make_error", [_not_found, _rate_limited])
def test_an_api_error_survives_a_copy(make_error: Callable[[], APIError]) -> None:
    """copy.copy(error) and copy.deepcopy(error) give an equal exception of the same class."""
    original = make_error()

    shallow = copy.copy(original)
    deep = copy.deepcopy(original)

    _assert_equal_error(shallow, original)
    _assert_equal_error(deep, original)
    assert deep.details is not original.details
