"""The organization resource, sync and async."""

import uuid

import pytest

from askpilot import AuthenticationError, Organization, PermissionDeniedError
from tests.conftest import (
    BASE_URL,
    ORGANIZATION_BODY,
    ORGANIZATION_ID,
    Recorder,
    error_body,
    json_response,
    make_async_client,
    make_client,
)


def test_get_sends_get_v1_organization_and_gives_the_organization() -> None:
    """The method reads GET /v1/organization."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_client(recorder)

    organization = client.organization.get()

    assert recorder.request.method == "GET"
    assert str(recorder.request.url) == f"{BASE_URL}/v1/organization"
    assert organization == Organization(id=uuid.UUID(ORGANIZATION_ID), name="Acme Estates")


async def test_the_async_get_gives_the_organization() -> None:
    """The async method reads the same route."""
    recorder = Recorder(json_response(200, ORGANIZATION_BODY))
    client = make_async_client(recorder)

    organization = await client.organization.get()

    assert str(recorder.request.url) == f"{BASE_URL}/v1/organization"
    assert organization.id == uuid.UUID(ORGANIZATION_ID)


def test_a_401_gives_authentication_error() -> None:
    """A key that the service refuses gives AuthenticationError with the code."""
    client = make_client(Recorder(json_response(401, error_body("unauthorized"))))

    with pytest.raises(AuthenticationError) as raised:
        client.organization.get()

    assert raised.value.code == "unauthorized"


def test_a_403_gives_permission_denied_error_with_the_message() -> None:
    """A key without the scope gives PermissionDeniedError, and the message names the scope."""
    body = error_body("forbidden", "This API key does not have the scope organization:read.")
    client = make_client(Recorder(json_response(403, body)))

    with pytest.raises(PermissionDeniedError) as raised:
        client.organization.get()

    assert "organization:read" in raised.value.message
