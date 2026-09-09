"""The workflows resource, sync and async: list, iterate, get, and start."""

# Python 3.9 evaluates the annotation of a function at run time, and it gives a
# TypeError for `X | None`. This line makes each annotation of this file a
# string. `tests/conftest.py` holds the same line, for the same reason.
from __future__ import annotations

import json
import uuid

import pytest

from askpilot import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    Page,
    Workflow,
    WorkflowStart,
)
from tests.conftest import (
    BASE_URL,
    PAGE_BODY,
    SESSION_ID,
    START_BODY,
    WORKFLOW_BODY,
    WORKFLOW_ID,
    Recorder,
    error_body,
    json_response,
    make_async_client,
    make_client,
)


def _page(count: int, next_cursor: str | None) -> dict:
    """Make a page body with `count` copies of the workflow."""
    return {
        "data": [WORKFLOW_BODY] * count,
        "pagination": {"next_cursor": next_cursor, "has_more": next_cursor is not None},
    }


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_sends_get_v1_workflows_with_no_query_by_default() -> None:
    """Without arguments the request holds no query parameter."""
    recorder = Recorder(json_response(200, PAGE_BODY))
    client = make_client(recorder)

    page = client.workflows.list()

    assert recorder.request.method == "GET"
    assert str(recorder.request.url) == f"{BASE_URL}/v1/workflows"
    assert isinstance(page, Page)
    assert isinstance(page.data[0], Workflow)
    assert page.pagination.next_cursor is None


def test_list_sends_only_the_parameters_that_the_caller_gave() -> None:
    """limit and search go on the query; cursor stays out when None."""
    recorder = Recorder(json_response(200, PAGE_BODY))
    client = make_client(recorder)

    client.workflows.list(limit=10, search="lead")

    assert dict(recorder.request.url.params) == {"limit": "10", "search": "lead"}


def test_list_sends_the_cursor() -> None:
    """The cursor goes on the query as it is."""
    recorder = Recorder(json_response(200, PAGE_BODY))
    client = make_client(recorder)

    client.workflows.list(cursor="eyJ2IjoxfQ")

    assert dict(recorder.request.url.params) == {"cursor": "eyJ2IjoxfQ"}


def test_list_does_not_check_the_limit_range() -> None:
    """The service checks the range and gives 422 with details."""
    details = [{"field": "limit", "code": "greater_than_equal", "message": "1 or more."}]
    recorder = Recorder(json_response(422, error_body("validation_error", details=details)))
    client = make_client(recorder)

    with pytest.raises(InvalidRequestError) as raised:
        client.workflows.list(limit=0)

    assert dict(recorder.request.url.params) == {"limit": "0"}
    assert raised.value.details[0].field == "limit"


async def test_the_async_list_gives_the_page() -> None:
    """The async method reads the same route with the same query."""
    recorder = Recorder(json_response(200, PAGE_BODY))
    client = make_async_client(recorder)

    page = await client.workflows.list(limit=5)

    assert dict(recorder.request.url.params) == {"limit": "5"}
    assert isinstance(page.data[0], Workflow)


# ---------------------------------------------------------------------------
# iterate
# ---------------------------------------------------------------------------


def test_iterate_reads_each_page_and_stops_when_next_cursor_is_null() -> None:
    """The second request carries the cursor of the first answer."""
    recorder = Recorder(json_response(200, _page(2, "c1")), json_response(200, _page(1, None)))
    client = make_client(recorder)

    workflows = list(client.workflows.iterate())

    assert len(workflows) == 3
    assert all(isinstance(workflow, Workflow) for workflow in workflows)
    assert len(recorder.requests) == 2
    assert dict(recorder.requests[0].url.params) == {"limit": "100"}
    assert dict(recorder.requests[1].url.params) == {"limit": "100", "cursor": "c1"}


def test_iterate_looks_at_next_cursor_and_not_at_the_number_of_items() -> None:
    """A short page with a cursor is not the last page."""
    recorder = Recorder(json_response(200, _page(1, "c1")), json_response(200, _page(1, None)))
    client = make_client(recorder)

    workflows = list(client.workflows.iterate(limit=100))

    assert len(workflows) == 2
    assert len(recorder.requests) == 2


def test_iterate_sends_the_limit_and_the_search() -> None:
    """The 2 arguments go on each page request."""
    recorder = Recorder(json_response(200, _page(1, None)))
    client = make_client(recorder)

    list(client.workflows.iterate(limit=50, search="lead"))

    assert dict(recorder.request.url.params) == {"limit": "50", "search": "lead"}


def test_iterate_with_an_empty_first_page_gives_nothing() -> None:
    """An organization with no workflow gives an empty iteration."""
    recorder = Recorder(json_response(200, _page(0, None)))
    client = make_client(recorder)

    assert list(client.workflows.iterate()) == []


def test_iterate_reads_a_page_only_when_the_caller_asks_for_it() -> None:
    """The iterator is lazy: no request goes out before the first item is read."""
    recorder = Recorder(json_response(200, _page(1, "c1")), json_response(200, _page(1, None)))
    client = make_client(recorder)

    iterator = client.workflows.iterate()
    assert recorder.requests == []

    next(iterator)

    assert len(recorder.requests) == 1


async def test_the_async_iterate_gives_each_item_of_each_page() -> None:
    """The async iterator reads the pages the same way."""
    recorder = Recorder(json_response(200, _page(2, "c1")), json_response(200, _page(1, None)))
    client = make_async_client(recorder)

    workflows = [workflow async for workflow in client.workflows.iterate(limit=10)]

    assert len(workflows) == 3
    assert dict(recorder.requests[1].url.params) == {"limit": "10", "cursor": "c1"}


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_sends_the_id_in_the_path() -> None:
    """A str id and a UUID id give the same path."""
    recorder = Recorder(json_response(200, WORKFLOW_BODY))
    client = make_client(recorder)

    first = client.workflows.get(WORKFLOW_ID)
    second = client.workflows.get(uuid.UUID(WORKFLOW_ID))

    assert first == second
    assert first.id == uuid.UUID(WORKFLOW_ID)
    assert [str(request.url) for request in recorder.requests] == [
        f"{BASE_URL}/v1/workflows/{WORKFLOW_ID}",
        f"{BASE_URL}/v1/workflows/{WORKFLOW_ID}",
    ]


def test_get_quotes_an_id_that_holds_a_slash() -> None:
    """An id can never change the route: the path stays under /v1/workflows/."""
    recorder = Recorder(json_response(404, error_body("not_found")))
    client = make_client(recorder)

    with pytest.raises(NotFoundError):
        client.workflows.get("../organization?x=1")

    assert recorder.request.url.raw_path == b"/v1/workflows/..%2Forganization%3Fx%3D1"


def test_a_404_gives_not_found_error() -> None:
    """A workflow of another organization and a missing workflow give the same error."""
    client = make_client(Recorder(json_response(404, error_body("not_found"))))

    with pytest.raises(NotFoundError) as raised:
        client.workflows.get(WORKFLOW_ID)

    assert raised.value.code == "not_found"


async def test_the_async_get_gives_the_workflow() -> None:
    """The async method reads the same route."""
    recorder = Recorder(json_response(200, WORKFLOW_BODY))
    client = make_async_client(recorder)

    workflow = await client.workflows.get(WORKFLOW_ID)

    assert str(recorder.request.url) == f"{BASE_URL}/v1/workflows/{WORKFLOW_ID}"
    assert workflow.name == "inbound-lead-handler"


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def test_start_sends_post_with_the_context_only() -> None:
    """Without session_id the body holds context and nothing else."""
    recorder = Recorder(json_response(202, START_BODY))
    client = make_client(recorder)

    start = client.workflows.start(WORKFLOW_ID, context="New lead: John Smith.")

    assert recorder.request.method == "POST"
    assert str(recorder.request.url) == f"{BASE_URL}/v1/workflows/{WORKFLOW_ID}/start"
    assert json.loads(recorder.request.content) == {"context": "New lead: John Smith."}
    assert isinstance(start, WorkflowStart)
    assert str(start.session_id) == SESSION_ID


@pytest.mark.parametrize("session_id", [SESSION_ID, uuid.UUID(SESSION_ID)])
def test_start_adds_session_id_when_the_caller_gives_1(session_id: str | uuid.UUID) -> None:
    """A str and a UUID both go on the body as text."""
    recorder = Recorder(json_response(202, START_BODY))
    client = make_client(recorder)

    client.workflows.start(uuid.UUID(WORKFLOW_ID), context="Again", session_id=session_id)

    assert json.loads(recorder.request.content) == {"context": "Again", "session_id": SESSION_ID}


def test_start_does_not_strip_or_measure_the_context() -> None:
    """The service trims and measures the context, and it gives 422 with details."""
    details = [{"field": "context", "code": "string_too_short", "message": "Too short."}]
    recorder = Recorder(json_response(422, error_body("validation_error", details=details)))
    client = make_client(recorder)

    with pytest.raises(InvalidRequestError) as raised:
        client.workflows.start(WORKFLOW_ID, context="   ")

    assert json.loads(recorder.request.content) == {"context": "   "}
    assert raised.value.details[0].field == "context"
    assert raised.value.details[0].code == "string_too_short"


def test_a_409_gives_conflict_error_with_the_code() -> None:
    """A workflow with no API trigger gives ConflictError, and the code says which rule."""
    body = error_body("api_trigger_not_configured", "This workflow has no API trigger.")
    client = make_client(Recorder(json_response(409, body)))

    with pytest.raises(ConflictError) as raised:
        client.workflows.start(WORKFLOW_ID, context="New lead")

    assert raised.value.code == "api_trigger_not_configured"


async def test_the_async_start_gives_the_start() -> None:
    """The async method sends the same body."""
    recorder = Recorder(json_response(202, START_BODY))
    client = make_async_client(recorder)

    start = await client.workflows.start(WORKFLOW_ID, context="New lead", session_id=SESSION_ID)

    assert json.loads(recorder.request.content) == {"context": "New lead", "session_id": SESSION_ID}
    assert str(start.id) == START_BODY["id"]
