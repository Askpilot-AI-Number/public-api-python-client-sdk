"""The models of the answers.

The models keep the pydantic default for an unknown field, so a later version
of the API can add a field and an installed SDK keeps working.
"""

import uuid
from datetime import timedelta

import pytest
from pydantic import BaseModel

from askpilot.models import (
    AutoRun,
    ErrorBody,
    ErrorResponse,
    FieldError,
    Organization,
    Page,
    PageInfo,
    SubagentSource,
    Trigger,
    TriggerEvent,
    TriggerSource,
    User,
    Workflow,
    WorkflowFile,
    WorkflowStart,
)
from tests.conftest import (
    ORGANIZATION_BODY,
    ORGANIZATION_ID,
    PAGE_BODY,
    START_BODY,
    WORKFLOW_BODY,
    WORKFLOW_ID,
)

ANSWER_MODELS: list[type[BaseModel]] = [
    Organization,
    Workflow,
    AutoRun,
    User,
    Trigger,
    TriggerSource,
    TriggerEvent,
    SubagentSource,
    WorkflowFile,
    WorkflowStart,
    Page,
    PageInfo,
    ErrorResponse,
    ErrorBody,
    FieldError,
]


def test_workflow_validates_the_example_body() -> None:
    """The workflow object of the API reference validates, with typed values."""
    workflow = Workflow.model_validate(WORKFLOW_BODY)

    assert workflow.id == uuid.UUID(WORKFLOW_ID)
    assert workflow.auto_run == AutoRun(enabled=True, frequency="daily")
    assert workflow.users == [User(email="jane@acme-estates.example", name="Jane Doe")]
    assert workflow.triggers[0].trigger_source == TriggerSource(slug="api", name="API")
    assert workflow.triggers[0].events[0].slug == "workflow.start_via_api"
    assert workflow.triggers[0].filters is None
    assert workflow.files[1].path == ["reference"]


def test_a_time_of_the_answer_is_aware_and_utc() -> None:
    """`created_at` and `updated_at` are aware datetimes in UTC."""
    workflow = Workflow.model_validate(WORKFLOW_BODY)

    assert workflow.created_at.tzinfo is not None
    assert workflow.created_at.utcoffset() == timedelta(0)
    assert workflow.created_at.microsecond == 418272
    assert workflow.updated_at.utcoffset() == timedelta(0)


def test_a_platform_subagent_has_id_none() -> None:
    """A subagent source of the type platform_internal gives `id` None."""
    workflow = Workflow.model_validate(WORKFLOW_BODY)

    sources = workflow.triggers[0].subagent_sources
    assert sources[2] == SubagentSource(id=None, name="web-research", type="platform_internal")
    assert sources[0].id == uuid.UUID("9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d")


def test_an_unknown_field_is_ignored() -> None:
    """A field that the SDK does not know does not stop the validation."""
    body = {**WORKFLOW_BODY, "brand_new_field": {"a": 1}}

    workflow = Workflow.model_validate(body)

    assert "brand_new_field" not in workflow.model_dump()


@pytest.mark.parametrize("model", ANSWER_MODELS)
def test_each_answer_model_keeps_the_pydantic_default_for_unknown_fields(
    model: type[BaseModel],
) -> None:
    """No answer model sets extra="forbid"."""
    assert model.model_config.get("extra") in (None, "ignore")


def test_an_unknown_value_of_scope_type_and_frequency_passes() -> None:
    """The 3 fields are text, and never an Enum: the set of values can grow."""
    body = {
        **WORKFLOW_BODY,
        "scope": "team_only",
        "auto_run": {"enabled": True, "frequency": "yearly"},
    }
    body["triggers"] = [
        {
            **WORKFLOW_BODY["triggers"][0],
            "subagent_sources": [{"id": None, "name": "x", "type": "brand_new_type"}],
        }
    ]

    workflow = Workflow.model_validate(body)

    assert workflow.scope == "team_only"
    assert workflow.auto_run.frequency == "yearly"
    assert workflow.triggers[0].subagent_sources[0].type == "brand_new_type"


def test_organization_validates_the_example_body() -> None:
    """The organization object gives a UUID and a name."""
    organization = Organization.model_validate(ORGANIZATION_BODY)

    assert organization.id == uuid.UUID(ORGANIZATION_ID)
    assert organization.name == "Acme Estates"


def test_workflow_start_validates_the_example_body() -> None:
    """The start answer gives 3 UUIDs."""
    start = WorkflowStart.model_validate(START_BODY)

    assert isinstance(start.id, uuid.UUID)
    assert start.workflow_id == uuid.UUID(WORKFLOW_ID)
    assert isinstance(start.session_id, uuid.UUID)


def test_page_of_workflow_validates_the_list_body() -> None:
    """`Page[Workflow]` gives typed items and the page info."""
    page = Page[Workflow].model_validate(PAGE_BODY)

    assert isinstance(page.data[0], Workflow)
    assert page.pagination == PageInfo(next_cursor=None, has_more=False)


def test_page_with_a_cursor_validates() -> None:
    """A page that is not the last holds the cursor of the next page."""
    body = {"data": [], "pagination": {"next_cursor": "eyJ2IjoxfQ", "has_more": True}}

    page = Page[Workflow].model_validate(body)

    assert page.data == []
    assert page.pagination.next_cursor == "eyJ2IjoxfQ"
    assert page.pagination.has_more is True


def test_error_response_validates_with_and_without_details() -> None:
    """`details` is on a 422 only, so the field has the default None."""
    plain = ErrorResponse.model_validate(
        {"error": {"code": "not_found", "message": "No.", "request_id": "r1"}}
    )
    detailed = ErrorResponse.model_validate(
        {
            "error": {
                "code": "validation_error",
                "message": "No.",
                "request_id": "r2",
                "details": [{"field": "context", "code": "string_too_short", "message": "Short."}],
            }
        }
    )

    assert plain.error.details is None
    assert detailed.error.details == [
        FieldError(field="context", code="string_too_short", message="Short.")
    ]
