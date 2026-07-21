import { afterEach, describe, expect, it, vi } from "vitest";
import {
  approveReview,
  approveRubricCriterion,
  createAssignment,
  createRubricCriterion,
  createTestCase,
  executeSubmission,
  uploadSubmissions,
} from "@/lib/client-api";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => vi.unstubAllGlobals());

describe("live API mutations", () => {
  it("posts human approval to the submission review endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "review-1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    await approveReview("submission 1", {
      reviewer: "Instructor",
      ai_analysis_id: "analysis-1",
      status: "APPROVED",
      decision_reason: "Verified linked evidence.",
      scores: [{ rubric_criterion_id: "criterion-1", awarded_score: 4, reason: null }],
    });
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringMatching(/\/submissions\/submission%201\/review$/),
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"status":"APPROVED"') }),
    );
  });

  it("uploads one immutable submission per file and queues execution", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse([{ id: "submission-1" }, { id: "submission-2" }], 201))
      .mockResolvedValueOnce(jsonResponse({ id: "run-1" }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const ids = await uploadSubmissions("assignment-1", [
      new File(["print(1)"], "one.py", { type: "text/x-python" }),
      new File(["print(2)"], "two.py", { type: "text/x-python" }),
    ], "student");
    await executeSubmission(ids[0]);
    expect(ids).toEqual(["submission-1", "submission-2"]);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/assignments\/assignment-1\/submissions\/upload$/);
    expect(fetchMock.mock.calls[1]).toEqual([
      expect.stringMatching(/\/submissions\/submission-1\/execute$/),
      expect.objectContaining({ method: "POST", body: '{"analyze_after_execution":true}' }),
    ]);
  });

  it("uses the create, rubric approval, and test-case endpoints for assignment setup", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ id: "assignment-1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "criterion-1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "criterion-1" }))
      .mockResolvedValueOnce(jsonResponse({ id: "test-1" }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const assignmentId = await createAssignment({
      title: "Assignment",
      description: "Description",
      total_score: 5,
      time_limit_ms: 2000,
      python_version: "3.12",
      execution_mode: "FUNCTION",
      entry_function: "solve",
      arguments_schema: { type: "array" },
      comparison_mode: "JSON_VALUE",
    });
    const criterionId = await createRubricCriterion(assignmentId, {
      criterion_key: "correctness",
      title: "Correctness",
      description: "Observable correctness",
      max_score: 5,
      rules: {},
      sort_order: 0,
      active: true,
      origin: "HUMAN",
    });
    await approveRubricCriterion(assignmentId, criterionId, "Instructor");
    await createTestCase(assignmentId, { name: "Visible", input_payload: [], expected_output: 1, comparison_mode: null, is_hidden: false, active: true, sort_order: 0 });
    expect(fetchMock.mock.calls.map((call) => String(call[0]))).toEqual([
      expect.stringMatching(/\/assignments$/),
      expect.stringMatching(/\/assignments\/assignment-1\/rubrics$/),
      expect.stringMatching(/\/assignments\/assignment-1\/rubrics\/criterion-1\/approve$/),
      expect.stringMatching(/\/assignments\/assignment-1\/test-cases$/),
    ]);
  });
});
