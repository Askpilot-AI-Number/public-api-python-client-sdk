# Workflows

`client.workflows` gives you the workflows of your organization: a list, a single workflow, and a
way to start one. A workflow is a task that Askpilot runs for your organization. It has a name, a
description, the users with access, the triggers with their sources, and a file list.

There are four methods. Each one has an async twin on `AsyncAskpilot`.

## `client.workflows.list(*, limit=None, cursor=None, search=None)`

Returns the workflows in your organization, one page at a time.

The list includes every workflow, active or not, whatever its scope. Use limit and cursor to page
through the results, and search to filter by name or description.

| | |
|---|---|
| Operation | `GET /v1/workflows` |
| Scope of the key | `workflows:read` |
| Returns | `Page[Workflow]` |

| Argument | Type | Description |
|---|---|---|
| `limit` | `int` or `None` | How many items to return per page, from 1 to 100. The default is 25. |
| `cursor` | `str` or `None` | Cursor from a previous response. Pass the next_cursor value to get the next page, or leave it out to start from the beginning. |
| `search` | `str` or `None` | Only return items that contain this text. The match ignores case. |

The SDK sends only the arguments you pass. It doesn't check the range of `limit`: the API does,
and a value outside 1 to 100 gives an `InvalidRequestError` with `details`.

```python
page = client.workflows.list(limit=100, search="lead")
for workflow in page.data:
    print(workflow.name)
if page.pagination.has_more:
    next_page = client.workflows.list(limit=100, search="lead", cursor=page.pagination.next_cursor)
```

### `Page[Workflow]`

A page of results. The data list holds the items of this page, and pagination tells you how to get
the next one. `Page` is a generic model: `list()` returns a `Page` of `Workflow` items.

| Field | Type | Description |
|---|---|---|
| `data` | `list[Workflow]` | The items on this page. It's an empty list when there are no results. |
| `pagination` | `PageInfo` | Whether there are more results, and the cursor for the next page. |

### `PageInfo`

Tells you whether there are more results and how to fetch the next page.

| Field | Type | Description |
|---|---|---|
| `next_cursor` | `str` or `None` | Cursor for the next page of results. It's null when you've reached the last page. |
| `has_more` | `bool` | Whether there are more results after this page. |

The cursor is opaque: send it back as it is. Stop on `next_cursor`, not on the size of a page.

### Errors

| Code | Status | Exception | When |
|---|---|---|---|
| `unauthorized` | 401 | `AuthenticationError` | The key is missing, revoked, expired, or not valid. |
| `forbidden` | 403 | `PermissionDeniedError` | The key doesn't have the scope `workflows:read`. |
| `invalid_cursor` | 422 | `InvalidRequestError` | The cursor isn't valid. Read the list again from the start. |
| `validation_error` | 422 | `InvalidRequestError` | `limit` is outside 1 to 100, or `search` is too long. `details` names the field. |
| `rate_limited` | 429 | `RateLimitError` | Your organization sent too many requests. Wait `retry_after` seconds. |
| `internal_error` | 500 | `ServerError` | Something went wrong on the Askpilot side. |
| `service_unavailable` | 503 | `ServerError` | The API can't read its data right now. Try again. |

## `client.workflows.iterate(*, limit=100, search=None)`

Yields every workflow in your organization, reading the pages as you go. Each page is one request
to `GET /v1/workflows`, and the loop stops when the API says there's no next page.

| Argument | Type | Description |
|---|---|---|
| `limit` | `int` | How many items to fetch per page, from 1 to 100. The default is 100, which reads the list with the fewest requests. |
| `search` | `str` or `None` | Only return items that contain this text. The match ignores case. |

```python
for workflow in client.workflows.iterate(search="lead"):
    print(workflow.name)
```

With the async client: `async for workflow in client.workflows.iterate():`.

The errors are the errors of `list()`. Each page counts as one request in your rate limit.

## `client.workflows.get(workflow_id)`

Returns a single workflow by its id.

The object is the same as in the list. If the workflow doesn't exist in your organization, you get
a `NotFoundError`.

| | |
|---|---|
| Operation | `GET /v1/workflows/{workflow_id}` |
| Scope of the key | `workflows:read` |
| Returns | `Workflow` |

| Argument | Type | Description |
|---|---|---|
| `workflow_id` | `str` or `UUID` | Unique identifier of the workflow. |

```python
workflow = client.workflows.get("018f2c1e-8a4b-7c3d-9e5f-1a2b3c4d5e6f")
print(workflow.name, workflow.is_active)
```

### Errors

| Code | Status | Exception | When |
|---|---|---|---|
| `unauthorized` | 401 | `AuthenticationError` | The key is missing, revoked, expired, or not valid. |
| `forbidden` | 403 | `PermissionDeniedError` | The key doesn't have the scope `workflows:read`. |
| `not_found` | 404 | `NotFoundError` | The workflow doesn't exist, or another organization owns it. The two cases give the same error. |
| `validation_error` | 422 | `InvalidRequestError` | `workflow_id` isn't a UUID. |
| `rate_limited` | 429 | `RateLimitError` | Your organization sent too many requests. Wait `retry_after` seconds. |
| `internal_error` | 500 | `ServerError` | Something went wrong on the Askpilot side. |
| `service_unavailable` | 503 | `ServerError` | The API can't read its data right now. Try again. |

## `client.workflows.start(workflow_id, *, context, session_id=None)`

Starts a workflow with the text you provide.

Askpilot accepts the request and responds with 202 right away. The workflow itself runs a few
seconds later, in the session you named or in a new one. To start, the workflow must be active,
have an active trigger with the source api, and have at least one user with access.

| | |
|---|---|
| Operation | `POST /v1/workflows/{workflow_id}/start` |
| Scope of the key | `workflows:write` |
| Returns | `WorkflowStart` |

| Argument | Type | Description |
|---|---|---|
| `workflow_id` | `str` or `UUID` | Unique identifier of the workflow. |
| `context` | `str` | The text you want the workflow to work with. Askpilot trims whitespace at the start and end, and what's left must be 1 to 10,000 characters long. |
| `session_id` | `str`, `UUID`, or `None` | The session to run the workflow in. It must be an open session in your organization. Leave it out and Askpilot creates a new session. Each start applies the workflow's current settings to the session: the subagent sources on the API trigger and the workflow's auto-run settings replace what the session had. |

The SDK sends `context` as you pass it, and it adds `session_id` to the request only when you pass
one. Askpilot trims and measures the text, and it answers with an `InvalidRequestError` when the
text is empty or too long.

```python
start = client.workflows.start(
    "018f2c1e-8a4b-7c3d-9e5f-1a2b3c4d5e6f",
    context="New lead: John Smith, +44 7700 900123, wants a 2-bed flat in Leeds.",
)
print(start.id, start.session_id)

# Later: send a second message to the same session
client.workflows.start(start.workflow_id, context="John called back.", session_id=start.session_id)
```

**What 202 means.** A `WorkflowStart` says that Askpilot accepted the start, not that the workflow
ran. The session starts a few seconds later. Keep `session_id`: it names the session in the
Askpilot web app, and a later start can send a second message to the same session.

**Each start replaces the session's settings.** When you pass a `session_id`, Askpilot applies the
workflow's current settings to that session: the subagent sources on the API trigger and the
workflow's auto-run settings replace what the session had. Changes someone made to that session in
the Askpilot web app don't survive a start.

**A start isn't idempotent.** A request you send twice starts the workflow twice, and the SDK never
retries a start on its own after a timeout or a gateway error, only after a 429. To make a
workflow startable, a person adds a trigger with the source API to it in the Askpilot web app.

### `WorkflowStart`

Confirmation that Askpilot accepted your request to start the workflow.

The workflow doesn't run right away: Askpilot starts it a few seconds later. Keep session_id if
you want to start the workflow again in the same session. Each start applies the workflow's
current settings to that session.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Unique identifier of this start request. Include it when you contact support. |
| `workflow_id` | `UUID` | Unique identifier of the workflow that's being started. |
| `session_id` | `UUID` | Unique identifier of the session the workflow runs in. It's the session you passed in, or a new one that Askpilot created for you. |

### Errors

| Code | Status | Exception | When |
|---|---|---|---|
| `unauthorized` | 401 | `AuthenticationError` | The key is missing, revoked, expired, or not valid. |
| `forbidden` | 403 | `PermissionDeniedError` | The key doesn't have the scope `workflows:write`. |
| `not_found` | 404 | `NotFoundError` | The workflow doesn't exist, or another organization owns it. |
| `workflow_inactive` | 409 | `ConflictError` | A person stopped the workflow. Make it active in Askpilot. |
| `api_trigger_not_configured` | 409 | `ConflictError` | The workflow has no active trigger with the source API. Add one in Askpilot. |
| `workflow_owner_missing` | 409 | `ConflictError` | The workflow has no user. Give a user access to it in Askpilot. |
| `session_not_open` | 409 | `ConflictError` | The session of `session_id` isn't open. Send the request again without `session_id`. |
| `validation_error` | 422 | `InvalidRequestError` | `context` is empty or too long, or `session_id` names a session that doesn't exist. `details` names the field. |
| `rate_limited` | 429 | `RateLimitError` | Your organization sent too many requests. Wait `retry_after` seconds. |
| `internal_error` | 500 | `ServerError` | Something went wrong on the Askpilot side. |
| `service_unavailable` | 503 | `ServerError` | Askpilot can't take the start right now. Send the request again. |

## The workflow object

### `Workflow`

A workflow in your organization.

The list and the single-workflow endpoints both return this object.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Unique identifier of the workflow. |
| `name` | `str` | Name of the workflow. |
| `description` | `str` | Description of what the workflow does, as written in Askpilot. |
| `scope` | `str` | Who can use the workflow: company_wide means everyone in your organization, and only_me means a single user. New values may be added over time, so don't reject values you don't recognize. |
| `is_active` | `bool` | Whether the workflow is active. An inactive workflow can't be started through the API. |
| `auto_run` | `AutoRun` | The auto-run settings of the workflow. |
| `users` | `list[User]` | The people who have access to this workflow, sorted by email address. |
| `triggers` | `list[Trigger]` | The triggers that can start this workflow, oldest first. Paused triggers are included. |
| `files` | `list[WorkflowFile]` | The files that belong to this workflow, sorted by folder and then by name. The content of a file isn't included. |
| `created_at` | `datetime` | When the workflow was created. |
| `updated_at` | `datetime` | When the workflow was last changed. |

Each `datetime` is aware and in UTC. A later version of the API can add a field, and the SDK
ignores a field it doesn't know, so your installed version keeps working.

### `AutoRun`

The auto-run settings of a workflow.

Auto-run lets a workflow run again on a schedule.

| Field | Type | Description |
|---|---|---|
| `enabled` | `bool` or `None` | Whether the workflow runs again automatically on a schedule. It's null if auto-run was never configured. |
| `frequency` | `str` or `None` | How often the workflow runs automatically: hourly, daily, weekly, or monthly. It's null if there's no schedule. |

### `User`

A person who has access to the workflow.

| Field | Type | Description |
|---|---|---|
| `email` | `str` | Email address of the user. |
| `name` | `str` | Full name of the user, made from their first and last name. It's an empty string when neither is set. |

### `Trigger`

A trigger that starts this workflow.

You can start a workflow through this API when it has an active trigger whose source is api.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Unique identifier of the trigger. |
| `name` | `str` | Name of the trigger. It can be empty. |
| `is_active` | `bool` | Whether the trigger is active. A paused trigger is inactive, but it still appears in this list. |
| `trigger_source` | `TriggerSource` | Where the trigger's events come from, such as the API or Street. |
| `events` | `list[TriggerEvent]` | The events that fire this trigger and start the workflow. |
| `filters` | `dict[str, Any]` or `None` | Extra conditions for the trigger, exactly as configured in Askpilot. It's null when the trigger has none. |
| `input_message` | `str` | Text that Askpilot adds to the session message when this trigger starts the workflow. It can be empty. |
| `subagent_sources` | `list[SubagentSource]` | The subagent sources attached to this trigger. Sources with a type other than platform_internal come first, sorted by name, followed by the platform_internal sources, also sorted by name. |

### `TriggerSource`

Where a trigger's events come from, such as the API or Street.

| Field | Type | Description |
|---|---|---|
| `slug` | `str` | Machine-readable name of the source, such as api. Use this value in your code. |
| `name` | `str` | Human-readable name of the source, such as API. |

### `TriggerEvent`

An event that fires the trigger.

| Field | Type | Description |
|---|---|---|
| `slug` | `str` | Machine-readable name of the event. Use this value in your code. |
| `name` | `str` | Human-readable name of the event. |

### `SubagentSource`

A subagent source that's attached to a trigger.

Check the type field to see what kind it is.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` or `None` | Unique identifier of the subagent source. It's null when the type is platform_internal. |
| `name` | `str` | Name of the subagent source, such as API, Street CRM, or web-research. |
| `type` | `str` | What kind of subagent source this is, such as api, street, or platform_internal. A platform_internal source is a subagent built into Askpilot. New types may be added over time, so don't reject values you don't recognize. |

### `WorkflowFile`

A file that belongs to the workflow.

The response includes the name and location of the file, but not its content.

| Field | Type | Description |
|---|---|---|
| `id` | `UUID` | Unique identifier of the file. |
| `name` | `str` | Name of the file, such as PROCESS.md. |
| `path` | `list[str]` | The folders that contain the file, from the top level down. An empty list means the file is at the root of the workflow. |

## The error response

Every error response of the API has the same body, whatever the status. The SDK reads it into the
exception: `code`, `message`, `request_id`, and `details` become attributes of the `APIError`. You
don't need these models to handle an error, but they're available if you want to read a body
yourself.

### `ErrorResponse`

The body of every error response, whatever the status code.

| Field | Type | Description |
|---|---|---|
| `error` | `ErrorBody` | What went wrong: the error code, a message, and the id of the request. |

### `ErrorBody`

Details about the error.

| Field | Type | Description |
|---|---|---|
| `code` | `str` | A stable code that identifies the error, such as not_found or rate_limited. Match on this value in your code; it won't change. |
| `message` | `str` | A human-readable explanation of the error. This text may change, so don't match on it. |
| `request_id` | `str` | Unique identifier of this request. Include it when you contact support. |
| `details` | `list[FieldError]` or `None` | The fields that failed validation. It's only included on 422 responses. |

### `FieldError`

Details about one field of your request that failed validation.

Only 422 responses include these.

| Field | Type | Description |
|---|---|---|
| `field` | `str` | Name of the field that failed validation, such as context. For a nested field, the parts are joined with a dot. |
| `code` | `str` | A short code that says what's wrong with the field, such as string_too_short or not_found. Match on this value in your code. |
| `message` | `str` | A human-readable explanation of what's wrong with the field. |

## The rate limit

The four methods count in the rate limit of your organization: 60 requests each minute by default,
shared by every key of the organization. Each page of `iterate()` is one request, so a `limit` of
100 reads the same data with fewer requests than a `limit` of 25. When you pass the limit, the API
answers 429, and the SDK waits for the `Retry-After` of the response and sends the request again,
up to `max_retries` times. After the last try you get a `RateLimitError` with `retry_after`.
