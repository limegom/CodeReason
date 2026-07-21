from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExportRecord:
    student_id: str
    filename: str
    ai_suggested_total: float | None
    human_approved: bool
    final_total: float | None
    rubric_scores: dict[str, float | None] = field(default_factory=dict)
    error_category: str = "NONE"
    review_status: str = "REVIEW_REQUIRED"
    short_feedback: str = ""

    def __post_init__(self) -> None:
        if not self.human_approved and self.final_total is not None:
            raise ValueError("final_total is available only after human approval")
        if self.human_approved and self.final_total is None:
            raise ValueError("a human-approved export requires final_total")


def _safe_cell(value: object) -> object:
    if not isinstance(value, str):
        return value
    # Prevent spreadsheet formula execution while preserving the visible value.
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value.replace("\x00", "")


def build_csv_export(records: list[ExportRecord]) -> str:
    rubric_ids = sorted({rubric_id for record in records for rubric_id in record.rubric_scores})
    fieldnames = [
        "student_id",
        "filename",
        "ai_suggested_total",
        "final_total",
        *[f"rubric_{rubric_id}" for rubric_id in rubric_ids],
        "error_category",
        "review_status",
        "short_feedback",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    for record in records:
        row: dict[str, object] = {
            "student_id": _safe_cell(record.student_id),
            "filename": _safe_cell(record.filename),
            "ai_suggested_total": "" if record.ai_suggested_total is None else record.ai_suggested_total,
            "final_total": record.final_total if record.human_approved else "",
            "error_category": record.error_category,
            "review_status": record.review_status,
            "short_feedback": _safe_cell(record.short_feedback),
        }
        for rubric_id in rubric_ids:
            score = record.rubric_scores.get(rubric_id)
            row[f"rubric_{rubric_id}"] = "" if score is None else score
        writer.writerow(row)
    return stream.getvalue()

