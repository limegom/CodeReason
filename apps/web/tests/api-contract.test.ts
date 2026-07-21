import { describe, expect, it } from "vitest";
import {
  ContractError,
  adaptAssignmentOverview,
  adaptSubmissionBundle,
  parseAssignmentOverviews,
  parseSubmissionBundle,
} from "@/lib/api-contract";

const assignment = {
  id: "assignment-uuid",
  demo_key: null,
  title: "Live assignment",
  description: "Evidence-bound grading",
  total_score: "20.0",
  time_limit_ms: 2000,
  python_version: "3.12",
  execution_mode: "FUNCTION",
  entry_function: "solve",
  arguments_schema: { type: "array" },
  comparison_mode: "JSON_VALUE",
  provenance: "STORED_LIVE",
  analysis_input_version: 3,
};

function bundle(finalGrade: unknown, analysisStatus = "COMPLETED") {
  const evidence = {
    id: "evidence-1",
    test_result_id: "result-1",
    kind: "TestResult",
    visibility: "STUDENT_VISIBLE",
    summary: "Visible JSON value comparison passed.",
    details: { passed: true },
    start_line: null,
    end_line: null,
    provenance: "STORED_LIVE",
  };
  return {
    submission: {
      id: "submission-uuid",
      assignment_id: assignment.id,
      student_reference: "student-01",
      status: "APPROVED",
      source_version: 2,
      provenance: "STORED_LIVE",
    },
    assignment,
    source_file: { id: "source-1", filename: "solution.py", content: "def solve():\n    return 1\n" },
    rubric_criteria: [{
      id: "criterion-1",
      criterion_key: "correctness",
      title: "Correctness",
      max_score: "20.0",
      active: true,
      approval_status: "HUMAN_APPROVED",
      sort_order: 0,
    }],
    execution_run: {
      id: "run-1",
      status: "COMPLETED",
      error_category: null,
      exception_type: null,
      signature_status: "MATCH",
      provenance: "STORED_LIVE",
    },
    test_results: [{
      id: "result-1",
      test_case_id: "visible-1",
      status: "PASSED",
      applied_comparison_mode: "JSON_VALUE",
      error_category: null,
      actual_output: "1",
      stdout: null,
      stderr: null,
      exit_code: 0,
      duration_ms: 3.5,
      test_name: "Visible basic case",
      is_hidden: false,
      visibility: "STUDENT_VISIBLE",
      input_payload: [],
      expected_output: 1,
    }],
    evidence: [evidence],
    analysis: {
      id: "analysis-1",
      status: analysisStatus,
      model_name: "gpt-5.6",
      provider: "openai",
      model_reported_confidence: 0.82,
      review_required: true,
      review_reasons: ["LOW_MODEL_REPORTED_CONFIDENCE"],
      stale_reason: analysisStatus === "STALE" ? "Rubric changed" : null,
      external_data_manifest: {
        status: "SENT",
        fields_sent: ["redacted_source_code", "sanitized_primary_evidence"],
        redacted: true,
        redaction_count: 2,
        redaction_categories: ["EMAIL", "API_KEY"],
        hidden_test_values_withheld: true,
        model_tools_enabled: false,
      },
      provenance: "STORED_LIVE",
      rubric_scores: [{
        rubric_criterion_id: "criterion-1",
        suggested_score: "18.0",
        interpretation: "The linked results show evidence of correct behavior on the available tests.",
        model_reported_confidence: 0.82,
        primary_evidence: [evidence],
      }],
    },
    human_reviews: [{
      id: "review-1",
      reviewer: "Instructor",
      status: "APPROVED",
      decision_reason: "Evidence reviewed.",
      is_current: true,
      approved_at: "2026-07-15T00:00:00Z",
      created_at: "2026-07-15T00:00:00Z",
      scores: [{ rubric_criterion_id: "criterion-1", awarded_score: "19.0" }],
    }],
    final_grade: finalGrade,
    analysis_summary: { error_category: "NONE" },
    student_feedback: [{
      concept: "Return value",
      shows_evidence_of: "The visible result shows evidence of the expected JSON value.",
      likely_misconception: "",
      next_step: "Check additional edge cases.",
    }],
    uncertainties: ["Hidden values remain withheld."],
  };
}

describe("reviewer DTO contract", () => {
  it("adapts assignment overview decimal fields and provenance", () => {
    const parsed = parseAssignmentOverviews([{ ...assignment, submission_count: 2, pending_review_count: 1, approved_count: 1, consistency_issue_count: 0, analyzed_percent: 100, rubric_ready: true }]);
    expect(adaptAssignmentOverview(parsed[0])).toMatchObject({
      id: "assignment-uuid",
      totalScore: 20,
      provenance: "STORED_LIVE",
      submissions: 2,
      rubricReady: true,
    });
  });

  it("uses only final_grade for finalTotal and preserves the transmission manifest", () => {
    const adapted = adaptSubmissionBundle(parseSubmissionBundle(bundle({ final_total: "19.0" })));
    expect(adapted.finalTotal).toBe(19);
    expect(adapted.aiSuggestedTotal).toBe(18);
    expect(adapted.externalDataManifest).toMatchObject({
      status: "SENT",
      fieldsSent: ["redacted_source_code", "sanitized_primary_evidence"],
      redactionCount: 2,
      hiddenTestValuesWithheld: true,
      modelToolsEnabled: false,
    });
  });

  it("does not infer a final total from an APPROVED submission or current review", () => {
    const adapted = adaptSubmissionBundle(parseSubmissionBundle(bundle(null)));
    expect(adapted.status).toBe("APPROVED");
    expect(adapted.finalTotal).toBeUndefined();
  });

  it("does not mark a rubric ready when approved maxima differ from assignment total", () => {
    const raw = bundle(null);
    raw.rubric_criteria[0].max_score = "19.0";
    const adapted = adaptSubmissionBundle(parseSubmissionBundle(raw));
    expect(adapted.rubricReady).toBe(false);
  });

  it("maps stale analysis to a blocked stale review state", () => {
    const adapted = adaptSubmissionBundle(parseSubmissionBundle(bundle(null, "STALE")));
    expect(adapted.status).toBe("STALE");
    expect(adapted.staleReason).toBe("Rubric changed");
    expect(adapted.reviewRequired).toBe(true);
  });

  it("rejects AI interpretation masquerading as Primary Evidence", () => {
    const invalid = bundle(null);
    invalid.evidence[0].kind = "AIInterpretation";
    expect(() => parseSubmissionBundle(invalid)).toThrow(ContractError);
  });
});
