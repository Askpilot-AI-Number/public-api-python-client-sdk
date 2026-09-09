"""The official Python client for the Askpilot public API.

Create a client with your API key, then call the API through its resources::

    import askpilot

    client = askpilot.Askpilot(api_key="ask_...")
    organization = client.organization.get()
    for workflow in client.workflows.iterate():
        print(workflow.name)

Every error the SDK raises is an ``AskpilotError``. Read the README for the
full guide.
"""

from askpilot._client import Askpilot, AsyncAskpilot
from askpilot._http import SDK_VERSION
from askpilot.errors import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AskpilotError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    UnexpectedResponseError,
)
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

__version__ = SDK_VERSION

__all__ = [
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "Askpilot",
    "AskpilotError",
    "AsyncAskpilot",
    "AuthenticationError",
    "AutoRun",
    "ConfigurationError",
    "ConflictError",
    "ErrorBody",
    "ErrorResponse",
    "FieldError",
    "InvalidRequestError",
    "NotFoundError",
    "Organization",
    "Page",
    "PageInfo",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "SubagentSource",
    "Trigger",
    "TriggerEvent",
    "TriggerSource",
    "UnexpectedResponseError",
    "User",
    "Workflow",
    "WorkflowFile",
    "WorkflowStart",
]
