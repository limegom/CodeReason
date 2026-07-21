from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import ComparisonMode, ExecutionMode


def function_assignment_payload() -> dict[str, object]:
    return {
        "title": "Matrix construction",
        "description": "Build a matrix through the requested function contract.",
        "execution_mode": "FUNCTION",
        "entry_function": "make_matrix",
        "arguments_schema": {
            "type": "object",
            "properties": {
                "data": {"type": "array"},
                "rows": {"type": "integer", "minimum": 0},
                "cols": {"type": "integer", "minimum": 0},
            },
            "required": ["data", "rows", "cols"],
        },
        "comparison_mode": "JSON_VALUE",
    }


def test_execution_and_comparison_modes_are_an_explicit_closed_contract() -> None:
    assert {mode.value for mode in ExecutionMode} == {"FUNCTION", "STDIN_STDOUT"}
    assert {mode.value for mode in ComparisonMode} == {
        "EXACT",
        "IGNORE_FINAL_NEWLINE",
        "TRIM_TRAILING_WHITESPACE",
        "TOKEN_BASED",
        "JSON_VALUE",
    }


def test_assignment_crud_preserves_execution_contract(client: TestClient) -> None:
    create_response = client.post("/api/assignments", json=function_assignment_payload())
    assert create_response.status_code == 201, create_response.text

    created = create_response.json()
    assignment_id = created["id"]
    assert created["execution_mode"] == "FUNCTION"
    assert created["entry_function"] == "make_matrix"
    assert created["arguments_schema"]["required"] == ["data", "rows", "cols"]
    assert created["comparison_mode"] == "JSON_VALUE"

    get_response = client.get(f"/api/assignments/{assignment_id}")
    assert get_response.status_code == 200, get_response.text
    assert get_response.json() == created

    list_response = client.get("/api/assignments")
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()] == [assignment_id]

    update_response = client.patch(
        f"/api/assignments/{assignment_id}",
        json={"title": "Updated matrix assignment", "comparison_mode": "TOKEN_BASED"},
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()
    assert updated["title"] == "Updated matrix assignment"
    assert updated["comparison_mode"] == "TOKEN_BASED"
    assert updated["entry_function"] == "make_matrix"

    delete_response = client.delete(f"/api/assignments/{assignment_id}")
    assert delete_response.status_code in {200, 204}, delete_response.text
    if delete_response.status_code == 200:
        assert delete_response.json() == {"deleted": True, "id": assignment_id}
    assert client.get(f"/api/assignments/{assignment_id}").status_code == 404


def test_function_mode_requires_an_entry_function(client: TestClient) -> None:
    payload = function_assignment_payload()
    payload["entry_function"] = None

    response = client.post("/api/assignments", json=payload)

    assert response.status_code == 422, response.text
    assert "entry_function" in response.text


def test_stdin_stdout_mode_does_not_require_an_entry_function(client: TestClient) -> None:
    response = client.post(
        "/api/assignments",
        json={
            "title": "Echo normalized tokens",
            "description": "Read stdin and write the answer to stdout.",
            "execution_mode": "STDIN_STDOUT",
            "entry_function": None,
            "arguments_schema": {"type": "string"},
            "comparison_mode": "IGNORE_FINAL_NEWLINE",
        },
    )

    assert response.status_code == 201, response.text
    created = response.json()
    assert created["execution_mode"] == "STDIN_STDOUT"
    assert created["entry_function"] is None
    assert created["comparison_mode"] == "IGNORE_FINAL_NEWLINE"


def test_stdin_stdout_mode_rejects_a_function_entrypoint(client: TestClient) -> None:
    response = client.post(
        "/api/assignments",
        json={
            "title": "Standard stream program",
            "execution_mode": "STDIN_STDOUT",
            "entry_function": "main",
            "arguments_schema": {"type": "string"},
            "comparison_mode": "EXACT",
        },
    )

    assert response.status_code == 422, response.text
    assert "entry_function" in response.text
