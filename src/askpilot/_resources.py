"""The resources of the API: the organization and the workflows.

Each resource exists 2 times, for the sync client and for the async client.
The 3 helpers at the top hold the shared logic: the path, the query, and the
body. A method is 1 call of `_send` around them.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, Optional, Union
from urllib.parse import quote

from askpilot.models import Organization, Page, Workflow, WorkflowStart

if TYPE_CHECKING:
    from askpilot._client import Askpilot, AsyncAskpilot

ORGANIZATION_PATH = "/v1/organization"
WORKFLOWS_PATH = "/v1/workflows"

#: The default page size of `iterate`: the largest page that the API gives,
#: so the loop reads the list with the fewest requests.
ITERATE_LIMIT = 100


def _workflow_path(workflow_id: Union[str, uuid.UUID], suffix: str = "") -> str:
    """Give the path of 1 workflow. The id is quoted, so it cannot change the route."""
    return f"{WORKFLOWS_PATH}/{quote(str(workflow_id), safe='')}{suffix}"


def _list_query(
    limit: Optional[int], cursor: Optional[str], search: Optional[str]
) -> dict[str, Any]:
    """Give the query of the list: the parameters that the caller gave, and no other."""
    parameters = (("limit", limit), ("cursor", cursor), ("search", search))
    return {name: value for name, value in parameters if value is not None}


def _start_body(context: str, session_id: Optional[Union[str, uuid.UUID]]) -> dict[str, Any]:
    """Give the body of the start: `session_id` only when the caller gave 1."""
    body: dict[str, Any] = {"context": context}
    if session_id is not None:
        body["session_id"] = str(session_id)
    return body


class OrganizationResource:
    """The organization that your API key belongs to. Reach it as ``client.organization``."""

    def __init__(self, client: Askpilot) -> None:
        self._client = client

    def get(self) -> Organization:
        """Returns the organization that your API key belongs to.

        There's nothing to pass: the API key determines the organization.

        Returns:
            The organization, with its id and its name.

        Raises:
            AuthenticationError: The key is missing, revoked, expired, or not valid.
            PermissionDeniedError: The key doesn't have the scope organization:read.
        """
        return self._client._send("GET", ORGANIZATION_PATH, model=Organization)


class WorkflowsResource:
    """The workflows of your organization. Reach them as ``client.workflows``."""

    def __init__(self, client: Askpilot) -> None:
        self._client = client

    def list(
        self,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Page[Workflow]:
        """Returns the workflows in your organization, one page at a time.

        The list includes every workflow, active or not, whatever its scope. Use
        limit and cursor to page through the results, and search to filter by name
        or description. To read every page in one loop, use ``iterate()``.

        Args:
            limit: How many items to return per page, from 1 to 100. The default is 25.
            cursor: Cursor from a previous response. Pass the next_cursor value to get
                the next page, or leave it out to start from the beginning.
            search: Only return items that contain this text. The match ignores case.

        Returns:
            One page: ``data`` holds the workflows, and ``pagination.next_cursor`` is
            the cursor of the next page, or None on the last page.

        Raises:
            InvalidRequestError: The cursor isn't valid (code invalid_cursor), or
                limit is outside 1 to 100 (code validation_error, with details).
            PermissionDeniedError: The key doesn't have the scope workflows:read.
        """
        query = _list_query(limit, cursor, search)
        return self._client._send("GET", WORKFLOWS_PATH, model=Page[Workflow], query=query)

    def iterate(
        self, *, limit: int = ITERATE_LIMIT, search: Optional[str] = None
    ) -> Iterator[Workflow]:
        """Yields every workflow in your organization, reading the pages as you go.

        Each page is one request. The loop stops when the API says there's no
        next page, so a short page isn't the end.

        Args:
            limit: How many items to fetch per page, from 1 to 100. The default
                is 100, which reads the list with the fewest requests.
            search: Only return items that contain this text. The match ignores case.

        Yields:
            Each workflow, newest first.

        Raises:
            InvalidRequestError: limit is outside 1 to 100.
            PermissionDeniedError: The key doesn't have the scope workflows:read.
        """
        cursor: Optional[str] = None
        while True:
            page = self.list(limit=limit, cursor=cursor, search=search)
            yield from page.data
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    def get(self, workflow_id: Union[str, uuid.UUID]) -> Workflow:
        """Returns a single workflow by its id.

        The object is the same as in the list.

        Args:
            workflow_id: Unique identifier of the workflow.

        Returns:
            The workflow.

        Raises:
            NotFoundError: The workflow doesn't exist in your organization.
            PermissionDeniedError: The key doesn't have the scope workflows:read.
        """
        return self._client._send("GET", _workflow_path(workflow_id), model=Workflow)

    def start(
        self,
        workflow_id: Union[str, uuid.UUID],
        *,
        context: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> WorkflowStart:
        """Starts a workflow with the text you provide.

        Askpilot accepts the request right away (HTTP 202) and returns before
        the workflow runs. The workflow itself runs a few seconds later, in the
        session you named or in a new one. To start, the workflow must be
        active, have an active trigger with the source api, and have at least
        one user with access.

        A request you send twice starts the workflow twice: there's no
        idempotency key. To send a second message to the same session, pass
        the session_id of the first response.

        Args:
            workflow_id: Unique identifier of the workflow.
            context: The text you want the workflow to work with. Askpilot trims
                whitespace at the start and end, and what's left must be 1 to 10,000
                characters long.
            session_id: The session to run the workflow in. It must be an open
                session in your organization. Leave it out and Askpilot creates a new
                session.

        Returns:
            The confirmation, with the id of this start request, the workflow id,
            and the session id.

        Raises:
            NotFoundError: The workflow doesn't exist in your organization.
            ConflictError: The workflow can't start now. ``code`` says why:
                workflow_inactive, api_trigger_not_configured,
                workflow_owner_missing, or session_not_open.
            InvalidRequestError: The context is empty or too long, or session_id
                names a session that doesn't exist.
            PermissionDeniedError: The key doesn't have the scope workflows:write.
        """
        body = _start_body(context, session_id)
        path = _workflow_path(workflow_id, "/start")
        return self._client._send("POST", path, model=WorkflowStart, body=body)


class AsyncOrganizationResource:
    """The organization that your API key belongs to. Reach it as ``client.organization``."""

    def __init__(self, client: AsyncAskpilot) -> None:
        self._client = client

    async def get(self) -> Organization:
        """Returns the organization that your API key belongs to.

        There's nothing to pass: the API key determines the organization.

        Returns:
            The organization, with its id and its name.

        Raises:
            AuthenticationError: The key is missing, revoked, expired, or not valid.
            PermissionDeniedError: The key doesn't have the scope organization:read.
        """
        return await self._client._send("GET", ORGANIZATION_PATH, model=Organization)


class AsyncWorkflowsResource:
    """The workflows of your organization. Reach them as ``client.workflows``."""

    def __init__(self, client: AsyncAskpilot) -> None:
        self._client = client

    async def list(
        self,
        *,
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Page[Workflow]:
        """Returns the workflows in your organization, one page at a time.

        The list includes every workflow, active or not, whatever its scope. Use
        limit and cursor to page through the results, and search to filter by name
        or description. To read every page in one loop, use ``iterate()``.

        Args:
            limit: How many items to return per page, from 1 to 100. The default is 25.
            cursor: Cursor from a previous response. Pass the next_cursor value to get
                the next page, or leave it out to start from the beginning.
            search: Only return items that contain this text. The match ignores case.

        Returns:
            One page: ``data`` holds the workflows, and ``pagination.next_cursor`` is
            the cursor of the next page, or None on the last page.

        Raises:
            InvalidRequestError: The cursor isn't valid (code invalid_cursor), or
                limit is outside 1 to 100 (code validation_error, with details).
            PermissionDeniedError: The key doesn't have the scope workflows:read.
        """
        query = _list_query(limit, cursor, search)
        return await self._client._send("GET", WORKFLOWS_PATH, model=Page[Workflow], query=query)

    async def iterate(
        self, *, limit: int = ITERATE_LIMIT, search: Optional[str] = None
    ) -> AsyncIterator[Workflow]:
        """Yields every workflow in your organization, reading the pages as you go.

        Each page is one request. The loop stops when the API says there's no
        next page, so a short page isn't the end.

        Args:
            limit: How many items to fetch per page, from 1 to 100. The default
                is 100, which reads the list with the fewest requests.
            search: Only return items that contain this text. The match ignores case.

        Yields:
            Each workflow, newest first.

        Raises:
            InvalidRequestError: limit is outside 1 to 100.
            PermissionDeniedError: The key doesn't have the scope workflows:read.
        """
        cursor: Optional[str] = None
        while True:
            page = await self.list(limit=limit, cursor=cursor, search=search)
            for workflow in page.data:
                yield workflow
            cursor = page.pagination.next_cursor
            if cursor is None:
                return

    async def get(self, workflow_id: Union[str, uuid.UUID]) -> Workflow:
        """Returns a single workflow by its id.

        The object is the same as in the list.

        Args:
            workflow_id: Unique identifier of the workflow.

        Returns:
            The workflow.

        Raises:
            NotFoundError: The workflow doesn't exist in your organization.
            PermissionDeniedError: The key doesn't have the scope workflows:read.
        """
        return await self._client._send("GET", _workflow_path(workflow_id), model=Workflow)

    async def start(
        self,
        workflow_id: Union[str, uuid.UUID],
        *,
        context: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> WorkflowStart:
        """Starts a workflow with the text you provide.

        Askpilot accepts the request right away (HTTP 202) and returns before
        the workflow runs. The workflow itself runs a few seconds later, in the
        session you named or in a new one. To start, the workflow must be
        active, have an active trigger with the source api, and have at least
        one user with access.

        A request you send twice starts the workflow twice: there's no
        idempotency key. To send a second message to the same session, pass
        the session_id of the first response.

        Args:
            workflow_id: Unique identifier of the workflow.
            context: The text you want the workflow to work with. Askpilot trims
                whitespace at the start and end, and what's left must be 1 to 10,000
                characters long.
            session_id: The session to run the workflow in. It must be an open
                session in your organization. Leave it out and Askpilot creates a new
                session.

        Returns:
            The confirmation, with the id of this start request, the workflow id,
            and the session id.

        Raises:
            NotFoundError: The workflow doesn't exist in your organization.
            ConflictError: The workflow can't start now. ``code`` says why:
                workflow_inactive, api_trigger_not_configured,
                workflow_owner_missing, or session_not_open.
            InvalidRequestError: The context is empty or too long, or session_id
                names a session that doesn't exist.
            PermissionDeniedError: The key doesn't have the scope workflows:write.
        """
        body = _start_body(context, session_id)
        path = _workflow_path(workflow_id, "/start")
        return await self._client._send("POST", path, model=WorkflowStart, body=body)
