from app.models import EvidenceKind, EvidenceVisibility


def test_only_deterministic_observations_are_primary_evidence_kinds() -> None:
    assert {kind.value for kind in EvidenceKind} == {
        "TestResult",
        "ExecutionError",
        "ASTFinding",
        "StaticFinding",
        "SourceCodeLocation",
    }


def test_evidence_visibility_has_explicit_disclosure_levels() -> None:
    assert {visibility.value for visibility in EvidenceVisibility} == {
        "INTERNAL",
        "REVIEWER_ONLY",
        "STUDENT_VISIBLE",
    }
