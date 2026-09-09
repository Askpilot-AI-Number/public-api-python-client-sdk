"""The objects that the Askpilot API returns.

Each class here matches one object of the API reference, with the same field
names and the same descriptions. Two rules make the models safe to keep
installed while the API grows: a field that the SDK doesn't know is ignored,
and fields such as scope, type, and frequency are plain strings, because new
values may be added over time.
"""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

# Each field below that can hold None spells its type with `Optional[X]`, and
# not with `X | None`. pydantic evaluates the annotation of a field at run time,
# and Python 3.9 gives a TypeError for `X | None`. The package supports 3.9.
# `dict[str, Any]` and `list[FieldError]` are correct on 3.9: PEP 585 added
# them in that version.


class Organization(BaseModel):
    """The organization that your API key belongs to."""

    id: UUID = Field(description="Unique identifier of the organization.")
    name: str = Field(description="Name of the organization.")


class User(BaseModel):
    """A person who has access to the workflow."""

    email: str = Field(description="Email address of the user.")
    name: str = Field(
        description="Full name of the user, made from their first and last name. It's an empty "
        "string when neither is set."
    )


class SubagentSource(BaseModel):
    """A subagent source that's attached to a trigger.

    Check the type field to see what kind it is.
    """

    id: Optional[UUID] = Field(
        description="Unique identifier of the subagent source. It's null when the type is "
        "platform_internal."
    )
    name: str = Field(
        description="Name of the subagent source, such as API, Street CRM, or web-research."
    )
    type: str = Field(
        description="What kind of subagent source this is, such as api, street, or "
        "platform_internal. A platform_internal source is a subagent built into Askpilot. New "
        "types may be added over time, so don't reject values you don't recognize."
    )


class TriggerSource(BaseModel):
    """Where a trigger's events come from, such as the API or Street."""

    slug: str = Field(
        description="Machine-readable name of the source, such as api. Use this value in your code."
    )
    name: str = Field(description="Human-readable name of the source, such as API.")


class TriggerEvent(BaseModel):
    """An event that fires the trigger."""

    slug: str = Field(
        description="Machine-readable name of the event. Use this value in your code."
    )
    name: str = Field(description="Human-readable name of the event.")


class Trigger(BaseModel):
    """A trigger that starts this workflow.

    You can start a workflow through this API when it has an active trigger
    whose source is api.
    """

    id: UUID = Field(description="Unique identifier of the trigger.")
    name: str = Field(description="Name of the trigger. It can be empty.")
    is_active: bool = Field(
        description="Whether the trigger is active. A paused trigger is inactive, but it still "
        "appears in this list."
    )
    trigger_source: TriggerSource = Field(
        description="Where the trigger's events come from, such as the API or Street."
    )
    events: list[TriggerEvent] = Field(
        description="The events that fire this trigger and start the workflow."
    )
    filters: Optional[dict[str, Any]] = Field(
        description="Extra conditions for the trigger, exactly as configured in Askpilot. It's "
        "null when the trigger has none."
    )
    input_message: str = Field(
        description="Text that Askpilot adds to the session message when this trigger starts the "
        "workflow. It can be empty."
    )
    subagent_sources: list[SubagentSource] = Field(
        description="The subagent sources attached to this trigger. Sources with a type other "
        "than platform_internal come first, sorted by name, followed by the platform_internal "
        "sources, also sorted by name."
    )


class WorkflowFile(BaseModel):
    """A file that belongs to the workflow.

    The response includes the name and location of the file, but not its
    content.
    """

    id: UUID = Field(description="Unique identifier of the file.")
    name: str = Field(description="Name of the file, such as PROCESS.md.")
    path: list[str] = Field(
        description="The folders that contain the file, from the top level down. An empty list "
        "means the file is at the root of the workflow."
    )


class AutoRun(BaseModel):
    """The auto-run settings of a workflow.

    Auto-run lets a workflow run again on a schedule.
    """

    enabled: Optional[bool] = Field(
        description="Whether the workflow runs again automatically on a schedule. It's null if "
        "auto-run was never configured."
    )
    frequency: Optional[str] = Field(
        description="How often the workflow runs automatically: hourly, daily, weekly, or "
        "monthly. It's null if there's no schedule."
    )


class Workflow(BaseModel):
    """A workflow in your organization.

    The list and the single-workflow endpoints both return this object.
    """

    id: UUID = Field(description="Unique identifier of the workflow.")
    name: str = Field(description="Name of the workflow.")
    description: str = Field(
        description="Description of what the workflow does, as written in Askpilot."
    )
    scope: str = Field(
        description="Who can use the workflow: company_wide means everyone in your organization, "
        "and only_me means a single user. New values may be added over time, so don't reject "
        "values you don't recognize."
    )
    is_active: bool = Field(
        description="Whether the workflow is active. An inactive workflow can't be started "
        "through the API."
    )
    auto_run: AutoRun = Field(description="The auto-run settings of the workflow.")
    users: list[User] = Field(
        description="The people who have access to this workflow, sorted by email address."
    )
    triggers: list[Trigger] = Field(
        description="The triggers that can start this workflow, oldest first. Paused triggers "
        "are included."
    )
    files: list[WorkflowFile] = Field(
        description="The files that belong to this workflow, sorted by folder and then by name. "
        "The content of a file isn't included."
    )
    created_at: datetime = Field(description="When the workflow was created.")
    updated_at: datetime = Field(description="When the workflow was last changed.")


class WorkflowStart(BaseModel):
    """Confirmation that Askpilot accepted your request to start the workflow.

    The workflow doesn't run right away: Askpilot starts it a few seconds
    later. Keep session_id if you want to start the workflow again in the same
    session.
    """

    id: UUID = Field(
        description="Unique identifier of this start request. Include it when you contact support."
    )
    workflow_id: UUID = Field(description="Unique identifier of the workflow that's being started.")
    session_id: UUID = Field(
        description="Unique identifier of the session the workflow runs in. It's the session you "
        "passed in, or a new one that Askpilot created for you."
    )


class PageInfo(BaseModel):
    """Tells you whether there are more results and how to fetch the next page."""

    next_cursor: Optional[str] = Field(
        description="Cursor for the next page of results. It's null when you've reached the "
        "last page."
    )
    has_more: bool = Field(description="Whether there are more results after this page.")


T = TypeVar("T")


# Python 3.10 has no `class Page[T]` syntax, so the class takes Generic[T].
class Page(BaseModel, Generic[T]):
    """A page of results. The data list holds the items of this page, and pagination tells you
    how to get the next one.
    """

    data: list[T] = Field(
        description="The items on this page. It's an empty list when there are no results."
    )
    pagination: PageInfo = Field(
        description="Whether there are more results, and the cursor for the next page."
    )


class FieldError(BaseModel):
    """Details about one field of your request that failed validation.

    Only 422 responses include these.
    """

    field: str = Field(
        description="Name of the field that failed validation, such as context. For a nested "
        "field, the parts are joined with a dot."
    )
    code: str = Field(
        description="A short code that says what's wrong with the field, such as "
        "string_too_short or not_found. Match on this value in your code."
    )
    message: str = Field(description="A human-readable explanation of what's wrong with the field.")


class ErrorBody(BaseModel):
    """Details about the error."""

    code: str = Field(
        description="A stable code that identifies the error, such as not_found or rate_limited. "
        "Match on this value in your code; it won't change."
    )
    message: str = Field(
        description="A human-readable explanation of the error. This text may change, so don't "
        "match on it."
    )
    request_id: str = Field(
        description="Unique identifier of this request. Include it when you contact support."
    )
    details: Optional[list[FieldError]] = Field(
        default=None,
        description="The fields that failed validation. It's only included on 422 responses.",
    )


class ErrorResponse(BaseModel):
    """The body of every error response, whatever the status code."""

    error: ErrorBody = Field(
        description="What went wrong: the error code, a message, and the id of the request."
    )
