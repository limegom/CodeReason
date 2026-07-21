import type {
  AssignmentSummary,
  ConsistencyIssue,
  DataSource,
  Evidence,
  EvidenceKind,
  ExternalDataManifest,
  Provenance,
  Submission,
  SubmissionStatus,
  TestResultDetail,
} from "./types";

type JsonRecord = Record<string, unknown>;

const PROVENANCE = ["LIVE", "STORED_LIVE", "DEMO_FIXTURE", "UNAVAILABLE"] as const;
const EXECUTION_MODES = ["FUNCTION", "STDIN_STDOUT"] as const;
const COMPARISON_MODES = [
  "EXACT",
  "IGNORE_FINAL_NEWLINE",
  "TRIM_TRAILING_WHITESPACE",
  "TOKEN_BASED",
  "JSON_VALUE",
] as const;
const SUBMISSION_STATUSES = [
  "UPLOADED",
  "QUEUED",
  "ANALYZING",
  "REVIEW_REQUIRED",
  "APPROVED",
  "FAILED",
] as const;
const ANALYSIS_STATUSES = ["PENDING", "RUNNING", "COMPLETED", "FAILED", "STALE"] as const;
const EVIDENCE_KINDS = [
  "TestResult",
  "ExecutionError",
  "ASTFinding",
  "StaticFinding",
  "SourceCodeLocation",
] as const;
const VISIBILITIES = ["INTERNAL", "REVIEWER_ONLY", "STUDENT_VISIBLE"] as const;
const RUBRIC_STATUSES = ["DRAFT", "AI_STRUCTURED", "HUMAN_APPROVED", "ARCHIVED"] as const;

export class ContractError extends Error {
  constructor(message: string) {
    super(`API contract mismatch: ${message}`);
    this.name = "ContractError";
  }
}

function record(value: unknown, path: string): JsonRecord {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ContractError(`${path} must be an object`);
  }
  return value as JsonRecord;
}

function array(value: unknown, path: string): unknown[] {
  if (!Array.isArray(value)) throw new ContractError(`${path} must be an array`);
  return value;
}

function string(value: unknown, path: string): string {
  if (typeof value !== "string") throw new ContractError(`${path} must be a string`);
  return value;
}

function nullableString(value: unknown, path: string): string | null {
  return value === null ? null : string(value, path);
}

function boolean(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") throw new ContractError(`${path} must be a boolean`);
  return value;
}

function numberLike(value: unknown, path: string): number {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(parsed)) throw new ContractError(`${path} must be a finite number`);
  return parsed;
}

function nullableNumberLike(value: unknown, path: string): number | null {
  return value === null ? null : numberLike(value, path);
}

function enumeration<const T extends readonly string[]>(value: unknown, values: T, path: string): T[number] {
  const parsed = string(value, path);
  if (!values.includes(parsed)) throw new ContractError(`${path} contains unsupported value ${parsed}`);
  return parsed as T[number];
}

function stringArray(value: unknown, path: string): string[] {
  return array(value, path).map((item, index) => string(item, `${path}[${index}]`));
}

export interface WireAssignmentRead {
  id: string;
  demo_key: string | null;
  title: string;
  description: string;
  total_score: number;
  time_limit_ms: number;
  python_version: string;
  execution_mode: (typeof EXECUTION_MODES)[number];
  entry_function: string | null;
  arguments_schema: JsonRecord;
  comparison_mode: (typeof COMPARISON_MODES)[number];
  provenance: Provenance;
  analysis_input_version: number;
}

export interface WireAssignmentOverviewRead extends WireAssignmentRead {
  submission_count: number;
  pending_review_count: number;
  approved_count: number;
  consistency_issue_count: number;
  analyzed_percent: number;
  rubric_ready: boolean;
}

interface WireSubmissionRead {
  id: string;
  assignment_id: string;
  student_reference: string;
  status: (typeof SUBMISSION_STATUSES)[number];
  source_version: number;
  provenance: Provenance;
}

interface WireSourceFileRead {
  id: string;
  filename: string;
  content: string;
}

interface WireRubricCriterionRead {
  id: string;
  criterion_key: string;
  title: string;
  max_score: number;
  active: boolean;
  approval_status: (typeof RUBRIC_STATUSES)[number];
  sort_order: number;
}

interface WireExecutionRunRead {
  id: string;
  status: string;
  error_category: string | null;
  exception_type: string | null;
  signature_status: string | null;
  provenance: Provenance;
}

interface WireTestResultRead {
  id: string;
  test_case_id: string;
  status: string;
  applied_comparison_mode: string;
  error_category: string | null;
  actual_output: string | null;
  stdout: string | null;
  stderr: string | null;
  exit_code: number | null;
  duration_ms: number | null;
  test_name: string | null;
  is_hidden: boolean | null;
  visibility: (typeof VISIBILITIES)[number];
  input_payload?: unknown;
  expected_output?: unknown;
}

interface WireEvidenceRead {
  id: string;
  test_result_id: string | null;
  kind: (typeof EVIDENCE_KINDS)[number];
  visibility: (typeof VISIBILITIES)[number];
  summary: string;
  details: JsonRecord;
  start_line: number | null;
  end_line: number | null;
  provenance: Provenance;
}

interface WireRubricScoreRead {
  rubric_criterion_id: string;
  suggested_score: number;
  interpretation: string;
  model_reported_confidence: number | null;
  primary_evidence: WireEvidenceRead[];
}

interface WireAIAnalysisRead {
  id: string;
  status: (typeof ANALYSIS_STATUSES)[number];
  model_name: string;
  provider: string;
  model_reported_confidence: number | null;
  review_required: boolean;
  review_reasons: string[];
  stale_reason: string | null;
  external_data_manifest: JsonRecord;
  provenance: Provenance;
  rubric_scores: WireRubricScoreRead[];
}

interface WireHumanRubricScoreRead {
  rubric_criterion_id: string;
  awarded_score: number;
}

interface WireHumanReviewRead {
  id: string;
  reviewer: string;
  status: string;
  decision_reason: string | null;
  is_current: boolean;
  approved_at: string | null;
  created_at: string;
  scores: WireHumanRubricScoreRead[];
}

interface WireFinalGradeRead {
  final_total: number;
}

export interface WireSubmissionReviewBundleRead {
  submission: WireSubmissionRead;
  assignment: WireAssignmentRead;
  source_file: WireSourceFileRead | null;
  rubric_criteria: WireRubricCriterionRead[];
  execution_run: WireExecutionRunRead | null;
  test_results: WireTestResultRead[];
  evidence: WireEvidenceRead[];
  analysis: WireAIAnalysisRead | null;
  human_reviews: WireHumanReviewRead[];
  final_grade: WireFinalGradeRead | null;
  analysis_summary: JsonRecord | null;
  student_feedback: JsonRecord[];
  uncertainties: string[];
}

function parseAssignment(value: unknown, path: string): WireAssignmentRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    demo_key: nullableString(item.demo_key, `${path}.demo_key`),
    title: string(item.title, `${path}.title`),
    description: string(item.description, `${path}.description`),
    total_score: numberLike(item.total_score, `${path}.total_score`),
    time_limit_ms: numberLike(item.time_limit_ms, `${path}.time_limit_ms`),
    python_version: string(item.python_version, `${path}.python_version`),
    execution_mode: enumeration(item.execution_mode, EXECUTION_MODES, `${path}.execution_mode`),
    entry_function: nullableString(item.entry_function, `${path}.entry_function`),
    arguments_schema: record(item.arguments_schema, `${path}.arguments_schema`),
    comparison_mode: enumeration(item.comparison_mode, COMPARISON_MODES, `${path}.comparison_mode`),
    provenance: enumeration(item.provenance, PROVENANCE, `${path}.provenance`),
    analysis_input_version: numberLike(item.analysis_input_version, `${path}.analysis_input_version`),
  };
}

export function parseAssignmentOverviews(value: unknown): WireAssignmentOverviewRead[] {
  return array(value, "assignment_overviews").map((raw, index) => {
    const path = `assignment_overviews[${index}]`;
    const item = record(raw, path);
    return {
      ...parseAssignment(item, path),
      submission_count: numberLike(item.submission_count, `${path}.submission_count`),
      pending_review_count: numberLike(item.pending_review_count, `${path}.pending_review_count`),
      approved_count: numberLike(item.approved_count, `${path}.approved_count`),
      consistency_issue_count: numberLike(item.consistency_issue_count, `${path}.consistency_issue_count`),
      analyzed_percent: numberLike(item.analyzed_percent, `${path}.analyzed_percent`),
      rubric_ready: boolean(item.rubric_ready, `${path}.rubric_ready`),
    };
  });
}

function parseSubmission(value: unknown, path: string): WireSubmissionRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    assignment_id: string(item.assignment_id, `${path}.assignment_id`),
    student_reference: string(item.student_reference, `${path}.student_reference`),
    status: enumeration(item.status, SUBMISSION_STATUSES, `${path}.status`),
    source_version: numberLike(item.source_version, `${path}.source_version`),
    provenance: enumeration(item.provenance, PROVENANCE, `${path}.provenance`),
  };
}

function parseSource(value: unknown, path: string): WireSourceFileRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    filename: string(item.filename, `${path}.filename`),
    content: string(item.content, `${path}.content`),
  };
}

function parseRubric(value: unknown, path: string): WireRubricCriterionRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    criterion_key: string(item.criterion_key, `${path}.criterion_key`),
    title: string(item.title, `${path}.title`),
    max_score: numberLike(item.max_score, `${path}.max_score`),
    active: boolean(item.active, `${path}.active`),
    approval_status: enumeration(item.approval_status, RUBRIC_STATUSES, `${path}.approval_status`),
    sort_order: numberLike(item.sort_order, `${path}.sort_order`),
  };
}

function parseRun(value: unknown, path: string): WireExecutionRunRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    status: string(item.status, `${path}.status`),
    error_category: nullableString(item.error_category, `${path}.error_category`),
    exception_type: nullableString(item.exception_type, `${path}.exception_type`),
    signature_status: nullableString(item.signature_status, `${path}.signature_status`),
    provenance: enumeration(item.provenance, PROVENANCE, `${path}.provenance`),
  };
}

function parseTestResult(value: unknown, path: string): WireTestResultRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    test_case_id: string(item.test_case_id, `${path}.test_case_id`),
    status: string(item.status, `${path}.status`),
    applied_comparison_mode: string(item.applied_comparison_mode, `${path}.applied_comparison_mode`),
    error_category: nullableString(item.error_category, `${path}.error_category`),
    actual_output: nullableString(item.actual_output, `${path}.actual_output`),
    stdout: nullableString(item.stdout, `${path}.stdout`),
    stderr: nullableString(item.stderr, `${path}.stderr`),
    exit_code: nullableNumberLike(item.exit_code, `${path}.exit_code`),
    duration_ms: nullableNumberLike(item.duration_ms, `${path}.duration_ms`),
    test_name: item.test_name === undefined ? null : nullableString(item.test_name, `${path}.test_name`),
    is_hidden: item.is_hidden === undefined ? null : item.is_hidden === null ? null : boolean(item.is_hidden, `${path}.is_hidden`),
    visibility: enumeration(item.visibility, VISIBILITIES, `${path}.visibility`),
    input_payload: item.input_payload,
    expected_output: item.expected_output,
  };
}

function parseEvidence(value: unknown, path: string): WireEvidenceRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    test_result_id: nullableString(item.test_result_id, `${path}.test_result_id`),
    kind: enumeration(item.kind, EVIDENCE_KINDS, `${path}.kind`),
    visibility: enumeration(item.visibility, VISIBILITIES, `${path}.visibility`),
    summary: string(item.summary, `${path}.summary`),
    details: record(item.details, `${path}.details`),
    start_line: nullableNumberLike(item.start_line, `${path}.start_line`),
    end_line: nullableNumberLike(item.end_line, `${path}.end_line`),
    provenance: enumeration(item.provenance, PROVENANCE, `${path}.provenance`),
  };
}

function parseRubricScore(value: unknown, path: string): WireRubricScoreRead {
  const item = record(value, path);
  return {
    rubric_criterion_id: string(item.rubric_criterion_id, `${path}.rubric_criterion_id`),
    suggested_score: numberLike(item.suggested_score, `${path}.suggested_score`),
    interpretation: string(item.interpretation, `${path}.interpretation`),
    model_reported_confidence: nullableNumberLike(
      item.model_reported_confidence,
      `${path}.model_reported_confidence`,
    ),
    primary_evidence: array(item.primary_evidence, `${path}.primary_evidence`).map((evidence, index) =>
      parseEvidence(evidence, `${path}.primary_evidence[${index}]`),
    ),
  };
}

function parseAnalysis(value: unknown, path: string): WireAIAnalysisRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    status: enumeration(item.status, ANALYSIS_STATUSES, `${path}.status`),
    model_name: string(item.model_name, `${path}.model_name`),
    provider: string(item.provider, `${path}.provider`),
    model_reported_confidence: nullableNumberLike(
      item.model_reported_confidence,
      `${path}.model_reported_confidence`,
    ),
    review_required: boolean(item.review_required, `${path}.review_required`),
    review_reasons: stringArray(item.review_reasons, `${path}.review_reasons`),
    stale_reason: nullableString(item.stale_reason, `${path}.stale_reason`),
    external_data_manifest: record(item.external_data_manifest, `${path}.external_data_manifest`),
    provenance: enumeration(item.provenance, PROVENANCE, `${path}.provenance`),
    rubric_scores: array(item.rubric_scores, `${path}.rubric_scores`).map((score, index) =>
      parseRubricScore(score, `${path}.rubric_scores[${index}]`),
    ),
  };
}

function parseHumanReview(value: unknown, path: string): WireHumanReviewRead {
  const item = record(value, path);
  return {
    id: string(item.id, `${path}.id`),
    reviewer: string(item.reviewer, `${path}.reviewer`),
    status: string(item.status, `${path}.status`),
    decision_reason: nullableString(item.decision_reason, `${path}.decision_reason`),
    is_current: boolean(item.is_current, `${path}.is_current`),
    approved_at: nullableString(item.approved_at, `${path}.approved_at`),
    created_at: string(item.created_at, `${path}.created_at`),
    scores: array(item.scores, `${path}.scores`).map((score, index) => {
      const scorePath = `${path}.scores[${index}]`;
      const parsed = record(score, scorePath);
      return {
        rubric_criterion_id: string(parsed.rubric_criterion_id, `${scorePath}.rubric_criterion_id`),
        awarded_score: numberLike(parsed.awarded_score, `${scorePath}.awarded_score`),
      };
    }),
  };
}

export function parseSubmissionBundle(value: unknown): WireSubmissionReviewBundleRead {
  const item = record(value, "submission_bundle");
  return {
    submission: parseSubmission(item.submission, "submission_bundle.submission"),
    assignment: parseAssignment(item.assignment, "submission_bundle.assignment"),
    source_file:
      item.source_file === null ? null : parseSource(item.source_file, "submission_bundle.source_file"),
    rubric_criteria: array(item.rubric_criteria, "submission_bundle.rubric_criteria").map((rubric, index) =>
      parseRubric(rubric, `submission_bundle.rubric_criteria[${index}]`),
    ),
    execution_run:
      item.execution_run === null
        ? null
        : parseRun(item.execution_run, "submission_bundle.execution_run"),
    test_results: array(item.test_results, "submission_bundle.test_results").map((result, index) =>
      parseTestResult(result, `submission_bundle.test_results[${index}]`),
    ),
    evidence: array(item.evidence, "submission_bundle.evidence").map((evidence, index) =>
      parseEvidence(evidence, `submission_bundle.evidence[${index}]`),
    ),
    analysis: item.analysis === null ? null : parseAnalysis(item.analysis, "submission_bundle.analysis"),
    human_reviews: array(item.human_reviews, "submission_bundle.human_reviews").map((review, index) =>
      parseHumanReview(review, `submission_bundle.human_reviews[${index}]`),
    ),
    final_grade:
      item.final_grade === null
        ? null
        : {
            final_total: numberLike(
              record(item.final_grade, "submission_bundle.final_grade").final_total,
              "submission_bundle.final_grade.final_total",
            ),
          },
    analysis_summary:
      item.analysis_summary === null
        ? null
        : record(item.analysis_summary, "submission_bundle.analysis_summary"),
    student_feedback: array(item.student_feedback, "submission_bundle.student_feedback").map(
      (feedback, index) => record(feedback, `submission_bundle.student_feedback[${index}]`),
    ),
    uncertainties: stringArray(item.uncertainties, "submission_bundle.uncertainties"),
  };
}

export function parseSubmissionBundles(value: unknown): WireSubmissionReviewBundleRead[] {
  return array(value, "submission_bundles").map((bundle, index) => {
    try {
      return parseSubmissionBundle(bundle);
    } catch (error) {
      if (error instanceof ContractError) {
        throw new ContractError(`submission_bundles[${index}]: ${error.message.replace(/^API contract mismatch: /, "")}`);
      }
      throw error;
    }
  });
}

export function adaptAssignmentOverview(
  item: WireAssignmentOverviewRead,
  dataSource: DataSource = "API",
): AssignmentSummary {
  return {
    id: item.id,
    title: item.title,
    description: item.description,
    totalScore: item.total_score,
    executionMode: item.execution_mode,
    entryFunction: item.entry_function ?? undefined,
    comparisonMode: item.comparison_mode,
    progress: item.analyzed_percent,
    submissions: item.submission_count,
    pendingReview: item.pending_review_count,
    approved: item.approved_count,
    consistencyIssues: item.consistency_issue_count,
    rubricReady: item.rubric_ready,
    provenance: item.provenance,
    dataSource,
  };
}

const KIND_MAP: Record<(typeof EVIDENCE_KINDS)[number], EvidenceKind> = {
  TestResult: "TEST_RESULT",
  ExecutionError: "EXECUTION_ERROR",
  ASTFinding: "AST_FINDING",
  StaticFinding: "STATIC_FINDING",
  SourceCodeLocation: "SOURCE_CODE_LOCATION",
};

const KIND_TITLES: Record<EvidenceKind, string> = {
  TEST_RESULT: "Test result",
  EXECUTION_ERROR: "Execution error",
  AST_FINDING: "AST finding",
  STATIC_FINDING: "Static finding",
  SOURCE_CODE_LOCATION: "Source location",
};

function adaptEvidence(item: WireEvidenceRead, tests: Map<string, WireTestResultRead>): Evidence {
  const test = item.test_result_id ? tests.get(item.test_result_id) : undefined;
  const detailPassed = item.details.passed;
  const status = test?.status ?? (typeof item.details.status === "string" ? item.details.status : undefined);
  const passed =
    typeof detailPassed === "boolean"
      ? detailPassed
      : status === "PASSED"
        ? true
        : status === "FAILED" || status === "ERROR" || item.kind === "ExecutionError"
          ? false
          : null;
  const kind = KIND_MAP[item.kind];
  return {
    id: item.id,
    kind,
    title: KIND_TITLES[kind],
    message: item.summary,
    passed,
    visibility: item.visibility,
    provenance: item.provenance,
    lineStart: item.start_line ?? undefined,
    lineEnd: item.end_line ?? undefined,
    testCase: test?.test_case_id,
  };
}

function adaptManifest(raw: JsonRecord): ExternalDataManifest {
  const fields = Array.isArray(raw.fields_sent)
    ? raw.fields_sent.filter((item): item is string => typeof item === "string")
    : [];
  const categories = Array.isArray(raw.redaction_categories)
    ? raw.redaction_categories.filter((item): item is string => typeof item === "string")
    : [];
  return {
    status: typeof raw.status === "string" ? raw.status : undefined,
    fieldsSent: fields,
    redacted: typeof raw.redacted === "boolean" ? raw.redacted : undefined,
    redactionCount: typeof raw.redaction_count === "number" ? raw.redaction_count : undefined,
    redactionCategories: categories,
    redactionIsBestEffort:
      typeof raw.redaction_is_best_effort === "boolean" ? raw.redaction_is_best_effort : undefined,
    hiddenTestValuesWithheld:
      typeof raw.hidden_test_values_withheld === "boolean" ? raw.hidden_test_values_withheld : undefined,
    modelToolsEnabled:
      typeof raw.model_tools_enabled === "boolean" ? raw.model_tools_enabled : undefined,
  };
}

function adaptStatus(bundle: WireSubmissionReviewBundleRead): SubmissionStatus {
  if (bundle.analysis?.status === "STALE") return "STALE";
  switch (bundle.submission.status) {
    case "UPLOADED":
      return "PENDING";
    case "QUEUED":
    case "ANALYZING":
      return "RUNNING";
    case "REVIEW_REQUIRED":
      return "REVIEW_REQUIRED";
    case "APPROVED":
      return "APPROVED";
    case "FAILED":
      return "FAILED";
  }
}

export function adaptSubmissionBundle(
  bundle: WireSubmissionReviewBundleRead,
  dataSource: DataSource = "API",
): Submission {
  const analysis = bundle.analysis;
  const activeRubrics = bundle.rubric_criteria
    .filter((criterion) => criterion.active)
    .sort((left, right) => left.sort_order - right.sort_order);
  const rubricReady =
    activeRubrics.length > 0 &&
    activeRubrics.every((criterion) => criterion.approval_status === "HUMAN_APPROVED") &&
    Math.abs(activeRubrics.reduce((sum, criterion) => sum + criterion.max_score, 0) - bundle.assignment.total_score) < 0.000_001;
  const aiScores = new Map(
    (analysis?.rubric_scores ?? []).map((score) => [score.rubric_criterion_id, score]),
  );
  const currentReview = bundle.human_reviews.find((review) => review.is_current);
  const humanScores = new Map(
    (currentReview?.scores ?? []).map((score) => [score.rubric_criterion_id, score.awarded_score]),
  );
  const tests = new Map(bundle.test_results.map((result) => [result.id, result]));
  const evidence = bundle.evidence.map((item) => adaptEvidence(item, tests));
  const testResults: TestResultDetail[] = bundle.test_results.map((result) => {
    const linkedEvidence = bundle.evidence.find((item) => item.test_result_id === result.id);
    return {
      id: result.id,
      testCaseId: result.test_case_id,
      testName: result.test_name ?? undefined,
      isHidden: result.is_hidden ?? linkedEvidence?.visibility === "REVIEWER_ONLY",
      inputPayload: result.input_payload,
      expectedOutput: result.expected_output,
      status: result.status,
      comparisonMode: result.applied_comparison_mode,
      actualOutput: result.actual_output ?? undefined,
      stdout: result.stdout ?? undefined,
      stderr: result.stderr ?? undefined,
      exitCode: result.exit_code ?? undefined,
      durationMs: result.duration_ms ?? undefined,
      errorCategory: result.error_category ?? undefined,
      visibility: result.visibility ?? linkedEvidence?.visibility ?? "REVIEWER_ONLY",
    };
  });
  const scores = activeRubrics.map((criterion) => {
    const score = aiScores.get(criterion.id);
    return {
      rubricId: criterion.id,
      title: criterion.title,
      maxScore: criterion.max_score,
      aiSuggestedScore: score?.suggested_score ?? null,
      humanScore: humanScores.get(criterion.id),
      modelReportedConfidence: score?.model_reported_confidence ?? null,
      reason: score?.interpretation ?? "No current AI suggestion is available for this criterion.",
      evidenceIds: score?.primary_evidence.map((item) => item.id) ?? [],
      manualReviewRequired: analysis?.review_required ?? true,
    };
  });
  const feedback = bundle.student_feedback.map((item) => ({
    concept: typeof item.concept === "string" ? item.concept : "Concept feedback",
    showsEvidenceOf: typeof item.shows_evidence_of === "string" ? item.shows_evidence_of : "",
    likelyMisconception:
      typeof item.likely_misconception === "string" ? item.likely_misconception : "",
    nextStep: typeof item.next_step === "string" ? item.next_step : "",
  }));
  const summaryCategory = bundle.analysis_summary?.error_category;
  const aiSuggested = analysis && analysis.rubric_scores.length
    ? analysis.rubric_scores.reduce((sum, score) => sum + score.suggested_score, 0)
    : null;
  return {
    id: bundle.submission.id,
    assignmentId: bundle.assignment.id,
    assignmentTitle: bundle.assignment.title,
    totalScore: bundle.assignment.total_score,
    studentId: bundle.submission.student_reference,
    filename: bundle.source_file?.filename ?? "Source unavailable",
    status: adaptStatus(bundle),
    analysisStatus: analysis?.status,
    analysisId: analysis?.id,
    staleReason: analysis?.stale_reason ?? undefined,
    reviewRequired: analysis?.review_required ?? bundle.submission.status !== "APPROVED",
    reviewReasons: analysis?.review_reasons ?? ["MISSING_EVIDENCE"],
    rubricReady,
    errorCategory:
      typeof summaryCategory === "string"
        ? summaryCategory
        : bundle.execution_run?.error_category ?? (bundle.execution_run ? "NONE" : "PENDING"),
    executionStatus: bundle.execution_run?.status,
    aiSuggestedTotal: aiSuggested,
    finalTotal: bundle.final_grade?.final_total,
    provenance: bundle.submission.provenance,
    executionProvenance: bundle.execution_run?.provenance,
    analysisProvenance: analysis?.provenance,
    dataSource,
    source: bundle.source_file?.content ?? "",
    scores,
    evidence,
    testResults,
    reviewHistory: bundle.human_reviews.map((review) => ({
      id: review.id,
      reviewer: review.reviewer,
      status: review.status,
      decisionReason: review.decision_reason ?? undefined,
      isCurrent: review.is_current,
      approvedAt: review.approved_at ?? undefined,
      createdAt: review.created_at,
      total: review.scores.reduce((sum, score) => sum + score.awarded_score, 0),
    })),
    uncertainties: bundle.uncertainties,
    feedback,
    externalDataManifest: analysis ? adaptManifest(analysis.external_data_manifest) : undefined,
    modelName: analysis?.model_name,
    provider: analysis?.provider,
  };
}

export interface WireConsistencyIssueRead {
  id: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  status: "OPEN" | "DISMISSED" | "RESOLVED";
  potential_issue: boolean;
  description: string;
  submission_id: string;
  compared_submission_id: string | null;
  fingerprint_hash: string;
  test_status_vector: string[];
  error_category: string | null;
  ast_feature_summary: JsonRecord;
  exception_type: string | null;
  signature_status: string | null;
}

export function parseConsistencyIssues(value: unknown): WireConsistencyIssueRead[] {
  return array(value, "consistency_issues").map((raw, index) => {
    const path = `consistency_issues[${index}]`;
    const item = record(raw, path);
    return {
      id: string(item.id, `${path}.id`),
      severity: enumeration(item.severity, ["LOW", "MEDIUM", "HIGH"] as const, `${path}.severity`),
      status: enumeration(item.status, ["OPEN", "DISMISSED", "RESOLVED"] as const, `${path}.status`),
      potential_issue: boolean(item.potential_issue, `${path}.potential_issue`),
      description: string(item.description, `${path}.description`),
      submission_id: string(item.submission_id, `${path}.submission_id`),
      compared_submission_id: nullableString(
        item.compared_submission_id,
        `${path}.compared_submission_id`,
      ),
      fingerprint_hash: string(item.fingerprint_hash, `${path}.fingerprint_hash`),
      test_status_vector: stringArray(item.test_status_vector, `${path}.test_status_vector`),
      error_category: nullableString(item.error_category, `${path}.error_category`),
      ast_feature_summary: record(item.ast_feature_summary, `${path}.ast_feature_summary`),
      exception_type: nullableString(item.exception_type, `${path}.exception_type`),
      signature_status: nullableString(item.signature_status, `${path}.signature_status`),
    };
  });
}

export function adaptConsistencyIssue(item: WireConsistencyIssueRead): ConsistencyIssue {
  return {
    id: item.id,
    severity: item.severity,
    status: item.status,
    potentialIssue: item.potential_issue,
    description: item.description,
    submissionId: item.submission_id,
    comparedSubmissionId: item.compared_submission_id ?? undefined,
    fingerprint: item.fingerprint_hash,
    testStatusVector: item.test_status_vector,
    errorCategory: item.error_category ?? undefined,
    astFeatureSummary: item.ast_feature_summary,
    exceptionType: item.exception_type ?? undefined,
    signatureStatus: item.signature_status ?? undefined,
  };
}
