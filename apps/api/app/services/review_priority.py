from __future__ import annotations

from app.models import ReviewTrigger


def derive_review_requirements(
    *,
    evidence_count: int,
    conflicting_evidence: bool,
    execution_available: bool,
    model_reported_confidence: float | None,
    confidence_threshold: float = 0.70,
) -> tuple[bool, list[ReviewTrigger]]:
    """Build review signals; model confidence is a prioritization hint, not a probability."""

    reasons: list[ReviewTrigger] = []
    if evidence_count == 0:
        reasons.append(ReviewTrigger.MISSING_EVIDENCE)
    if conflicting_evidence:
        reasons.append(ReviewTrigger.CONFLICTING_EVIDENCE)
    if not execution_available:
        reasons.append(ReviewTrigger.EXECUTION_UNAVAILABLE)
    if model_reported_confidence is None or model_reported_confidence < confidence_threshold:
        reasons.append(ReviewTrigger.LOW_MODEL_REPORTED_CONFIDENCE)
    return bool(reasons), reasons

