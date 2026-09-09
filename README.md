# <img src="https://raw.githubusercontent.com/Askpilot-AI-Number/public-api-python-client-sdk/main/assets/askpilot-logo.png" alt="" height="32"> Askpilot Public API Python Client SDK

[![CI](https://github.com/Askpilot-AI-Number/public-api-python-client-sdk/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Askpilot-AI-Number/public-api-python-client-sdk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/askpilot)](https://pypi.org/project/askpilot/)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)

The official Python client for the [Askpilot](https://askpilot.com) public API. It gives you typed
access to your organization and its workflows, with retries, timeouts, and clear exceptions built
in.

- Python 3.9 or later
- A sync client and an async client
- Two runtime dependencies: [httpx](https://www.python-httpx.org) and
  [pydantic](https://docs.pydantic.dev)

## Install

```bash
pip install askpilot
```

Or, with uv:

```bash
uv add askpilot
```

## Quickstart

```python
import askpilot

client = askpilot.Askpilot(api_key="ask_...")

# The organization your key belongs to
organization = client.organization.get()
print(organization.name)

# One page of workflows
page = client.workflows.list(limit=10)
for workflow in page.data:
    print(workflow.id, workflow.name)

# Every workflow, page by page
for workflow in client.workflows.iterate():
    print(workflow.name)

# One workflow
workflow = client.workflows.get("018f2c1e-8a4b-7c3d-9e5f-1a2b3c4d5e6f")

# Start a workflow
start = client.workflows.start(workflow.id, context="New lead: John Smith, wants a 2-bed flat.")
print(start.session_id)

client.close()
```

You can also use the client as a context manager, so it closes itself:

```python
with askpilot.Askpilot() as client:
    print(client.organization.get().name)
```

## Your API key

You create an API key in Askpilot, under the organization settings. Askpilot shows the key once,
and it starts with `ask_`. Keep it in a secret store, never in your code or your repository.

Pass the key to the client, or set the `ASKPILOT_API_KEY` environment variable and create the
client with no arguments:

```python
client = askpilot.Askpilot()  # reads ASKPILOT_API_KEY
```

The key never appears in a log line, in an exception message, or in `repr(client)`.

| Environment variable | What it does |
|---|---|
| `ASKPILOT_API_KEY` | Your API key, used when you don't pass `api_key`. |
| `ASKPILOT_BASE_URL` | The URL of the API, used when you don't pass `base_url`. |

## Errors

Every exception the SDK raises is a subclass of `askpilot.AskpilotError`, so one `except` can catch
them all. An error response from the API becomes the `APIError` subclass of its HTTP status, and
the error code from the response stays on the exception as `code`:

```python
import askpilot

try:
    start = client.workflows.start(workflow_id, context="New lead: John Smith.")
except askpilot.ConflictError as error:
    if error.code == "api_trigger_not_configured":
        print("Add a trigger with the source API to this workflow in Askpilot.")
    else:
        raise
except askpilot.RateLimitError as error:
    print(f"Too many requests. Wait {error.retry_after} seconds.")
except askpilot.APIError as error:
    print(f"{error.status_code} {error.code}: {error.message} (request id {error.request_id})")
except askpilot.APIConnectionError:
    print("Couldn't reach Askpilot. Check your network and try again.")
```

| Exception | When |
|---|---|
| `AskpilotError` | The base of every exception below. |
| `ConfigurationError` | The key or the base URL is missing or not valid when you create the client. |
| `APIConnectionError` | No HTTP response arrived, even after the retries. |
| `APITimeoutError` | The response didn't arrive within the timeout. A subclass of `APIConnectionError`. |
| `APIError` | The API responded with an error status. The base of the classes below. |
| `InvalidRequestError` | 400 or 422. On a 422, `details` lists each field that failed validation. |
| `AuthenticationError` | 401. The key is missing, revoked, expired, or not valid. |
| `PermissionDeniedError` | 403. The key doesn't have the scope this call needs. |
| `NotFoundError` | 404. The resource doesn't exist in your organization. |
| `ConflictError` | 409. The state of the resource doesn't allow the action. Check `code`. |
| `RateLimitError` | 429. Wait `retry_after` seconds before the next request. |
| `ServerError` | 500 to 599. Something went wrong on the Askpilot side. |
| `UnexpectedResponseError` | The SDK couldn't read the response, for example a page from a proxy. |

Every `APIError` has `status_code`, `code`, `message`, `request_id`, `details`, and `body`. Include
`request_id` when you contact support. The error codes of each call are listed in
[docs/organization.md](docs/organization.md) and [docs/workflows.md](docs/workflows.md).

## Pagination

`list()` returns one page. `page.data` holds the items, and `page.pagination.next_cursor` is the
cursor of the next page, or `None` on the last page:

```python
cursor = None
while True:
    page = client.workflows.list(limit=100, cursor=cursor)
    for workflow in page.data:
        print(workflow.name)
    cursor = page.pagination.next_cursor
    if cursor is None:
        break
```

`iterate()` runs this loop for you and yields each item. Stop on `next_cursor`, not on the size of
a page: a short page can still have a next page. The cursor is opaque. Send it back as it is.

## Retries and the timeout

The client sends a `GET` again after a connection error, a timeout, or a 502, 503, or 504
response, and it sends any request again after a 429. It waits 0.5, 1, then 2 seconds between
tries, or the `Retry-After` of a 429 (at most 60 seconds). A `POST` is never retried for another
reason: a start that reached Askpilot may have started the workflow, and a second start would
start it again.

```python
client = askpilot.Askpilot(max_retries=0)  # no retries
client = askpilot.Askpilot(timeout=10.0)  # 10 seconds per request
```

The default timeout is 30 seconds, and it applies to each phase of a request. Pass an
`httpx.Timeout` for a value per phase.

## Logging

The SDK logs one line per request at `DEBUG` on the logger `askpilot`, with the method, the path,
the status, the duration, the request id, and what's left of your rate limit. Before each retry it
logs one line at `WARNING` with the cause and the wait. No line contains your key, a header value,
or a body. Two lines turn the `DEBUG` line on:

```python
import logging

logging.basicConfig()
logging.getLogger("askpilot").setLevel(logging.DEBUG)
```

## The async client

`AsyncAskpilot` has the same methods as coroutines, and `iterate()` is an async iterator:

```python
import asyncio

import askpilot


async def main() -> None:
    async with askpilot.AsyncAskpilot() as client:
        organization = await client.organization.get()
        print(organization.name)
        async for workflow in client.workflows.iterate():
            print(workflow.name)


asyncio.run(main())
```

## Your own httpx client

Pass an `httpx.Client` (or an `httpx.AsyncClient`) as `http_client` for a proxy, a custom CA, or
a test transport. You own it: `close()` doesn't close it. The SDK sets its own URL, headers, and
timeout on every request, so the base URL and the headers of your client aren't used.

```python
import httpx

import askpilot

http = httpx.Client(proxy="http://proxy.internal:3128", verify="/etc/ssl/company-ca.pem")
client = askpilot.Askpilot(http_client=http)
```

## Reference

- [docs/organization.md](docs/organization.md): `client.organization`
- [docs/workflows.md](docs/workflows.md): `client.workflows`
- The API reference, with a console to try calls: https://public-api.askpilot.com/docs

## License

MIT. See [LICENSE](LICENSE).
