"""The 2 clients: `Askpilot` for sync code and `AsyncAskpilot` for async code.

Each client holds the API key in 1 private attribute, makes each request with
an absolute URL and its own headers, and sends it through an httpx client:
1 that the SDK makes, or 1 that the caller gives.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping
from typing import Any, Final, Optional, Union

import httpx

from askpilot._http import (
    ModelT,
    Outcome,
    build_request,
    log_attempt,
    log_retry,
    new_request_id,
    parse_response,
    retry_wait,
    transport_failure,
)
from askpilot._resources import (
    AsyncOrganizationResource,
    AsyncWorkflowsResource,
    OrganizationResource,
    WorkflowsResource,
)
from askpilot.errors import APIConnectionError, ConfigurationError

DEFAULT_BASE_URL: Final[str] = "https://public-api.askpilot.com"
API_KEY_VARIABLE: Final[str] = "ASKPILOT_API_KEY"
BASE_URL_VARIABLE: Final[str] = "ASKPILOT_BASE_URL"
KEY_PREFIX: Final[str] = "ask_"

#: The hosts that take plain http: the local stack has no TLS.
LOCAL_HOSTS: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1"})

# The tests replace these 2 names, so no test waits.
_sleep = time.sleep
_async_sleep = asyncio.sleep


def _resolve_api_key(api_key: Optional[str]) -> str:
    """Give the API key of the client, from the argument or the environment.

    Args:
        api_key: The argument of the constructor, or None.

    Returns:
        The key.

    Raises:
        ConfigurationError: No key in either place, or a key that does not
            start with `ask_`, or a key with white space. The message names the
            rule, and never the key.
    """
    key = api_key if api_key is not None else (os.environ.get(API_KEY_VARIABLE) or None)
    if key is None:
        raise ConfigurationError(
            f"No API key was given. Pass api_key=... to the client, or set the "
            f"{API_KEY_VARIABLE} environment variable."
        )
    if not key.startswith(KEY_PREFIX) or any(character.isspace() for character in key):
        raise ConfigurationError(
            f"The API key must start with {KEY_PREFIX} and must not contain whitespace. "
            f"Check the value you copied from Askpilot."
        )
    return key


def _resolve_base_url(base_url: Optional[str]) -> str:
    """Give the base URL of the client, from the argument, the environment, or the default.

    Args:
        base_url: The argument of the constructor, or None.

    Returns:
        The URL, with no trailing slash.

    Raises:
        ConfigurationError: The URL is not a URL, or its scheme is not https
            and its host is not localhost or 127.0.0.1.
    """
    raw = base_url if base_url is not None else (os.environ.get(BASE_URL_VARIABLE) or None)
    if raw is None:
        raw = DEFAULT_BASE_URL
    url = raw[:-1] if raw.endswith("/") else raw
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL as error:
        raise ConfigurationError(
            "The base URL isn't a valid URL. Use an https URL, or an http URL of localhost "
            "for a local stack."
        ) from error
    local = parsed.scheme == "http" and parsed.host in LOCAL_HOSTS
    if parsed.scheme != "https" and not local:
        raise ConfigurationError(
            "The base URL must use https. Plain http is allowed only for localhost and 127.0.0.1."
        )
    if not parsed.host:
        raise ConfigurationError(
            f"The base URL must include a host, for example {DEFAULT_BASE_URL}."
        )
    return url


def _check_max_retries(max_retries: int) -> int:
    """Refuse a negative number of retries."""
    if max_retries < 0:
        raise ConfigurationError("max_retries must be 0 or more.")
    return max_retries


class Askpilot:
    """The Askpilot API client for synchronous code.

    Create one client and reuse it: it keeps a connection pool. Close it with
    ``close()`` or use it as a context manager.

    Example::

        import askpilot

        with askpilot.Askpilot(api_key="ask_...") as client:
            organization = client.organization.get()

    Args:
        api_key: Your API key. Leave it out to read the ASKPILOT_API_KEY
            environment variable.
        base_url: The URL of the API. Leave it out to read ASKPILOT_BASE_URL,
            or to use https://public-api.askpilot.com. Only https is allowed,
            except for localhost and 127.0.0.1.
        timeout: The timeout of each request, in seconds, or an httpx.Timeout
            for a value per phase. The default is 30 seconds.
        max_retries: How many times a request is sent again after a
            connection error, a timeout, a 429, or a gateway error (502, 503,
            504). The default is 2. Pass 0 to disable retries.
        http_client: Your own httpx.Client, for a proxy, a custom CA, or a
            test transport. You own it: ``close()`` doesn't close it. The SDK
            sets its own URL, headers, and timeout on every request.

    Raises:
        ConfigurationError: The key or the base URL is missing or not valid,
            or max_retries is negative.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: Union[float, httpx.Timeout] = 30.0,
        max_retries: int = 2,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = _resolve_api_key(api_key)
        self._base_url = _resolve_base_url(base_url)
        self._timeout = httpx.Timeout(timeout)
        self._max_retries = _check_max_retries(max_retries)
        self._owns_http = http_client is None
        self._http = http_client if http_client is not None else httpx.Client(timeout=self._timeout)
        self.organization = OrganizationResource(self)
        self.workflows = WorkflowsResource(self)

    def _send(
        self,
        method: str,
        path: str,
        *,
        model: type[ModelT],
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> ModelT:
        """Send 1 call, with the retries, and give the model of the answer."""
        request_id = new_request_id()
        request = build_request(
            base_url=self._base_url,
            api_key=self._api_key,
            method=method,
            path=path,
            request_id=request_id,
            timeout=self._timeout,
            query=query,
            body=body,
        )
        tries = self._max_retries + 1
        attempt = 0
        while True:
            started = time.monotonic()
            outcome: Outcome
            try:
                outcome = self._http.send(request, auth=None, follow_redirects=False)
            except httpx.HTTPError as error:
                outcome = transport_failure(error, request_id)
            log_attempt(method, path, request_id, attempt, tries, started, outcome)
            wait = retry_wait(method, attempt, self._max_retries, outcome)
            if wait is None:
                if isinstance(outcome, APIConnectionError):
                    raise outcome
                return parse_response(outcome, model, request_id)
            log_retry(method, path, request_id, attempt, tries, wait, outcome)
            _sleep(wait)
            attempt += 1

    def close(self) -> None:
        """Close the connection pool, if the SDK created it.

        A client you passed as http_client stays open: you own it.
        """
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Askpilot:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self._base_url!r})"


class AsyncAskpilot:
    """The Askpilot API client for asyncio code.

    Every method is a coroutine, and ``workflows.iterate()`` is an async
    iterator. Close the client with ``aclose()`` or use it as an async
    context manager.

    Example::

        import askpilot

        async with askpilot.AsyncAskpilot(api_key="ask_...") as client:
            organization = await client.organization.get()

    Args:
        api_key: Your API key. Leave it out to read the ASKPILOT_API_KEY
            environment variable.
        base_url: The URL of the API. Leave it out to read ASKPILOT_BASE_URL,
            or to use https://public-api.askpilot.com. Only https is allowed,
            except for localhost and 127.0.0.1.
        timeout: The timeout of each request, in seconds, or an httpx.Timeout
            for a value per phase. The default is 30 seconds.
        max_retries: How many times a request is sent again after a
            connection error, a timeout, a 429, or a gateway error (502, 503,
            504). The default is 2. Pass 0 to disable retries.
        http_client: Your own httpx.AsyncClient, for a proxy, a custom CA, or
            a test transport. You own it: ``aclose()`` doesn't close it. The
            SDK sets its own URL, headers, and timeout on every request.

    Raises:
        ConfigurationError: The key or the base URL is missing or not valid,
            or max_retries is negative.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: Union[float, httpx.Timeout] = 30.0,
        max_retries: int = 2,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._api_key = _resolve_api_key(api_key)
        self._base_url = _resolve_base_url(base_url)
        self._timeout = httpx.Timeout(timeout)
        self._max_retries = _check_max_retries(max_retries)
        self._owns_http = http_client is None
        self._http = (
            http_client if http_client is not None else httpx.AsyncClient(timeout=self._timeout)
        )
        self.organization = AsyncOrganizationResource(self)
        self.workflows = AsyncWorkflowsResource(self)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        model: type[ModelT],
        query: Optional[Mapping[str, Any]] = None,
        body: Optional[Mapping[str, Any]] = None,
    ) -> ModelT:
        """Send 1 call, with the retries, and give the model of the answer."""
        request_id = new_request_id()
        request = build_request(
            base_url=self._base_url,
            api_key=self._api_key,
            method=method,
            path=path,
            request_id=request_id,
            timeout=self._timeout,
            query=query,
            body=body,
        )
        tries = self._max_retries + 1
        attempt = 0
        while True:
            started = time.monotonic()
            outcome: Outcome
            try:
                outcome = await self._http.send(request, auth=None, follow_redirects=False)
            except httpx.HTTPError as error:
                outcome = transport_failure(error, request_id)
            log_attempt(method, path, request_id, attempt, tries, started, outcome)
            wait = retry_wait(method, attempt, self._max_retries, outcome)
            if wait is None:
                if isinstance(outcome, APIConnectionError):
                    raise outcome
                return parse_response(outcome, model, request_id)
            log_retry(method, path, request_id, attempt, tries, wait, outcome)
            await _async_sleep(wait)
            attempt += 1

    async def aclose(self) -> None:
        """Close the connection pool, if the SDK created it.

        A client you passed as http_client stays open: you own it.
        """
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncAskpilot:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self._base_url!r})"
