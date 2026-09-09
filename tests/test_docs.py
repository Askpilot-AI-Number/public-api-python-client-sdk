"""The documents are complete.

Each field of each model appears in the document of its tag, and each public
name of the package appears in the README or in `docs/`. The checks are cheap,
and they keep the documents complete when the API grows.
"""

from pathlib import Path

import pytest
from pydantic import BaseModel

import askpilot
from askpilot import (
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

ROOT = Path(__file__).parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
DOCS = {path.name: path.read_text(encoding="utf-8") for path in (ROOT / "docs").glob("*.md")}

# The document of each model: the organization in organization.md, and each
# other model in workflows.md.
MODEL_DOCUMENTS: dict[type[BaseModel], str] = {
    Organization: "organization.md",
    Workflow: "workflows.md",
    AutoRun: "workflows.md",
    User: "workflows.md",
    Trigger: "workflows.md",
    TriggerSource: "workflows.md",
    TriggerEvent: "workflows.md",
    SubagentSource: "workflows.md",
    WorkflowFile: "workflows.md",
    WorkflowStart: "workflows.md",
    Page: "workflows.md",
    PageInfo: "workflows.md",
    ErrorResponse: "workflows.md",
    ErrorBody: "workflows.md",
    FieldError: "workflows.md",
}


def test_the_docs_directory_holds_1_file_for_each_tag() -> None:
    """The document has 2 tags, Organization and Workflows, and docs/ has 2 files."""
    assert set(DOCS) == {"organization.md", "workflows.md"}


@pytest.mark.parametrize(("model", "document"), list(MODEL_DOCUMENTS.items()))
def test_each_field_of_the_model_appears_in_its_document(
    model: type[BaseModel], document: str
) -> None:
    """The field table of the document names each field of the model."""
    text = DOCS[document]

    missing = [field for field in model.model_fields if f"`{field}`" not in text]

    assert missing == [], f"{model.__name__}: {missing} not in docs/{document}"


@pytest.mark.parametrize(("model", "document"), list(MODEL_DOCUMENTS.items()))
def test_each_model_name_appears_in_its_document(model: type[BaseModel], document: str) -> None:
    """The document names the model that a method gives."""
    assert f"`{model.__name__}`" in DOCS[document]


@pytest.mark.parametrize("name", askpilot.__all__)
def test_each_public_name_appears_in_the_readme_or_in_docs(name: str) -> None:
    """A reader can find each public name in the documents."""
    texts = [README, *DOCS.values()]

    assert any(f"`{name}`" in text or f"{name}(" in text for text in texts), name


def test_the_readme_links_each_document() -> None:
    """The README points to each file of docs/."""
    for name in DOCS:
        assert f"docs/{name}" in README


def test_workflows_document_says_what_202_means() -> None:
    """The start gives 202: Askpilot accepted the start, and the workflow runs a few seconds later."""
    text = DOCS["workflows.md"]

    assert "202" in text
    assert "few seconds" in text


def test_the_readme_shows_the_logging_setup() -> None:
    """The README shows how to turn the DEBUG line on."""
    assert 'logging.getLogger("askpilot")' in README
    assert "logging.DEBUG" in README
