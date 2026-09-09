"""The 2 clients: the constructor rules, the ownership of the httpx client, and the repr."""

import httpx
import pytest

from askpilot import Askpilot, AsyncAskpilot, ConfigurationError
from tests.conftest import (
    API_KEY,
    BASE_URL,
    ORGANIZATION_BODY,
    Recorder,
    json_response,
    make_client,
)

PRODUCTION_URL = "https://public-api.askpilot.com"


def _mock_http() -> httpx.Client:
    """Make an httpx client that answers each request with the organization."""
    return httpx.Client(
        transport=httpx.MockTransport(Recorder(json_response(200, ORGANIZATION_BODY)))
    )


# ---------------------------------------------------------------------------
# The API key.
# ---------------------------------------------------------------------------


def test_the_key_argument_wins_over_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The argument is used when both exist."""
    monkeypatch.setenv("ASKPILOT_API_KEY", "ask_from-the-environment")
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))

    make_client(recorder).organization.get()

    assert recorder.request.headers["Authorization"] == f"Bearer {API_KEY}"


def test_the_key_comes_from_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the argument, ASKPILOT_API_KEY gives the key."""
    monkeypatch.setenv("ASKPILOT_API_KEY", API_KEY)
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = Askpilot(
        base_url=BASE_URL, http_client=httpx.Client(transport=httpx.MockTransport(recorder))
    )

    client.organization.get()

    assert recorder.request.headers["Authorization"] == f"Bearer {API_KEY}"


def test_no_key_anywhere_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """The message names the argument and the environment variable."""
    monkeypatch.delenv("ASKPILOT_API_KEY", raising=False)

    with pytest.raises(ConfigurationError) as raised:
        Askpilot(http_client=_mock_http())

    assert "api_key" in str(raised.value)
    assert "ASKPILOT_API_KEY" in str(raised.value)


def test_an_empty_environment_variable_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty ASKPILOT_API_KEY is the same as no variable."""
    monkeypatch.setenv("ASKPILOT_API_KEY", "")

    with pytest.raises(ConfigurationError) as raised:
        Askpilot(http_client=_mock_http())

    assert "ASKPILOT_API_KEY" in str(raised.value)


@pytest.mark.parametrize(
    "bad_key",
    ["sk_0123456789", "0123456789", " ask_0123456789", "ask_01234 56789", "ask_0123456789\n"],
)
def test_a_key_without_the_prefix_or_with_white_space_raises(bad_key: str) -> None:
    """The key must start with ask_ and hold no white space. The message holds no key."""
    with pytest.raises(ConfigurationError) as raised:
        Askpilot(api_key=bad_key, http_client=_mock_http())

    assert "ask_" in str(raised.value)
    assert bad_key.strip() not in str(raised.value)


def test_the_length_of_the_key_is_not_checked() -> None:
    """The service owns the format, so a short key passes the constructor."""
    client = Askpilot(api_key="ask_x", base_url=BASE_URL, http_client=_mock_http())

    assert client.organization.get().name == "Acme Estates"


def test_the_async_client_applies_the_same_key_rules() -> None:
    """AsyncAskpilot refuses a bad key the same way."""
    with pytest.raises(ConfigurationError):
        AsyncAskpilot(api_key="bad", http_client=httpx.AsyncClient())


# ---------------------------------------------------------------------------
# The base URL.
# ---------------------------------------------------------------------------


def test_the_default_base_url_is_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the argument and the variable, the client talks to the production API."""
    monkeypatch.delenv("ASKPILOT_BASE_URL", raising=False)
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = Askpilot(
        api_key=API_KEY, http_client=httpx.Client(transport=httpx.MockTransport(recorder))
    )

    client.organization.get()

    assert str(recorder.request.url) == f"{PRODUCTION_URL}/v1/organization"


def test_the_base_url_comes_from_the_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """ASKPILOT_BASE_URL wins over the default."""
    monkeypatch.setenv("ASKPILOT_BASE_URL", "https://dev.askpilot.test")
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = Askpilot(
        api_key=API_KEY, http_client=httpx.Client(transport=httpx.MockTransport(recorder))
    )

    client.organization.get()

    assert str(recorder.request.url) == "https://dev.askpilot.test/v1/organization"


def test_the_base_url_argument_wins_over_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The argument is used when both exist."""
    monkeypatch.setenv("ASKPILOT_BASE_URL", "https://dev.askpilot.test")
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))

    make_client(recorder).organization.get()

    assert str(recorder.request.url) == f"{BASE_URL}/v1/organization"


def test_1_trailing_slash_is_removed() -> None:
    """A base URL with a trailing slash gives no double slash in the path."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = Askpilot(
        api_key=API_KEY,
        base_url=f"{BASE_URL}/",
        http_client=httpx.Client(transport=httpx.MockTransport(recorder)),
    )

    client.organization.get()

    assert str(recorder.request.url) == f"{BASE_URL}/v1/organization"
    assert repr(client) == f"Askpilot(base_url='{BASE_URL}')"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.askpilot.test",
        "http://public-api.askpilot.com",
        "ftp://api.askpilot.test",
        "api.askpilot.test",
        "not a url",
        "https://",
        "https://api.askpilot.test:port",
    ],
)
def test_a_base_url_without_https_raises_configuration_error(url: str) -> None:
    """https is the only scheme, except for localhost and 127.0.0.1.

    The last case is a URL that httpx refuses: the port is not a number.
    """
    with pytest.raises(ConfigurationError) as raised:
        Askpilot(api_key=API_KEY, base_url=url, http_client=_mock_http())

    assert "https" in str(raised.value)
    assert API_KEY not in str(raised.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:5080",
        "http://127.0.0.1:5080",
        "http://localhost",
        "https://localhost:5080",
    ],
)
def test_http_is_permitted_for_localhost_and_127_0_0_1(url: str) -> None:
    """The local stack has no TLS."""
    client = Askpilot(api_key=API_KEY, base_url=url, http_client=_mock_http())

    assert repr(client) == f"Askpilot(base_url='{url}')"


# ---------------------------------------------------------------------------
# The httpx client, close(), and the context managers.
# ---------------------------------------------------------------------------


def test_the_sdk_makes_an_http_client_and_close_closes_it() -> None:
    """Without http_client the SDK owns the connection pool, and close() closes it."""
    client = Askpilot(api_key=API_KEY, base_url=BASE_URL)

    client.close()

    with pytest.raises(RuntimeError, match="closed"):
        client.organization.get()


def test_the_context_manager_closes_the_client() -> None:
    """The with statement closes the client at the end."""
    with Askpilot(api_key=API_KEY, base_url=BASE_URL) as client:
        assert repr(client) == f"Askpilot(base_url='{BASE_URL}')"

    with pytest.raises(RuntimeError, match="closed"):
        client.organization.get()


def test_the_client_of_the_caller_stays_open_after_close() -> None:
    """The caller owns the client that the caller made."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    http = httpx.Client(transport=httpx.MockTransport(recorder))
    client = Askpilot(api_key=API_KEY, base_url=BASE_URL, http_client=http)

    client.close()

    assert http.is_closed is False
    assert http.get(f"{BASE_URL}/v1/organization").status_code == 200


async def test_the_async_context_manager_closes_the_client() -> None:
    """The async with statement closes the async client at the end."""
    async with AsyncAskpilot(api_key=API_KEY, base_url=BASE_URL) as client:
        assert repr(client) == f"AsyncAskpilot(base_url='{BASE_URL}')"

    with pytest.raises(RuntimeError, match="closed"):
        await client.organization.get()


async def test_the_async_client_of_the_caller_stays_open_after_aclose() -> None:
    """The caller owns the async client that the caller made."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    client = AsyncAskpilot(api_key=API_KEY, base_url=BASE_URL, http_client=http)

    await client.aclose()

    assert http.is_closed is False
    await http.aclose()


def test_the_client_of_the_caller_gives_no_base_url_and_no_header() -> None:
    """The SDK reads nothing from the httpx client of the caller."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    http = httpx.Client(
        transport=httpx.MockTransport(recorder),
        base_url="https://other.askpilot.test",
        headers={"Authorization": "Bearer other", "X-Custom": "1"},
    )
    client = Askpilot(api_key=API_KEY, base_url=BASE_URL, http_client=http)

    client.organization.get()

    assert str(recorder.request.url) == f"{BASE_URL}/v1/organization"
    assert recorder.request.headers["Authorization"] == f"Bearer {API_KEY}"
    assert "X-Custom" not in recorder.request.headers


# ---------------------------------------------------------------------------
# The repr, the key, and the options.
# ---------------------------------------------------------------------------


def test_repr_gives_the_class_name_and_the_base_url_and_never_the_key() -> None:
    """repr(client) is for a log line or a debugger."""
    client = make_client(Recorder(json_response(200, ORGANIZATION_BODY)))

    assert repr(client) == f"Askpilot(base_url='{BASE_URL}')"
    assert API_KEY not in repr(client)
    assert API_KEY not in str(client)


def test_the_key_lives_in_1_private_attribute_only() -> None:
    """The client holds the key 1 time, in a private attribute, and nothing else keeps a copy."""
    http = _mock_http()
    client = Askpilot(api_key=API_KEY, base_url=BASE_URL, http_client=http)

    holders = [name for name, value in vars(client).items() if value == API_KEY]

    assert len(holders) == 1
    assert holders[0].startswith("_")
    assert API_KEY not in vars(client.organization).values()
    assert API_KEY not in vars(client.workflows).values()
    assert "Authorization" not in http.headers


def test_a_negative_max_retries_raises_configuration_error() -> None:
    """max_retries is 0 or more."""
    with pytest.raises(ConfigurationError, match="max_retries"):
        Askpilot(api_key=API_KEY, base_url=BASE_URL, max_retries=-1, http_client=_mock_http())


def test_the_resources_are_the_2_documented_attributes() -> None:
    """organization and workflows hold the 5 methods."""
    client = make_client(Recorder(json_response(200, ORGANIZATION_BODY)))

    assert callable(client.organization.get)
    assert callable(client.workflows.list)
    assert callable(client.workflows.iterate)
    assert callable(client.workflows.get)
    assert callable(client.workflows.start)
