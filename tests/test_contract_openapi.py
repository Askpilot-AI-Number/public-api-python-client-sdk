"""The contract test: the SDK follows the vendored OpenAPI document.

3 explicit maps pin the operations, the schemas, and the parameters of the
document to the SDK. A new operation, a new schema, a new field, a changed
description, or a changed nullability fails 1 of these tests, and the SDK
change follows in the same task. `tests/fixtures/OPENAPI_SOURCE.md` says where
the document comes from.
"""

import inspect
import json
import typing
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from askpilot import (
    Askpilot,
    AsyncAskpilot,
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
from tests.conftest import API_KEY, BASE_URL

DOCUMENT: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "openapi.json").read_text(encoding="utf-8")
)

# Map 1: each operation of the document, to the method of the resource.
OPERATIONS: dict[tuple[str, str], str] = {
    ("GET", "/v1/organization"): "organization.get",
    ("GET", "/v1/workflows"): "workflows.list",
    ("GET", "/v1/workflows/{workflow_id}"): "workflows.get",
    ("POST", "/v1/workflows/{workflow_id}/start"): "workflows.start",
}

# Map 2: each schema of an answer, to the model of the SDK. `Page` is the
# generic class: a parametrized pydantic model holds no docstring and no
# fields of its own, so the checks read the origin class.
SCHEMAS: dict[str, type[BaseModel]] = {
    "OrganizationOut": Organization,
    "WorkflowOut": Workflow,
    "AutoRunOut": AutoRun,
    "UserOut": User,
    "TriggerOut": Trigger,
    "TriggerSourceOut": TriggerSource,
    "TriggerEventOut": TriggerEvent,
    "SubagentSourceOut": SubagentSource,
    "FileOut": WorkflowFile,
    "WorkflowStartOut": WorkflowStart,
    "Page_WorkflowOut_": Page,
    "PageInfo": PageInfo,
    "ErrorResponse": ErrorResponse,
    "ErrorBody": ErrorBody,
    "FieldError": FieldError,
}

# The schemas that have no model, with the reason.
IGNORED_SCHEMAS: dict[str, str] = {
    "WorkflowStartIn": "the start method takes context and session_id as keyword arguments",
    "HTTPValidationError": "FastAPI adds it for a 422, and this API answers with its envelope",
    "ValidationError": "the item of HTTPValidationError",
}

# Map 3: each parameter of the document, to the method whose docstring
# explains it. The document names the same parameter 1 time for each route.
PARAMETERS: dict[tuple[str, str, str], str] = {
    ("GET", "/v1/workflows", "limit"): "workflows.list",
    ("GET", "/v1/workflows", "cursor"): "workflows.list",
    ("GET", "/v1/workflows", "search"): "workflows.list",
    ("GET", "/v1/workflows/{workflow_id}", "workflow_id"): "workflows.get",
    ("POST", "/v1/workflows/{workflow_id}/start", "workflow_id"): "workflows.start",
}


def _collapse(text: str) -> str:
    """Give the text with 1 space between the words. A docstring wraps at 100 columns."""
    return " ".join(text.split())


def _document_operations() -> dict[tuple[str, str], dict[str, Any]]:
    """Give each operation of the document by method and path."""
    return {
        (method.upper(), path): operation
        for path, operations in DOCUMENT["paths"].items()
        for method, operation in operations.items()
    }


def _method_of(client: Any, dotted: str) -> Any:
    """Give the method `resource.name` of a client."""
    resource, name = dotted.split(".")
    return getattr(getattr(client, resource), name)


def _clients() -> tuple[Askpilot, AsyncAskpilot]:
    """Make the 2 clients on a transport that answers nothing. No test here sends a request."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError("The contract test sends no request.")

    sync_client = Askpilot(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=httpx.Client(transport=httpx.MockTransport(refuse)),
    )
    async_client = AsyncAskpilot(
        api_key=API_KEY,
        base_url=BASE_URL,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
    )
    return sync_client, async_client


def _public_callables() -> dict[str, Any]:
    """Give each public callable of the package, by a name that reads well in a test id.

    The map comes from the package, and not from a list in this file. A list
    does not hold a method that a later task adds, and the guard below is then
    silent for that method.

    The holders are the 2 client classes and the 4 resource classes. The
    resource classes are in a private module, so the map reads them from the
    type of an attribute of a client.

    Returns:
        The dotted name of each public callable, and the callable.
    """
    sync_client, async_client = _clients()
    # The value says whether `__init__` belongs in the map. A person writes
    # `Askpilot(...)`, so the constructor of a client is public. A person never
    # writes `WorkflowsResource(...)`: a client makes the 4 resource groups, and
    # `_resources.py` imports the 2 client classes under `TYPE_CHECKING` to
    # break the import cycle. `get_type_hints` gives a `NameError` for such an
    # annotation, on each Python version, and that is the cost of the guard
    # against the cycle. The methods of a resource group are public, and the
    # map holds each 1.
    holders: dict[str, tuple[type, bool]] = {
        "Askpilot": (Askpilot, True),
        "AsyncAskpilot": (AsyncAskpilot, True),
        "Askpilot.organization": (type(sync_client.organization), False),
        "Askpilot.workflows": (type(sync_client.workflows), False),
        "AsyncAskpilot.organization": (type(async_client.organization), False),
        "AsyncAskpilot.workflows": (type(async_client.workflows), False),
    }
    found: dict[str, Any] = {}
    for holder_name, (holder, with_init) in holders.items():
        for name in dir(holder):
            if name.startswith("_") and not (name == "__init__" and with_init):
                continue
            value = getattr(holder, name)
            if not callable(value):
                continue
            if getattr(value, "__module__", "").split(".")[0] != "askpilot":
                continue
            found[f"{holder_name}.{name}"] = value
    return found


#: Each public callable of the package. The test below reads the annotations of
#: each 1 with `typing.get_type_hints`.
PUBLIC_CALLABLES: dict[str, Any] = _public_callables()


# ---------------------------------------------------------------------------
# The operations.
# ---------------------------------------------------------------------------


def test_each_operation_of_the_document_is_in_the_map() -> None:
    """A new operation in the document fails here, until the SDK gets its method."""
    assert set(_document_operations()) == set(OPERATIONS)


@pytest.mark.parametrize(("operation", "dotted"), list(OPERATIONS.items()))
def test_each_mapped_method_exists_on_both_clients(operation: tuple[str, str], dotted: str) -> None:
    """The sync client holds the method, and the async client holds it as a coroutine."""
    sync_client, async_client = _clients()

    sync_method = _method_of(sync_client, dotted)
    async_method = _method_of(async_client, dotted)

    assert callable(sync_method)
    assert callable(async_method)
    assert not inspect.iscoroutinefunction(sync_method)
    assert inspect.iscoroutinefunction(async_method)


@pytest.mark.parametrize(("operation", "dotted"), list(OPERATIONS.items()))
def test_the_success_schema_of_each_operation_is_the_model_of_the_method(
    operation: tuple[str, str], dotted: str
) -> None:
    """The 200 or 202 answer of the operation is the return type of the method."""
    document_operation = _document_operations()[operation]
    success = next(status for status in ("200", "202") if status in document_operation["responses"])
    reference = document_operation["responses"][success]["content"]["application/json"]["schema"]
    schema_name = reference["$ref"].rsplit("/", 1)[1]
    sync_client, _ = _clients()

    hint = typing.get_type_hints(_method_of(sync_client, dotted))["return"]

    # A parametrized pydantic model, Page[Workflow], is a subclass of Page.
    assert issubclass(hint, SCHEMAS[schema_name])


@pytest.mark.parametrize("operation", list(OPERATIONS))
def test_each_operation_needs_the_bearer_scheme_and_gives_the_envelope(
    operation: tuple[str, str],
) -> None:
    """The SDK sends a bearer key, and it reads the envelope of each error status."""
    document_operation = _document_operations()[operation]

    assert document_operation["security"] == [{"HTTPBearer": []}]
    for status, response in document_operation["responses"].items():
        if status not in ("200", "202"):
            schema = response["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/ErrorResponse"}, status


def test_the_bearer_scheme_is_the_only_security_scheme() -> None:
    """The document holds 1 scheme, and it is the bearer scheme of the Authorization header."""
    schemes = DOCUMENT["components"]["securitySchemes"]

    assert set(schemes) == {"HTTPBearer"}
    assert schemes["HTTPBearer"]["type"] == "http"
    assert schemes["HTTPBearer"]["scheme"] == "bearer"


# ---------------------------------------------------------------------------
# The schemas.
# ---------------------------------------------------------------------------


def test_each_schema_of_the_document_is_mapped_or_ignored() -> None:
    """A new schema in the document fails here, until the SDK gets its model.

    The ignore list can name a schema that the document does not hold today,
    HTTPValidationError for example: FastAPI adds it when a 422 has no other
    schema.
    """
    document_schemas = set(DOCUMENT["components"]["schemas"])

    unknown = document_schemas - set(SCHEMAS) - set(IGNORED_SCHEMAS)
    missing = set(SCHEMAS) - document_schemas

    assert unknown == set(), f"These schemas of the document have no model: {unknown}"
    assert missing == set(), f"These models map to no schema of the document: {missing}"


@pytest.mark.parametrize(("name", "model"), list(SCHEMAS.items()))
def test_the_model_holds_the_properties_of_the_schema(name: str, model: type[BaseModel]) -> None:
    """The set of the field names is the set of the property names."""
    schema = DOCUMENT["components"]["schemas"][name]

    assert set(model.model_fields) == set(schema["properties"])


@pytest.mark.parametrize(("name", "model"), list(SCHEMAS.items()))
def test_the_required_fields_of_the_model_are_the_required_properties(
    name: str, model: type[BaseModel]
) -> None:
    """A field has a default only when the document does not require the property."""
    schema = DOCUMENT["components"]["schemas"][name]

    required = {field for field, info in model.model_fields.items() if info.is_required()}

    assert required == set(schema.get("required", []))


@pytest.mark.parametrize(("name", "model"), list(SCHEMAS.items()))
def test_a_nullable_property_is_optional_on_the_model(name: str, model: type[BaseModel]) -> None:
    """A property with null in its type is `| None` on the model, and no other is."""
    schema = DOCUMENT["components"]["schemas"][name]

    for field, property_schema in schema["properties"].items():
        nullable = any(item.get("type") == "null" for item in property_schema.get("anyOf", []))
        optional = type(None) in typing.get_args(model.model_fields[field].annotation)
        assert nullable == optional, f"{name}.{field}: nullable={nullable}, optional={optional}"


@pytest.mark.parametrize(("name", "model"), list(SCHEMAS.items()))
def test_each_field_description_is_the_property_description(
    name: str, model: type[BaseModel]
) -> None:
    """The description of a field is the description of the property, verbatim."""
    schema = DOCUMENT["components"]["schemas"][name]

    for field, property_schema in schema["properties"].items():
        assert model.model_fields[field].description == property_schema["description"], (
            f"{name}.{field}"
        )


@pytest.mark.parametrize(("name", "model"), list(SCHEMAS.items()))
def test_the_model_docstring_is_the_schema_description(name: str, model: type[BaseModel]) -> None:
    """The docstring of the model is the description of the schema, verbatim.

    The comparison collapses the white space: a docstring wraps at 100 columns,
    and the document keeps the wrap of the source.
    """
    schema = DOCUMENT["components"]["schemas"][name]

    assert model.__doc__ is not None
    assert _collapse(inspect.cleandoc(model.__doc__)) == _collapse(schema["description"])


def test_each_schema_example_validates_with_the_model() -> None:
    """When a schema holds an example, the model accepts it.

    The document holds no example today, so the loop checks 0 examples. The
    test stays: the check is ready for the first example.
    """
    for name, model in SCHEMAS.items():
        schema = DOCUMENT["components"]["schemas"][name]
        examples = schema.get("examples") or []
        example = schema.get("example", examples[0] if examples else None)
        if example is not None:
            model.model_validate(example)


# ---------------------------------------------------------------------------
# The parameters.
# ---------------------------------------------------------------------------


def test_each_parameter_of_the_document_is_in_the_map() -> None:
    """A new parameter in the document fails here, until the SDK explains it."""
    parameters = {
        (method, path, parameter["name"])
        for (method, path), operation in _document_operations().items()
        for parameter in operation.get("parameters", [])
    }

    assert parameters == set(PARAMETERS)


@pytest.mark.parametrize(("parameter", "dotted"), list(PARAMETERS.items()))
def test_each_parameter_description_is_in_the_method_docstring(
    parameter: tuple[str, str, str], dotted: str
) -> None:
    """The docstring of the method holds the description of the parameter, verbatim.

    The comparison collapses the white space: a docstring wraps at 100 columns.
    """
    method, path, name = parameter
    document_parameter = next(
        item
        for item in _document_operations()[(method, path)]["parameters"]
        if item["name"] == name
    )
    sync_client, async_client = _clients()

    for client in (sync_client, async_client):
        docstring = inspect.getdoc(_method_of(client, dotted)) or ""
        assert _collapse(document_parameter["description"]) in _collapse(docstring), (
            f"{dotted}: {name}"
        )
        assert f"{name}:" in docstring


# ---------------------------------------------------------------------------
# The annotations of the package, on the lowest Python version.
# ---------------------------------------------------------------------------


def test_the_map_of_the_public_callables_holds_each_client_and_each_resource() -> None:
    """The map is not empty, and it holds the 2 constructors and the 4 methods.

    `_public_callables` reads the package. If a later change hides a name from
    `dir`, the map goes quiet and the guard below runs on nothing. This test
    sees that.
    """
    assert "Askpilot.__init__" in PUBLIC_CALLABLES
    assert "AsyncAskpilot.__init__" in PUBLIC_CALLABLES
    for holder in ("Askpilot", "AsyncAskpilot"):
        assert f"{holder}.organization.get" in PUBLIC_CALLABLES
        for name in ("list", "iterate", "get", "start"):
            assert f"{holder}.workflows.{name}" in PUBLIC_CALLABLES


@pytest.mark.parametrize("dotted", sorted(PUBLIC_CALLABLES))
def test_a_type_reader_reads_each_annotation_of_each_public_callable(dotted: str) -> None:
    """`typing.get_type_hints` gives each annotation of each public callable.

    The package ships `py.typed` and it says `Requires-Python: >=3.9`. A tool
    that reads the types of the package calls `typing.get_type_hints`, and that
    call evaluates the annotation strings of `from __future__ import
    annotations` at run time. Python 3.9 gives a `TypeError` for `X | Y`. So
    each annotation of `src/askpilot/` spells `Optional[X]` or `Union[X, Y]`,
    and this test is the guard on 3.9.

    The call itself is the first assertion: it raises for 1 wrong annotation
    anywhere in the signature. The test reads each name of the signature, and
    not the name `return` only, so an annotation of a parameter counts too.
    """
    target = PUBLIC_CALLABLES[dotted]

    hints = typing.get_type_hints(target)

    annotated = {
        name
        for name, parameter in inspect.signature(target).parameters.items()
        if parameter.annotation is not inspect.Parameter.empty
    }
    assert annotated <= set(hints), sorted(annotated - set(hints))
