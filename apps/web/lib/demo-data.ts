import type { AssignmentSummary, Submission } from "./types";

export const demoAssignment: AssignmentSummary = {
  id: "demo",
  title: "Matrix Transformation Assignment",
  description:
    "Implement make_matrix(data, rows, cols) and return a row-major two-dimensional list.",
  totalScore: 20,
  executionMode: "FUNCTION",
  entryFunction: "make_matrix",
  comparisonMode: "JSON_VALUE",
  progress: 80,
  submissions: 5,
  pendingReview: 3,
  approved: 1,
  consistencyIssues: 2,
  rubricReady: true,
  provenance: "DEMO_FIXTURE",
  dataSource: "LOCAL_FIXTURE",
};

const rubric = [
  ["structure", "Function & parameters", 3],
  ["approach", "2D list construction", 5],
  ["dimensions", "Correct dimensions", 4],
  ["values", "Value order & output", 6],
  ["quality", "Code quality", 2],
] as const;

const demoFixtureAnalysis = {
  executionProvenance: "DEMO_FIXTURE" as const,
  analysisProvenance: "DEMO_FIXTURE" as const,
  modelName: "stored-fixture",
  provider: "stored-fixture",
  externalDataManifest: {
    status: "NOT_SENT_FIXTURE",
    fieldsSent: [],
    redactionCategories: [],
    redactionCount: 0,
    hiddenTestValuesWithheld: true,
    modelToolsEnabled: false,
  },
  reviewHistory: [] as Submission["reviewHistory"],
};

function scores(
  values: number[],
  confidence: number,
  evidencePrefix: string,
  reviewRequired = true,
) {
  return rubric.map(([rubricId, title, maxScore], index) => ({
    rubricId,
    title,
    maxScore,
    aiSuggestedScore: values[index],
      modelReportedConfidence: confidence,
    reason:
      values[index] === maxScore
        ? "The submitted code shows evidence satisfying this criterion in the linked Primary Evidence."
        : "The linked execution and source findings suggest a gap in this rubric criterion.",
    evidenceIds: [`${evidencePrefix}-${index + 1}`],
    manualReviewRequired: reviewRequired,
  }));
}

const correctSource = `def make_matrix(data, rows, cols):
    if rows * cols != len(data):
        raise ValueError("invalid dimensions")
    return [data[i:i + cols] for i in range(0, len(data), cols)]`;

const wrongSource = `def make_matrix(data, rows, cols):
    matrix = []
    for row in range(rows):
        current = []
        for column in range(cols):
            index = row * cols + column + 1
            current.append(data[index] if index < len(data) else None)
        matrix.append(current)
    return matrix`;

function makeEvidence(prefix: string, failure = false) {
  return [
    {
      id: `${prefix}-1`,
      kind: "AST_FINDING" as const,
      title: "Entry function signature",
      message: "make_matrix(data, rows, cols) is defined with the expected parameters.",
      passed: true,
      visibility: "STUDENT_VISIBLE" as const,
      lineStart: 1,
      lineEnd: 1,
    },
    {
      id: `${prefix}-2`,
      kind: "AST_FINDING" as const,
      title: "Nested construction",
      message: "The source contains loop-driven two-dimensional list construction.",
      passed: true,
      visibility: "STUDENT_VISIBLE" as const,
      lineStart: 2,
      lineEnd: 9,
    },
    {
      id: `${prefix}-3`,
      kind: "TEST_RESULT" as const,
      title: failure ? "Visible test mismatch" : "Visible tests passed",
      message: failure
        ? "JSON value comparison found a different value at [0][0]."
        : "All visible JSON value comparisons passed.",
      passed: !failure,
      visibility: "STUDENT_VISIBLE" as const,
      testCase: "visible/basic-matrix",
    },
    {
      id: `${prefix}-4`,
      kind: "TEST_RESULT" as const,
      title: failure ? "Hidden test mismatch" : "Hidden tests passed",
      message: failure
        ? "A hidden JSON_VALUE comparison did not match. Inputs and expected values are withheld."
        : "Hidden tests passed. Inputs and expected values are withheld.",
      passed: !failure,
      visibility: "REVIEWER_ONLY" as const,
      testCase: "hidden/edge-cases",
    },
    {
      id: `${prefix}-5`,
      kind: "STATIC_FINDING" as const,
      title: "No unnecessary globals",
      message: "No module-level mutable data was observed.",
      passed: true,
      visibility: "STUDENT_VISIBLE" as const,
    },
  ].map((evidence) => ({ ...evidence, provenance: "DEMO_FIXTURE" as const }));
}

export const demoSubmissions: Submission[] = [
  {
    id: "correct",
    assignmentId: "demo",
    assignmentTitle: demoAssignment.title,
    totalScore: 20,
    studentId: "student-01",
    filename: "correct_solution.py",
    status: "APPROVED",
    errorCategory: "NONE",
    aiSuggestedTotal: 20,
    finalTotal: 20,
    provenance: "DEMO_FIXTURE",
    dataSource: "LOCAL_FIXTURE",
    ...demoFixtureAnalysis,
    reviewHistory: [{ id: "fixture-review-correct", reviewer: "demo-instructor", status: "APPROVED", decisionReason: "Stored fixture approval.", isCurrent: true, approvedAt: "2026-07-14T00:00:00Z", createdAt: "2026-07-14T00:00:00Z", total: 20 }],
    reviewRequired: false,
    reviewReasons: [],
    rubricReady: true,
    source: correctSource,
    scores: scores([3, 5, 4, 6, 2], 0.96, "correct", false).map((score) => ({
      ...score,
      humanScore: score.aiSuggestedScore,
    })),
    evidence: makeEvidence("correct"),
    testResults: [],
    uncertainties: [],
    feedback: [
      {
        concept: "Row-major slicing",
        showsEvidenceOf: "The implementation shows evidence of mapping contiguous slices into rows.",
        likelyMisconception: "No likely misconception is supported by the available evidence.",
        nextStep: "Consider documenting behavior for invalid dimensions.",
      },
    ],
  },
  {
    id: "idea-wrong",
    assignmentId: "demo",
    assignmentTitle: demoAssignment.title,
    totalScore: 20,
    studentId: "student-02",
    filename: "idea_correct_output_wrong.py",
    status: "REVIEW_REQUIRED",
    errorCategory: "LOGIC",
    aiSuggestedTotal: 12,
    provenance: "DEMO_FIXTURE",
    dataSource: "LOCAL_FIXTURE",
    ...demoFixtureAnalysis,
    reviewRequired: true,
    reviewReasons: ["HUMAN_REVIEW"],
    rubricReady: true,
    source: wrongSource,
    scores: scores([3, 5, 4, 0, 0], 0.78, "wrong"),
    evidence: makeEvidence("wrong", true),
    testResults: [],
    uncertainties: ["The static hardcoding heuristic is not sufficient by itself to support a deduction."],
    feedback: [
      {
        concept: "Index mapping",
        showsEvidenceOf: "The nested loops show evidence of a row/column construction approach.",
        likelyMisconception: "The +1 offset suggests a likely zero-based indexing misconception.",
        nextStep: "Trace the first element and verify that its source index is zero.",
      },
    ],
  },
  {
    id: "runtime",
    assignmentId: "demo",
    assignmentTitle: demoAssignment.title,
    totalScore: 20,
    studentId: "student-03",
    filename: "runtime_error.py",
    status: "REVIEW_REQUIRED",
    errorCategory: "RUNTIME",
    aiSuggestedTotal: 7,
    provenance: "DEMO_FIXTURE",
    dataSource: "LOCAL_FIXTURE",
    ...demoFixtureAnalysis,
    reviewRequired: true,
    reviewReasons: ["HUMAN_REVIEW"],
    rubricReady: true,
    source: wrongSource.replace("+ 1", "+ len(data)"),
    scores: scores([3, 4, 0, 0, 0], 0.86, "runtime"),
    evidence: [
      ...makeEvidence("runtime", true),
      {
        id: "runtime-error",
        kind: "EXECUTION_ERROR",
        title: "IndexError",
        message: "IndexError was raised at the list access on line 7.",
        passed: false,
        visibility: "STUDENT_VISIBLE",
        provenance: "DEMO_FIXTURE",
        lineStart: 7,
        lineEnd: 7,
      },
    ],
    testResults: [],
    uncertainties: [],
    feedback: [],
  },
  {
    id: "hardcoded",
    assignmentId: "demo",
    assignmentTitle: demoAssignment.title,
    totalScore: 20,
    studentId: "student-04",
    filename: "hardcoded_solution.py",
    status: "STALE",
    errorCategory: "LOGIC",
    aiSuggestedTotal: 8,
    provenance: "DEMO_FIXTURE",
    dataSource: "LOCAL_FIXTURE",
    ...demoFixtureAnalysis,
    reviewHistory: [{ id: "fixture-review-stale", reviewer: "demo-instructor", status: "APPROVED", decisionReason: "Preserved historical fixture review; inputs changed later.", isCurrent: false, approvedAt: "2026-07-13T00:00:00Z", createdAt: "2026-07-13T00:00:00Z", total: 8 }],
    analysisStatus: "STALE",
    staleReason: "A hidden test changed after this stored fixture.",
    reviewRequired: true,
    reviewReasons: ["STALE_INPUT"],
    rubricReady: true,
    source: `def make_matrix(data, rows, cols):\n    if data == [1, 2, 3, 4, 5, 6]:\n        return [[1, 2, 3], [4, 5, 6]]\n    return []`,
    scores: scores([3, 1, 1, 2, 1], 0.62, "hardcoded"),
    evidence: makeEvidence("hardcoded", true),
    testResults: [],
    uncertainties: ["Analysis is stale because a hidden test changed after this run."],
    feedback: [],
  },
  {
    id: "missing",
    assignmentId: "demo",
    assignmentTitle: demoAssignment.title,
    totalScore: 20,
    studentId: "student-05",
    filename: "missing_function.py",
    status: "REVIEW_REQUIRED",
    errorCategory: "MIXED",
    aiSuggestedTotal: 1,
    provenance: "DEMO_FIXTURE",
    dataSource: "LOCAL_FIXTURE",
    ...demoFixtureAnalysis,
    reviewRequired: true,
    reviewReasons: ["HUMAN_REVIEW"],
    rubricReady: true,
    source: `def transform_values(data):\n    return list(data)`,
    scores: scores([0, 0, 0, 0, 1], 0.94, "missing"),
    evidence: [
      {
        id: "missing-1",
        kind: "AST_FINDING",
        title: "Entry function missing",
        message: "No make_matrix function definition was found.",
        passed: false,
        visibility: "STUDENT_VISIBLE",
        provenance: "DEMO_FIXTURE",
      },
      ...makeEvidence("missing", true).slice(1),
    ],
    testResults: [],
    uncertainties: [],
    feedback: [],
  },
];

export function findDemoSubmission(id: string) {
  return demoSubmissions.find((submission) => submission.id === id);
}
