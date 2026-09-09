"""The live check against a real stack.

The tests run only when `ASKPILOT_API_KEY` and `ASKPILOT_BASE_URL` are set,
and pytest skips them otherwise. CI never sets them. They call the 4
operations and the error paths on the stack that the variables name. Run them
on the local stack:

    ASKPILOT_API_KEY=ask_... ASKPILOT_BASE_URL=http://localhost:5080 \\
        uv run pytest tests/live -p no:cacheprovider

The last test sends requests until the rate limit answers 429, so the key
holds no request budget for about 1 minute after the run.
"""

import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest

import askpilot
from askpilot import (
    AuthenticationError,
    InvalidRequestError,
    NotFoundError,
    Organization,
    RateLimitError,
    Workflow,
    WorkflowStart,
)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("ASKPILOT_API_KEY") and os.environ.get("ASKPILOT_BASE_URL")),
    reason="ASKPILOT_API_KEY and ASKPILOT_BASE_URL are not set",
)


@pytest.fixture(scope="module")
def client() -> Iterator[askpilot.Askpilot]:
    """The client of the live stack, from the 2 environment variables."""
    with askpilot.Askpilot() as live_client:
        yield live_client


def test_organization_get_gives_the_organization(client: askpilot.Askpilot) -> None:
    """GET /v1/organization gives the organization of the key."""
    organization = client.organization.get()

    assert isinstance(organization, Organization)
    assert isinstance(organization.id, uuid.UUID)
    assert organization.name


def test_workflows_list_gives_a_page(client: askpilot.Askpilot) -> None:
    """GET /v1/workflows gives a page of the size asked for."""
    page = client.workflows.list(limit=1)

    assert len(page.data) <= 1
    assert all(isinstance(workflow, Workflow) for workflow in page.data)
    assert isinstance(page.pagination.has_more, bool)


def test_workflows_iterate_gives_each_workflow(client: askpilot.Askpilot) -> None:
    """iterate reads each page and gives each workflow 1 time."""
    workflows = list(client.workflows.iterate(limit=2))

    ids = [workflow.id for workflow in workflows]
    assert len(ids) == len(set(ids))
    assert all(isinstance(workflow, Workflow) for workflow in workflows)


def test_workflows_get_gives_the_same_object_as_the_list(client: askpilot.Askpilot) -> None:
    """GET /v1/workflows/{id} gives the workflow of the list."""
    first = next(client.workflows.iterate(limit=1), None)
    if first is None:
        pytest.skip("The organization holds no workflow.")

    workflow = client.workflows.get(first.id)

    assert workflow.id == first.id
    assert workflow.name == first.name
    assert workflow.triggers == first.triggers


async def test_the_async_client_gives_the_organization() -> None:
    """AsyncAskpilot reads the same route."""
    async with askpilot.AsyncAskpilot() as async_client:
        organization = await async_client.organization.get()

    assert isinstance(organization.id, uuid.UUID)


def test_a_wrong_key_gives_authentication_error() -> None:
    """A key that the stack does not know gives 401."""
    wrong_key = "ask_" + "x" * 43
    with askpilot.Askpilot(api_key=wrong_key, max_retries=0) as wrong_client:
        with pytest.raises(AuthenticationError) as raised:
            wrong_client.organization.get()

    assert raised.value.code == "unauthorized"
    assert raised.value.request_id


def test_an_unknown_id_gives_not_found_error(client: askpilot.Askpilot) -> None:
    """A workflow id that does not exist gives 404."""
    with pytest.raises(NotFoundError) as raised:
        client.workflows.get(uuid.uuid4())

    assert raised.value.code == "not_found"


def test_a_bad_cursor_gives_invalid_request_error(client: askpilot.Askpilot) -> None:
    """A cursor that the stack cannot read gives 422 with the code invalid_cursor."""
    with pytest.raises(InvalidRequestError) as raised:
        client.workflows.list(cursor="x")

    assert raised.value.code == "invalid_cursor"


def test_start_gives_a_workflow_start_with_3_uuids(client: askpilot.Askpilot) -> None:
    """POST /v1/workflows/{id}/start on a workflow with an active API trigger gives 202."""
    startable = next(
        (
            workflow
            for workflow in client.workflows.iterate()
            if workflow.is_active
            and any(
                trigger.is_active and trigger.trigger_source.slug == "api"
                for trigger in workflow.triggers
            )
        ),
        None,
    )
    if startable is None:
        pytest.skip("The organization holds no active workflow with an active API trigger.")

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start = client.workflows.start(startable.id, context=f"SDK live check {stamp}")

    assert isinstance(start, WorkflowStart)
    assert isinstance(start.id, uuid.UUID)
    assert start.workflow_id == startable.id
    assert isinstance(start.session_id, uuid.UUID)


def test_the_rate_limit_gives_rate_limit_error_with_retry_after() -> None:
    """A loop of list calls with no retry reaches 429, and the error says how long to wait.

    This test is last: after it, the key has no request budget for the rest
    of the minute.
    """
    with askpilot.Askpilot(max_retries=0) as impatient_client:
        for _ in range(130):
            try:
                impatient_client.workflows.list(limit=1)
            except RateLimitError as error:
                assert error.code == "rate_limited"
                assert isinstance(error.retry_after, int)
                assert 0 <= error.retry_after <= 60
                assert error.limit is not None
                assert error.remaining == 0
                assert error.reset is not None
                return
    pytest.fail("130 calls gave no RateLimitError.")
