import {
  adaptAssignmentOverview,
  adaptConsistencyIssue,
  adaptSubmissionBundle,
  ContractError,
  parseAssignmentOverviews,
  parseConsistencyIssues,
  parseSubmissionBundle,
  parseSubmissionBundles,
} from "./api-contract";
import { demoAssignment, demoSubmissions, findDemoSubmission } from "./demo-data";
import type { AssignmentSummary, ConsistencyIssue, DataSource, Provenance, Submission } from "./types";

export interface DataEnvelope<T> {
  ok: true;
  data: T;
  provenance: Provenance;
  source: DataSource;
  notice?: string;
}

export interface DataFailure {
  ok: false;
  error: string;
  code: string;
  status?: number;
}

export type DataResult<T> = DataEnvelope<T> | DataFailure;

class NetworkApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkApiError";
  }
}

class HttpApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "HttpApiError";
  }
}

function internalApiBase(): string {
  return (
    process.env.API_INTERNAL_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000/api"
  ).replace(/\/$/, "");
}

async function errorFromResponse(response: Response): Promise<HttpApiError> {
  try {
    const body = (await response.json()) as {
      error?: { code?: unknown; message?: unknown };
    };
    const code = typeof body.error?.code === "string" ? body.error.code : "HTTP_ERROR";
    const message =
      typeof body.error?.message === "string"
        ? body.error.message
        : `API request failed with status ${response.status}`;
    return new HttpApiError(response.status, code, message);
  } catch {
    return new HttpApiError(response.status, "HTTP_ERROR", `API request failed with status ${response.status}`);
  }
}

async function requestJson<T>(path: string, parse: (value: unknown) => T): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${internalApiBase()}${path}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(3_000),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "API connection failed";
    throw new NetworkApiError(message);
  }
  if (!response.ok) throw await errorFromResponse(response);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ContractError("response body is not valid JSON");
  }
  return parse(body);
}

function failure(error: unknown): DataFailure {
  if (error instanceof HttpApiError) {
    return { ok: false, error: error.message, code: error.code, status: error.status };
  }
  if (error instanceof ContractError) {
    return { ok: false, error: error.message, code: "CONTRACT_MISMATCH" };
  }
  return {
    ok: false,
    error: error instanceof Error ? error.message : "The API request could not be completed.",
    code: error instanceof NetworkApiError ? "NETWORK_UNAVAILABLE" : "UNKNOWN_ERROR",
  };
}

function combinedProvenance(values: Provenance[]): Provenance {
  if (!values.length) return "UNAVAILABLE";
  if (values.every((value) => value === values[0])) return values[0];
  if (values.includes("LIVE")) return "LIVE";
  if (values.includes("STORED_LIVE")) return "STORED_LIVE";
  return values[0];
}

export async function getAssignments(): Promise<DataResult<AssignmentSummary[]>> {
  try {
    const wire = await requestJson("/reviewer/assignments", parseAssignmentOverviews);
    const data = wire.map((item) => adaptAssignmentOverview(item));
    return {
      ok: true,
      data,
      provenance: combinedProvenance(data.map((item) => item.provenance)),
      source: "API",
    };
  } catch (error) {
    return failure(error);
  }
}

export async function getAssignmentOverview(id: string): Promise<DataResult<AssignmentSummary>> {
  try {
    const wire = await requestJson("/reviewer/assignments", parseAssignmentOverviews);
    const found = wire.find(
      (item) => item.id === id || (id === "demo" && ["matrix-transformation-v1", "codereason-demo"].includes(item.demo_key ?? "")),
    );
    if (!found) return { ok: false, error: "Assignment was not found.", code: "NOT_FOUND", status: 404 };
    const data = adaptAssignmentOverview(found);
    return { ok: true, data, provenance: data.provenance, source: "API" };
  } catch (error) {
    if ((error instanceof NetworkApiError || (error instanceof HttpApiError && error.status === 404)) && id === "demo") {
      return {
        ok: true,
        data: demoAssignment,
        provenance: "DEMO_FIXTURE",
        source: "LOCAL_FIXTURE",
        notice: "API network unavailable - showing a clearly labeled local Demo Fixture.",
      };
    }
    return failure(error);
  }
}

export async function getSubmissions(assignmentId: string): Promise<DataResult<Submission[]>> {
  try {
    const wire = await requestJson(
      `/reviewer/assignments/${encodeURIComponent(assignmentId)}/submissions`,
      parseSubmissionBundles,
    );
    const data = wire.map((item) => adaptSubmissionBundle(item));
    return {
      ok: true,
      data,
      provenance: combinedProvenance(data.map((item) => item.provenance)),
      source: "API",
    };
  } catch (error) {
    if ((error instanceof NetworkApiError || (error instanceof HttpApiError && error.status === 404)) && assignmentId === "demo") {
      return {
        ok: true,
        data: demoSubmissions,
        provenance: "DEMO_FIXTURE",
        source: "LOCAL_FIXTURE",
        notice: "API network unavailable - showing stored local Demo Fixture records, not live execution or GPT output.",
      };
    }
    return failure(error);
  }
}

export async function getSubmission(id: string): Promise<DataResult<Submission>> {
  try {
    const wire = await requestJson(
      `/reviewer/submissions/${encodeURIComponent(id)}`,
      parseSubmissionBundle,
    );
    const data = adaptSubmissionBundle(wire);
    return { ok: true, data, provenance: data.provenance, source: "API" };
  } catch (error) {
    const fixture = findDemoSubmission(id);
    if ((error instanceof NetworkApiError || (error instanceof HttpApiError && error.status === 404)) && fixture) {
      return {
        ok: true,
        data: fixture,
        provenance: "DEMO_FIXTURE",
        source: "LOCAL_FIXTURE",
        notice: "API network unavailable - showing the matching local Demo Fixture, not a live record.",
      };
    }
    return failure(error);
  }
}

const demoConsistency: ConsistencyIssue[] = [
  {
    id: "demo-consistency-high",
    severity: "HIGH",
    status: "OPEN",
    potentialIssue: true,
    description: "Potential issue: similar deterministic failure fingerprints received materially different score treatment.",
    submissionId: "idea-wrong",
    comparedSubmissionId: "hardcoded",
    fingerprint: "demo-fixture-fingerprint-high",
    testStatusVector: ["PASSED", "FAILED", "FAILED"],
    errorCategory: "WRONG_ANSWER",
    astFeatureSummary: { loop: true },
    signatureStatus: "MATCH",
  },
];

export async function getConsistencyIssues(
  assignmentId: string,
  assignmentProvenance: Provenance = "LIVE",
): Promise<DataResult<ConsistencyIssue[]>> {
  try {
    const wire = await requestJson(
      `/assignments/${encodeURIComponent(assignmentId)}/consistency-issues`,
      parseConsistencyIssues,
    );
    return {
      ok: true,
      data: wire.map(adaptConsistencyIssue),
      provenance: assignmentProvenance,
      source: "API",
    };
  } catch (error) {
    if (error instanceof NetworkApiError && assignmentId === "demo") {
      return {
        ok: true,
        data: demoConsistency,
        provenance: "DEMO_FIXTURE",
        source: "LOCAL_FIXTURE",
        notice: "API network unavailable - showing labeled Demo Fixture consistency records.",
      };
    }
    return failure(error);
  }
}
