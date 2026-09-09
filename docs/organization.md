# Organization

`client.organization` gives you the organization your API key belongs to. It has one method.

## `client.organization.get()`

Returns the organization that your API key belongs to.

There's nothing to pass: the API key determines the organization.

| | |
|---|---|
| Operation | `GET /v1/organization` |
| Scope of the key | `organization:read` |
| Arguments | None |
| Returns | `Organization` |

```python
organization = client.organization.get()
print(organization.id, organization.name)
```

With the async client: `organization = await client.organization.get()`.

### `Organization`

The organization that your API key belongs to.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Unique identifier of the organization. |
| `name` | `str` | Name of the organization. |

### Errors

| Code | Status | Exception | When |
|---|---|---|---|
| `unauthorized` | 401 | `AuthenticationError` | The key is missing, revoked, expired, or not valid. |
| `forbidden` | 403 | `PermissionDeniedError` | The key doesn't have the scope `organization:read`. |
| `not_found` | 404 | `NotFoundError` | The organization doesn't exist. |
| `method_not_allowed` | 405 | `APIError` | The method isn't `GET`. The SDK never sends another one. |
| `rate_limited` | 429 | `RateLimitError` | Your organization sent too many requests. Wait `retry_after` seconds. |
| `internal_error` | 500 | `ServerError` | Something went wrong on the Askpilot side. |
| `service_unavailable` | 503 | `ServerError` | The API can't read its data right now. Try again. |

Every exception has `request_id`. Include it when you contact support. Read the README for the
full list of exceptions.
