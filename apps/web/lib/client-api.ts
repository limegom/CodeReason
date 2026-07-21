export class ApiMutationError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiMutationError";
  }
}

function publicApiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api").replace(/\/$/, "");
}

export function publicApiUrl(path: string): string {
  return `${publicApiBase()}${path}`;
}

async function mutationError(response: Response): Promise<ApiMutationError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: unknown; message?: unknown };
    };
    return new ApiMutationError(
      typeof body.error?.code === "string" ? body.error.code : "HTTP_ERROR",
      typeof body.error?.message === "string"
        ? body.error.message
        : `Request failed with status ${response.status}`,
      response.status,
    );
  } catch {
    return new ApiMutationError("HTTP_ERROR", `Request failed with status ${response.status}`, response.status);
  }
}

async function postJson(path: string, body: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(publicApiUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiMutationError(
      "NETWORK_UNAVAILABLE",
      error instanceof Error ? error.message : "The API is unavailable.",
    );
  }
  if (!response.ok) throw await mutationError(response);
  return response.json();
}

async function patchJson(path: string, body: unknown): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(publicApiUrl(path), {
      method: "PATCH",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiMutationError(
      "NETWORK_UNAVAILABLE",
      error instanceof Error ? error.message : "The API is unavailable.",
    );
  }
  if (!response.ok) throw await mutationError(response);
  return response.json();
}

async function getJson(path: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(publicApiUrl(path), { headers: { Accept: "application/json" }, cache: "no-store" });
  } catch (error) {
    throw new ApiMutationError(
      "NETWORK_UNAVAILABLE",
      error instanceof Error ? error.message : "The API is unavailable.",
    );
  }
  if (!response.ok) throw await mutationError(response);
  return response.json();
}

async function deleteRequest(path: string): Promise<void> {
  let response: Response;
  try {
    response = await fetch(publicApiUrl(path), { method: "DELETE", headers: { Accept: "application/json" } });
  } catch (error) {
    throw new ApiMutationError(
      "NETWORK_UNAVAILABLE",
      error instanceof Error ? error.message : "The API is unavailable.",
    );
  }
  if (!response.ok) throw await mutationError(response);
}

function idFromResponse(value: unknown, label: string): string {
  if (typeof value !== "object" || value === null || typeof (value as { id?: unknown }).id !== "string") {
    throw new ApiMutationError("CONTRACT_MISMATCH", `${label} succeeded but its response did not contain an ID.`);
  }
  return (value as { id: string }).id;
}

export interface AssignmentCreatePayload {
  title: string;
  description: string;
  total_score: number;
  time_limit_ms: number;
  python_version: string;
  execution_mode: "FUNCTION" | "STDIN_STDOUT";
  entry_function: string | null;
  arguments_schema: Record<string, unknown>;
  comparison_mode: "EXACT" | "IGNORE_FINAL_NEWLINE" | "TRIM_TRAILING_WHITESPACE" | "TOKEN_BASED" | "JSON_VALUE";
}

export async function createAssignment(payload: AssignmentCreatePayload): Promise<string> {
  return idFromResponse(await postJson("/assignments", payload), "Assignment creation");
}

export async function updateAssignment(assignmentId: string, payload: AssignmentCreatePayload): Promise<void> {
  await patchJson(`/assignments/${encodeURIComponent(assignmentId)}`, payload);
}

export async function requestRubricParse(assignmentId: string, policyText: string): Promise<string> {
  return idFromResponse(
    await postJson(`/assignments/${encodeURIComponent(assignmentId)}/rubrics/parse`, { policy_text: policyText }),
    "Rubric parse",
  );
}

export interface RubricParseJob {
  id: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "STALE";
  errorMessage?: string;
}

export async function getRubricParseJob(assignmentId: string, jobId: string): Promise<RubricParseJob> {
  const value = await getJson(`/assignments/${encodeURIComponent(assignmentId)}/rubrics/parse-jobs/${encodeURIComponent(jobId)}`);
  if (typeof value !== "object" || value === null) throw new ApiMutationError("CONTRACT_MISMATCH", "Rubric parse job response is not an object.");
  const item = value as { id?: unknown; status?: unknown; error_message?: unknown };
  if (typeof item.id !== "string" || !["PENDING", "RUNNING", "COMPLETED", "FAILED", "STALE"].includes(String(item.status))) {
    throw new ApiMutationError("CONTRACT_MISMATCH", "Rubric parse job response is invalid.");
  }
  return {
    id: item.id,
    status: item.status as RubricParseJob["status"],
    errorMessage: typeof item.error_message === "string" ? item.error_message : undefined,
  };
}

export interface RubricCriterionRecord {
  id: string;
  title: string;
  description: string;
  maxScore: number;
  sortOrder: number;
  active: boolean;
  origin: "HUMAN" | "AI_STRUCTURED";
  approvalStatus: "DRAFT" | "AI_STRUCTURED" | "HUMAN_APPROVED" | "ARCHIVED";
}

export async function listRubricCriteria(assignmentId: string): Promise<RubricCriterionRecord[]> {
  const value = await getJson(`/assignments/${encodeURIComponent(assignmentId)}/rubrics`);
  if (!Array.isArray(value)) throw new ApiMutationError("CONTRACT_MISMATCH", "Rubric list response is not an array.");
  return value.map((raw) => {
    if (typeof raw !== "object" || raw === null) throw new ApiMutationError("CONTRACT_MISMATCH", "Rubric list item is invalid.");
    const item = raw as Record<string, unknown>;
    const maxScore = typeof item.max_score === "number" ? item.max_score : Number(item.max_score);
    if (typeof item.id !== "string" || typeof item.title !== "string" || typeof item.description !== "string" || !Number.isFinite(maxScore)) {
      throw new ApiMutationError("CONTRACT_MISMATCH", "Rubric list item is missing required fields.");
    }
    return {
      id: item.id,
      title: item.title,
      description: item.description,
      maxScore,
      sortOrder: typeof item.sort_order === "number" ? item.sort_order : 0,
      active: item.active === true,
      origin: item.origin === "AI_STRUCTURED" ? "AI_STRUCTURED" : "HUMAN",
      approvalStatus: String(item.approval_status) as RubricCriterionRecord["approvalStatus"],
    };
  });
}

export interface RubricCreatePayload {
  criterion_key: string;
  title: string;
  description: string;
  max_score: number;
  rules: Record<string, unknown>;
  sort_order: number;
  active: boolean;
  origin: "HUMAN" | "AI_STRUCTURED";
}

export async function createRubricCriterion(assignmentId: string, payload: RubricCreatePayload): Promise<string> {
  return idFromResponse(
    await postJson(`/assignments/${encodeURIComponent(assignmentId)}/rubrics`, payload),
    "Rubric creation",
  );
}

export async function approveRubricCriterion(assignmentId: string, criterionId: string, approvedBy: string): Promise<void> {
  await postJson(
    `/assignments/${encodeURIComponent(assignmentId)}/rubrics/${encodeURIComponent(criterionId)}/approve`,
    { approved_by: approvedBy },
  );
}

export async function updateRubricCriterion(
  assignmentId: string,
  criterionId: string,
  payload: Omit<RubricCreatePayload, "criterion_key" | "origin">,
): Promise<void> {
  await patchJson(
    `/assignments/${encodeURIComponent(assignmentId)}/rubrics/${encodeURIComponent(criterionId)}`,
    payload,
  );
}

export async function deleteRubricCriterion(assignmentId: string, criterionId: string): Promise<void> {
  await deleteRequest(`/assignments/${encodeURIComponent(assignmentId)}/rubrics/${encodeURIComponent(criterionId)}`);
}

export interface TestCaseCreatePayload {
  name: string;
  input_payload: unknown;
  expected_output: unknown;
  comparison_mode: AssignmentCreatePayload["comparison_mode"] | null;
  is_hidden: boolean;
  active: boolean;
  sort_order: number;
}

export async function createTestCase(assignmentId: string, payload: TestCaseCreatePayload): Promise<string> {
  return idFromResponse(
    await postJson(`/assignments/${encodeURIComponent(assignmentId)}/test-cases`, payload),
    "Test case creation",
  );
}

export interface ReviewPayload {
  reviewer: string;
  ai_analysis_id: string | null;
  status: "APPROVED";
  decision_reason: string | null;
  scores: Array<{
    rubric_criterion_id: string;
    awarded_score: number;
    reason: string | null;
  }>;
}

export async function approveReview(submissionId: string, payload: ReviewPayload): Promise<void> {
  await postJson(`/submissions/${encodeURIComponent(submissionId)}/review`, payload);
}

export async function executeSubmission(submissionId: string): Promise<void> {
  await postJson(`/submissions/${encodeURIComponent(submissionId)}/execute`, {
    analyze_after_execution: true,
  });
}

export async function uploadSubmissions(
  assignmentId: string,
  files: File[],
  studentReferencePrefix: string,
): Promise<string[]> {
  const form = new FormData();
  for (const file of files) form.append("files", file, file.name);
  form.append("student_reference_prefix", studentReferencePrefix.trim() || "student");
  let response: Response;
  try {
    response = await fetch(
      publicApiUrl(`/assignments/${encodeURIComponent(assignmentId)}/submissions/upload`),
      { method: "POST", headers: { Accept: "application/json" }, body: form },
    );
  } catch (error) {
    throw new ApiMutationError(
      "NETWORK_UNAVAILABLE",
      error instanceof Error ? error.message : "The API is unavailable.",
    );
  }
  if (!response.ok) throw await mutationError(response);
  const body: unknown = await response.json();
  if (!Array.isArray(body) || !body.every((item) => typeof item === "object" && item !== null && typeof (item as { id?: unknown }).id === "string")) {
    throw new ApiMutationError("CONTRACT_MISMATCH", "Upload succeeded but the response did not contain submission IDs.");
  }
  return body.map((item) => (item as { id: string }).id);
}
