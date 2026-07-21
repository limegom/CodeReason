export type Provenance = "LIVE" | "STORED_LIVE" | "DEMO_FIXTURE" | "UNAVAILABLE";
export type DataSource = "API" | "LOCAL_FIXTURE";

export type SubmissionStatus =
  | "PENDING"
  | "RUNNING"
  | "ANALYZED"
  | "REVIEW_REQUIRED"
  | "APPROVED"
  | "FAILED"
  | "STALE";

export type AnalysisStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "STALE";
export type EvidenceVisibility = "INTERNAL" | "REVIEWER_ONLY" | "STUDENT_VISIBLE";
export type EvidenceKind =
  | "TEST_RESULT"
  | "EXECUTION_ERROR"
  | "AST_FINDING"
  | "STATIC_FINDING"
  | "SOURCE_CODE_LOCATION";

export interface ExternalDataManifest {
  status?: string;
  fieldsSent: string[];
  redacted?: boolean;
  redactionCount?: number;
  redactionCategories: string[];
  redactionIsBestEffort?: boolean;
  hiddenTestValuesWithheld?: boolean;
  modelToolsEnabled?: boolean;
}

export interface Evidence {
  id: string;
  kind: EvidenceKind;
  title: string;
  message: string;
  passed: boolean | null;
  visibility: EvidenceVisibility;
  provenance: Provenance;
  lineStart?: number;
  lineEnd?: number;
  testCase?: string;
}

export interface TestResultDetail {
  id: string;
  testCaseId: string;
  testName?: string;
  isHidden: boolean;
  inputPayload?: unknown;
  expectedOutput?: unknown;
  status: string;
  comparisonMode: string;
  actualOutput?: string;
  stdout?: string;
  stderr?: string;
  exitCode?: number;
  durationMs?: number;
  errorCategory?: string;
  visibility: EvidenceVisibility;
}

export interface HumanReviewHistory {
  id: string;
  reviewer: string;
  status: string;
  decisionReason?: string;
  isCurrent: boolean;
  approvedAt?: string;
  createdAt: string;
  total: number;
}

export interface RubricScore {
  rubricId: string;
  title: string;
  maxScore: number;
  aiSuggestedScore: number | null;
  humanScore?: number;
  modelReportedConfidence: number | null;
  reason: string;
  evidenceIds: string[];
  manualReviewRequired: boolean;
}

export interface Submission {
  id: string;
  assignmentId: string;
  assignmentTitle: string;
  totalScore: number;
  studentId: string;
  filename: string;
  status: SubmissionStatus;
  analysisStatus?: AnalysisStatus;
  analysisId?: string;
  staleReason?: string;
  reviewRequired: boolean;
  reviewReasons: string[];
  rubricReady: boolean;
  errorCategory: string;
  executionStatus?: string;
  aiSuggestedTotal: number | null;
  finalTotal?: number;
  provenance: Provenance;
  executionProvenance?: Provenance;
  analysisProvenance?: Provenance;
  dataSource: DataSource;
  source: string;
  scores: RubricScore[];
  evidence: Evidence[];
  testResults: TestResultDetail[];
  reviewHistory: HumanReviewHistory[];
  uncertainties: string[];
  feedback: Array<{
    concept: string;
    showsEvidenceOf: string;
    likelyMisconception: string;
    nextStep: string;
  }>;
  externalDataManifest?: ExternalDataManifest;
  modelName?: string;
  provider?: string;
}

export interface AssignmentSummary {
  id: string;
  title: string;
  description: string;
  totalScore: number;
  executionMode: "FUNCTION" | "STDIN_STDOUT";
  entryFunction?: string;
  comparisonMode:
    | "EXACT"
    | "IGNORE_FINAL_NEWLINE"
    | "TRIM_TRAILING_WHITESPACE"
    | "TOKEN_BASED"
    | "JSON_VALUE";
  progress: number;
  submissions: number;
  pendingReview: number;
  approved: number;
  consistencyIssues: number;
  rubricReady: boolean;
  provenance: Provenance;
  dataSource: DataSource;
}

export interface ConsistencyIssue {
  id: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  status: "OPEN" | "DISMISSED" | "RESOLVED";
  potentialIssue: boolean;
  description: string;
  submissionId: string;
  comparedSubmissionId?: string;
  fingerprint: string;
  testStatusVector: string[];
  errorCategory?: string;
  astFeatureSummary: Record<string, unknown>;
  exceptionType?: string;
  signatureStatus?: string;
}
