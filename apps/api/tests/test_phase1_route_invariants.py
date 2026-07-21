from __future__ import annotations

from fastapi.testclient import TestClient


def create_assignment(client: TestClient, *, comparison_mode: str = "EXACT") -> dict:
    response = client.post(
        "/api/assignments",
        json={
            "title": "Matrix assignment",
            "description": "Return the requested matrix.",
            "total_score": 10,
            "execution_mode": "FUNCTION",
            "entry_function": "make_matrix",
            "arguments_schema": {"type": "object"},
            "comparison_mode": comparison_mode,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_hidden_test_student_views_withhold_inputs_answers_and_evidence_details(
    client: TestClient,
) -> None:
    assignment = create_assignment(client, comparison_mode="JSON_VALUE")
    test_case_response = client.post(
        f"/api/assignments/{assignment['id']}/test-cases",
        json={
            "name": "hidden edge case",
            "input_payload": {"secret_input": [1, 2, 3]},
            "expected_output": {"secret_answer": [[1, 2, 3]]},
            "is_hidden": True,
        },
    )
    assert test_case_response.status_code == 201, test_case_response.text
    test_case = test_case_response.json()

    student_tests = client.get(
        f"/api/assignments/{assignment['id']}/test-cases/student"
    )
    assert student_tests.status_code == 200, student_tests.text
    assert student_tests.json()[0]["input_payload"] is None
    assert student_tests.json()[0]["expected_output"] is None

    submission = client.post(
        "/api/submissions",
        json={"assignment_id": assignment["id"], "student_reference": "opaque-1"},
    ).json()
    execution_run = client.post(
        f"/api/submissions/{submission['id']}/execution-runs",
        json={"runner_version": "test", "status": "COMPLETED"},
    ).json()
    test_result_response = client.post(
        f"/api/submissions/{submission['id']}/execution-runs/{execution_run['id']}/test-results",
        json={
            "test_case_id": test_case["id"],
            "status": "FAILED",
            "applied_comparison_mode": "JSON_VALUE",
            "actual_output": "SECRET_ACTUAL_OUTPUT",
        },
    )
    assert test_result_response.status_code == 201, test_result_response.text
    test_result = test_result_response.json()
    evidence_response = client.post(
        f"/api/submissions/{submission['id']}/evidence",
        json={
            "execution_run_id": execution_run["id"],
            "test_result_id": test_result["id"],
            "kind": "TestResult",
            "visibility": "STUDENT_VISIBLE",
            "summary": "SECRET_EXPECTED_VALUE did not match",
            "details": {"expected": "SECRET_EXPECTED_VALUE", "input": "SECRET_INPUT"},
        },
    )
    assert evidence_response.status_code == 201, evidence_response.text

    student_evidence = client.get(f"/api/submissions/{submission['id']}/evidence/student")
    assert student_evidence.status_code == 200, student_evidence.text
    serialized = str(student_evidence.json())
    assert "SECRET_" not in serialized
    assert "withheld" in student_evidence.json()[0]["summary"]


def test_test_result_records_and_enforces_the_effective_comparison_policy(
    client: TestClient,
) -> None:
    assignment = create_assignment(client, comparison_mode="TOKEN_BASED")
    test_case = client.post(
        f"/api/assignments/{assignment['id']}/test-cases",
        json={"name": "public", "input_payload": "a b", "expected_output": "a b"},
    ).json()
    submission = client.post(
        "/api/submissions",
        json={"assignment_id": assignment["id"], "student_reference": "opaque-2"},
    ).json()
    execution_run = client.post(
        f"/api/submissions/{submission['id']}/execution-runs",
        json={"runner_version": "test"},
    ).json()
    endpoint = (
        f"/api/submissions/{submission['id']}/execution-runs/"
        f"{execution_run['id']}/test-results"
    )

    mismatch = client.post(
        endpoint,
        json={
            "test_case_id": test_case["id"],
            "status": "PASSED",
            "applied_comparison_mode": "EXACT",
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "COMPARISON_POLICY_MISMATCH"

    recorded = client.post(
        endpoint,
        json={
            "test_case_id": test_case["id"],
            "status": "PASSED",
            "applied_comparison_mode": "TOKEN_BASED",
        },
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["applied_comparison_mode"] == "TOKEN_BASED"


def test_final_grade_endpoint_uses_only_current_human_approved_scores(
    client: TestClient,
) -> None:
    assignment = create_assignment(client)
    rubric = client.post(
        f"/api/assignments/{assignment['id']}/rubrics",
        json={
            "criterion_key": "correctness",
            "title": "Correctness",
            "description": "Observed results satisfy the function contract.",
            "max_score": 10,
            "origin": "AI_STRUCTURED",
        },
    ).json()
    approval = client.post(
        f"/api/assignments/{assignment['id']}/rubrics/{rubric['id']}/approve",
        json={"approved_by": "ta@example.test"},
    )
    assert approval.status_code == 200, approval.text
    submission = client.post(
        "/api/submissions",
        json={"assignment_id": assignment["id"], "student_reference": "opaque-3"},
    ).json()

    unavailable = client.get(f"/api/submissions/{submission['id']}/final-grade")
    assert unavailable.status_code == 409

    review = client.post(
        f"/api/submissions/{submission['id']}/human-reviews",
        json={
            "reviewer": "ta@example.test",
            "status": "APPROVED",
            "decision_reason": "Reviewed the linked primary evidence.",
            "scores": [
                {
                    "rubric_criterion_id": rubric["id"],
                    "awarded_score": 7.5,
                    "reason": "Human decision based on observed behavior.",
                }
            ],
        },
    )
    assert review.status_code == 201, review.text

    final_grade = client.get(f"/api/submissions/{submission['id']}/final-grade")
    assert final_grade.status_code == 200, final_grade.text
    assert float(final_grade.json()["final_total"]) == 7.5
    assert final_grade.json()["human_review_id"] == review.json()["id"]
