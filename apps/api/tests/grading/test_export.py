import csv
import io

import pytest

from app.grading.export import ExportRecord, build_csv_export


def test_unapproved_submission_has_blank_final_total():
    csv_text = build_csv_export(
        [
            ExportRecord(
                student_id="student-01",
                filename="answer.py",
                ai_suggested_total=17,
                human_approved=False,
                final_total=None,
                rubric_scores={"structure": None},
            )
        ]
    )
    row = next(csv.DictReader(io.StringIO(csv_text)))
    assert row["ai_suggested_total"] == "17"
    assert row["final_total"] == ""


def test_rejects_unapproved_final_total():
    with pytest.raises(ValueError, match="only after human approval"):
        ExportRecord(
            student_id="s1",
            filename="a.py",
            ai_suggested_total=10,
            human_approved=False,
            final_total=10,
        )


def test_csv_cells_are_safe_for_spreadsheets():
    csv_text = build_csv_export(
        [
            ExportRecord(
                student_id="=cmd|' /C calc'!A0",
                filename="answer.py",
                ai_suggested_total=20,
                human_approved=True,
                final_total=20,
            )
        ]
    )
    row = next(csv.DictReader(io.StringIO(csv_text)))
    assert row["student_id"].startswith("'=")

