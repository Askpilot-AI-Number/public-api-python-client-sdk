"""The exceptions that the SDK raises.

Every exception is a subclass of AskpilotError, so one except clause catches
them all::

    AskpilotError
    ├── ConfigurationError          a bad api_key or base_url when you create the client
    ├── APIConnectionError          no HTTP response, even after the retries
    │   └── APITimeoutError         the response didn't arrive in time
    └── APIError                    an HTTP response that isn't a success
        ├── InvalidRequestError     400 and 422, with the failed fields in details
        ├── AuthenticationError     401
        ├── PermissionDeniedError   403
        ├── NotFoundError           404
        ├── ConflictError           409
        ├── RateLimitError          429, with retry_after
        ├── ServerError             500 to 599
        └── UnexpectedResponseError a response the SDK can't read

The class comes from the HTTP status. The error code from the response stays
on the exception, so you can match on it, for example
``error.code == "workflow_inactive"`` on a ConflictError. These are the codes
the API documents today:

==============================  ======  =====================
Code                            Status  Exception
==============================  ======  =====================
bad_request                     400     InvalidRequestError
unauthorized                    401     AuthenticationError
forbidden                       403     PermissionDeniedError
not_found                       404     NotFoundError
method_not_allowed              405     APIError
workflow_inactive               409     ConflictError
api_trigger_not_configured      409     ConflictError
workflow_owner_missing          409     ConflictError
session_not_open                409     ConflictError
conflict                        409     ConflictError
validation_error (with details) 422     InvalidRequestError
invalid_cursor                  422     InvalidRequestError
rate_limited                    429     RateLimitError
internal_error                  500     ServerError
service_unavailable             503     ServerError
==============================  ======  =====================

No exception message ever contains your API key.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from askpilot.models import FieldError


class AskpilotError(Exception):
    """The base class of every error the SDK raises.

    Catch this class to handle every failure in one place.

    Attributes:
        message: A human-readable explanation of what went wrong.
        request_id: The id of the request, when there is one. Include it when
            you contact support.
    """

    def __init__(self, message: str, *, request_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id


class ConfigurationError(AskpilotError):
    """The client couldn't be set up.

    The API key or the base URL is missing or not valid, or an option is out
    of range. The message names the rule that failed. It never contains the
    key.
    """


class APIConnectionError(AskpilotError):
    """The request never got an HTTP response, even after the retries.

    The cause is a network problem: the host can't be reached, the connection
    dropped, or a proxy refused it. The original network error is available as
    ``__cause__``.
    """


class APITimeoutError(APIConnectionError):
    """The response didn't arrive within the timeout."""


class APIError(AskpilotError):
    """The API responded with an error status.

    Attributes:
        status_code: The HTTP status of the response.
        code: The error code from the response, such as not_found. It's None
            when the body wasn't in the standard error format, for example a
            page from a proxy.
        message: A human-readable explanation. This text may change, so don't
            match on it.
        request_id: The id of the request. Include it when you contact support.
        details: The fields that failed validation. It's empty unless the
            status is 422.
        body: The first 1,000 characters of the response body, for a support
            request.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Iterable[FieldError]] = None,
        body: str = "",
    ) -> None:
        super().__init__(message, request_id=request_id)
        self.status_code = status_code
        self.code = code
        self.details: list[FieldError] = list(details or [])
        self.body = body

    def __str__(self) -> str:
        code = f" {self.code}" if self.code else ""
        request_id = f" (request_id={self.request_id})" if self.request_id else ""
        return f"{self.status_code}{code}: {self.message}{request_id}"

    # BaseException rebuilds an exception with `type(error)(*error.args)`, and
    # `args` holds the message only. So pickle and copy would call `__init__`
    # without `status_code`. This rebuild goes through `_rebuild` instead, and
    # the constructor keeps its signature: it is part of the public surface.
    def __reduce__(self) -> tuple[Any, ...]:
        return (_rebuild, (type(self), self.message, dict(vars(self))))


def _rebuild(cls: type[APIError], message: str, state: dict[str, Any]) -> APIError:
    """Give an exception back from its class, its message, and its state.

    pickle and copy call this function. `cls.__new__(cls, message)` makes the
    exception with `args` equal to `(message,)`, without a call of `__init__`,
    and the state holds each attribute, also 1 that a caller added.
    """
    error = cls.__new__(cls, message)
    error.__dict__.update(state)
    return error


class InvalidRequestError(APIError):
    """The request was rejected: status 400 or 422.

    On a 422, ``details`` lists each field that failed validation.
    """


class AuthenticationError(APIError):
    """The API key is missing, revoked, expired, or not valid: status 401."""


class PermissionDeniedError(APIError):
    """The API key doesn't have the scope this operation needs: status 403."""


class NotFoundError(APIError):
    """The resource doesn't exist in your organization: status 404."""


class ConflictError(APIError):
    """The current state of the resource doesn't allow the action: status 409.

    Check ``code`` to see which rule applies, for example workflow_inactive.
    """


class RateLimitError(APIError):
    """Your organization sent too many requests: status 429.

    Wait for ``retry_after`` seconds before you send the next request.

    Attributes:
        retry_after: How many seconds to wait, from the Retry-After header.
        limit: How many requests the current period allows.
        remaining: How many requests are left in the current period.
        reset: When the current period ends, in Unix seconds.

    Each attribute is None when the response didn't include its header.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Iterable[FieldError]] = None,
        body: str = "",
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None,
        reset: Optional[int] = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            code=code,
            request_id=request_id,
            details=details,
            body=body,
        )
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset = reset


class ServerError(APIError):
    """Something went wrong on the Askpilot side: status 500 to 599.

    A 503 means the service can't take the request right now. Try again later.
    """


class UnexpectedResponseError(APIError):
    """The SDK couldn't read the response.

    This happens when a successful status comes with a body that isn't the
    expected JSON, or when the status is one the API never sends, such as a
    redirect. ``body`` holds the start of what came back.
    """
