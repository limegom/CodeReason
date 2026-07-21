from app.grading.consistency import ConsistencyRecord, find_potential_issues


def record(submission_id: str, score: float, **overrides):
    values = {
        "submission_id": submission_id,
        "rubric_id": "r1",
        "rubric_max_score": 10,
        "test_status_vector": ("PASSED", "WRONG_ANSWER"),
        "error_category": "LOGIC",
        "ast_feature_summary": {"loop": True, "return": True},
        "exception_type": None,
        "signature_status": "MATCH",
        "ai_suggested_score": score,
        "final_human_score": None,
        "model_reported_confidence": 0.9,
        "approved": False,
        "evidence_ids": ("ev-1",),
    }
    values.update(overrides)
    return ConsistencyRecord(**values)


def test_fingerprint_contains_required_deterministic_features():
    first = record("s1", 8)
    second = record("s2", 8, exception_type="IndexError")
    assert first.fingerprint() != second.fingerprint()


def test_same_fingerprint_large_score_gap_is_potential_issue_only():
    issues = find_potential_issues([record("s1", 3), record("s2", 9)])
    issue = next(item for item in issues if len(item.submission_ids) == 2)
    assert issue.reason.startswith("Potential issue:")
    assert issue.submission_ids == ("s1", "s2")


def test_missing_evidence_deduction_is_detected():
    issues = find_potential_issues([record("s1", 4, evidence_ids=())])
    assert any("no linked Primary Evidence" in item.reason for item in issues)


def test_repeated_explanation_across_different_observations_is_only_a_potential_issue():
    explanation = "The linked evidence suggests a gap in this criterion."
    issues = find_potential_issues(
        [
            record("s1", 4, explanation=explanation, error_category="LOGIC"),
            record(
                "s2",
                4,
                explanation=explanation,
                error_category="RUNTIME",
                exception_type="IndexError",
            ),
        ]
    )
    repeated = next(item for item in issues if "same explanation" in item.reason)
    assert repeated.reason.startswith("Potential issue:")
    assert repeated.submission_ids == ("s1", "s2")
