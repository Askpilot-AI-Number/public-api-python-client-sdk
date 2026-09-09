"""The request, the response, and the retry decision.

The 2 clients share the functions of this module. Each function takes values
and gives a value, and it keeps no state. The sync client and the async client
add the send and the sleep only.
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Final, Optional, TypeVar, Union

import httpx
import pydantic

from askpilot.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
)
from askpilot.models import ErrorBody, ErrorResponse

logger = logging.getLogger("askpilot")
# A library adds a NullHandler: an application that configures logging sees
# the lines, and an application that does not stays quiet.
logger.addHandler(logging.NullHandler())

#: The version that the SDK reports when the package metadata is not there.
FALLBACK_VERSION: Final[str] = "0.0.0+unknown"


def read_version() -> str:
    """Give the version of the package from its metadata.

    The version is in pyproject.toml only, and the metadata of the installed
    package holds it. An application with no package metadata, a frozen
    application for example, gets the fallback value, so the import of the SDK
    does not stop there.

    Returns:
        The version, or `0.0.0+unknown` without the metadata.
    """
    try:
        return version("askpilot")
    except PackageNotFoundError:
        return FALLBACK_VERSION


SDK_VERSION: Final[str] = read_version()

USER_AGENT: Final[str] = (
    f"askpilot-python/{SDK_VERSION} "
    f"python/{sys.version_info.major}.{sys.version_info.minor} httpx/{httpx.__version__}"
)

REQUEST_ID_HEADER: Final[str] = "X-Request-ID"

#: A GET is sent again after 1 of these. A POST is sent again after a 429 only.
RETRY_STATUSES_OF_A_GET: Final[frozenset[int]] = frozenset({502, 503, 504})
RATE_LIMITED: Final[int] = 429

#: The wait before the first, the second, and each later retry, in seconds,
#: when the answer holds no usable Retry-After.
BACKOFF_SECONDS: Final[tuple[float, ...]] = (0.5, 1.0, 2.0)
MAX_RETRY_AFTER_SECONDS: Final[int] = 60

#: The number of characters of the body that an exception keeps.
BODY_EXCERPT_LENGTH: Final[int] = 1000

# The class of each status that has 1 of its own. 5xx gives ServerError, each
# other 4xx gives APIError, and 1xx and 3xx give UnexpectedResponseError.
_STATUS_CLASSES: Final[dict[int, type[APIError]]] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: InvalidRequestError,
    429: RateLimitError,
}

ModelT = TypeVar("ModelT", bound=pydantic.BaseModel)

#: What 1 try gives: an answer, or the failure that stopped the request.
#:
#: This is an assignment and not an annotation, so Python evaluates it at run
#: time. `from __future__ import annotations` above does not reach it, and
#: Python 3.9 gives a TypeError for `X | Y`. So the alias uses `Union`.
Outcome = Union[httpx.Response, APIConnectionError]


def new_request_id() -> str:
    """Give the X-Request-ID of 1 call. The service echoes it in each answer."""
    return str(uuid.uuid4())


def build_request(
    *,
    base_url: str,
    api_key: str,
    method: str,
    path: str,
    request_id: str,
    timeout: httpx.Timeout,
    query: Optional[Mapping[str, Any]] = None,
    body: Optional[Mapping[str, Any]] = None,
) -> httpx.Request:
    """Make the request of 1 call.

    The URL is absolute, and the 4 headers are the headers of the SDK. The
    timeout goes on the request, so it applies also when the caller gave the
    httpx client.

    Args:
        base_url: The base URL of the API, with no trailing slash.
        api_key: The API key.
        method: `GET` or `POST`.
        path: The path of the operation, `/v1/organization` for example.
        request_id: The value of the X-Request-ID header.
        timeout: The timeout of the request.
        query: The query parameters, or None.
        body: The JSON body of a POST, or None.

    Returns:
        The request, ready for `send`.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        REQUEST_ID_HEADER: request_id,
    }
    return httpx.Request(
        method,
        f"{base_url}{path}",
        params=query,
        json=body,
        headers=headers,
        extensions={"timeout": timeout.as_dict()},
    )


def transport_failure(error: httpx.HTTPError, request_id: str) -> APIConnectionError:
    """Turn an httpx error into the exception of the SDK.

    Args:
        error: The httpx error of the send.
        request_id: The id of the request that failed.

    Returns:
        APITimeoutError for a timeout, else APIConnectionError. The httpx error
        is the cause of the exception, and the message holds no detail of it.
    """
    failure: APIConnectionError
    if isinstance(error, httpx.TimeoutException):
        failure = APITimeoutError(
            "Askpilot didn't respond within the timeout. Try again, or give the client a "
            "longer timeout.",
            request_id=request_id,
        )
    else:
        failure = APIConnectionError(
            "A network error stopped the request before Askpilot responded. Check your "
            "connection and the base URL, then try again.",
            request_id=request_id,
        )
    failure.__cause__ = error
    return failure


def retry_wait(method: str, attempt: int, max_retries: int, outcome: Outcome) -> Optional[float]:
    """Decide whether to send the request again, and how long to wait first.

    A GET is sent again after a connection error, a timeout, a 502, a 503, or
    a 504. A request of any method is sent again after a 429: the service
    refused it before any work. Nothing else is sent again.

    Args:
        method: The method of the request.
        attempt: The number of the try that just ended, from 0.
        max_retries: The number of tries after the first.
        outcome: The answer of the try, or the failure that stopped it.

    Returns:
        The wait in seconds, or None when the request is not sent again.
    """
    if attempt >= max_retries:
        return None
    if isinstance(outcome, APIConnectionError):
        if method != "GET":
            return None
        return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]
    status = outcome.status_code
    if status == RATE_LIMITED:
        retry_after = _header_int(outcome.headers, "Retry-After")
        if retry_after is not None and retry_after >= 0:
            return float(min(retry_after, MAX_RETRY_AFTER_SECONDS))
    elif method != "GET" or status not in RETRY_STATUSES_OF_A_GET:
        return None
    return BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)]


def parse_response(response: httpx.Response, model: type[ModelT], request_id: str) -> ModelT:
    """Turn the answer into a model, or raise the exception of the answer.

    Args:
        response: The answer of the last try.
        model: The model of a success.
        request_id: The id that the SDK sent.

    Returns:
        The model, for a 2xx with a body that the model accepts.

    Raises:
        UnexpectedResponseError: A 2xx body that is not JSON or that the model
            refuses, and each 1xx and 3xx.
        APIError: A 4xx or a 5xx, as the class of the status.
    """
    status = response.status_code
    if 200 <= status < 300:
        try:
            return model.model_validate(response.json())
        except (ValueError, pydantic.ValidationError) as error:
            raise UnexpectedResponseError(
                _unexpected_message(status),
                status_code=status,
                request_id=response.headers.get(REQUEST_ID_HEADER) or request_id,
                body=_excerpt(response),
            ) from error
    raise error_from_response(response, request_id)


def error_from_response(response: httpx.Response, request_id: str) -> APIError:
    """Make the exception of an answer that is not a success.

    Args:
        response: The answer.
        request_id: The id that the SDK sent.

    Returns:
        The exception of the status, with the fields of the envelope when the
        body is the envelope, and with `code` None otherwise.
    """
    status = response.status_code
    envelope = _envelope_of(response)
    if envelope is None:
        code, message, details, body_request_id = None, _unexpected_message(status), [], None
    else:
        code, message = envelope.code, envelope.message
        details, body_request_id = envelope.details or [], envelope.request_id
    resolved_id = body_request_id or response.headers.get(REQUEST_ID_HEADER) or request_id
    excerpt = _excerpt(response)
    if status == RATE_LIMITED:
        return RateLimitError(
            message,
            status_code=status,
            code=code,
            request_id=resolved_id,
            details=details,
            body=excerpt,
            retry_after=_header_int(response.headers, "Retry-After"),
            limit=_header_int(response.headers, "X-RateLimit-Limit"),
            remaining=_header_int(response.headers, "X-RateLimit-Remaining"),
            reset=_header_int(response.headers, "X-RateLimit-Reset"),
        )
    error_class = _STATUS_CLASSES.get(status)
    if error_class is None:
        if 500 <= status < 600:
            error_class = ServerError
        elif 400 <= status < 500:
            error_class = APIError
        else:
            error_class = UnexpectedResponseError
    return error_class(
        message,
        status_code=status,
        code=code,
        request_id=resolved_id,
        details=details,
        body=excerpt,
    )


def log_attempt(
    method: str,
    path: str,
    request_id: str,
    attempt: int,
    tries: int,
    started: float,
    outcome: Outcome,
) -> None:
    """Write the DEBUG line of 1 try.

    The line holds the method, the path, the status, the duration, the request
    id, the try number, and the rate-limit values when the answer holds them.
    It holds no header value, no body, no query value, and no key.

    Args:
        method: The method of the request.
        path: The path of the request, with no query string.
        request_id: The id of the call.
        attempt: The number of the try, from 0.
        tries: The number of tries of the call.
        started: The `time.monotonic()` value at the start of the try.
        outcome: The answer of the try, or the failure that stopped it.
    """
    elapsed_ms = int((time.monotonic() - started) * 1000)
    rate_limit = ""
    if isinstance(outcome, httpx.Response):
        status = str(outcome.status_code)
        remaining = outcome.headers.get("X-RateLimit-Remaining")
        limit = outcome.headers.get("X-RateLimit-Limit")
        if remaining is not None and limit is not None:
            rate_limit = f", rate limit remaining {remaining}/{limit}"
    else:
        status = _cause_of(outcome)
    logger.debug(
        "%s %s %s in %d ms (request_id=%s, try %d/%d%s)",
        method,
        path,
        status,
        elapsed_ms,
        request_id,
        attempt + 1,
        tries,
        rate_limit,
    )


def log_retry(
    method: str,
    path: str,
    request_id: str,
    attempt: int,
    tries: int,
    wait: float,
    outcome: Outcome,
) -> None:
    """Write the WARNING line before a retry: the cause and the wait.

    Args:
        method: The method of the request.
        path: The path of the request, with no query string.
        request_id: The id of the call.
        attempt: The number of the try that just ended, from 0.
        tries: The number of tries of the call.
        wait: The wait before the next try, in seconds.
        outcome: The answer of the try, or the failure that stopped it.
    """
    cause = (
        f"status {outcome.status_code}"
        if isinstance(outcome, httpx.Response)
        else f"a {_cause_of(outcome)}"
    )
    logger.warning(
        "Retrying %s %s in %.1f s after %s (request_id=%s, try %d/%d)",
        method,
        path,
        wait,
        cause,
        request_id,
        attempt + 1,
        tries,
    )


def _cause_of(failure: APIConnectionError) -> str:
    """Name the failure of a try for a log line."""
    return "timeout" if isinstance(failure, APITimeoutError) else "connection error"


def _unexpected_message(status: int) -> str:
    """Give the message of an answer whose body is not the envelope."""
    return f"The server returned an unexpected response (status {status})."


def _envelope_of(response: httpx.Response) -> Optional[ErrorBody]:
    """Read the error envelope of an answer, or give None when the body is not it."""
    try:
        return ErrorResponse.model_validate(response.json()).error
    except (ValueError, pydantic.ValidationError):
        return None


def _excerpt(response: httpx.Response) -> str:
    """Give the first characters of the body, for a support request."""
    return response.text[:BODY_EXCERPT_LENGTH]


def _header_int(headers: httpx.Headers, name: str) -> Optional[int]:
    """Read an integer header, or give None when the header is missing or not a number."""
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
