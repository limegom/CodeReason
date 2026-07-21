import { describe, expect, it } from "vitest";
import { demoSubmissions } from "@/lib/demo-data";

describe("demo grading semantics", () => {
  it("never exposes a final total before human approval", () => {
    for (const submission of demoSubmissions) {
      if (submission.status !== "APPROVED") expect(submission.finalTotal).toBeUndefined();
    }
  });

  it("keeps AI deductions linked to primary evidence", () => {
    for (const submission of demoSubmissions) {
      const evidenceIds = new Set(submission.evidence.map((evidence) => evidence.id));
      for (const score of submission.scores) {
        if (score.aiSuggestedScore < score.maxScore) {
          expect(score.evidenceIds.length).toBeGreaterThan(0);
          expect(score.evidenceIds.every((id) => evidenceIds.has(id))).toBe(true);
        }
      }
    }
  });

  it("labels every fixture as non-live provenance", () => {
    expect(demoSubmissions.every((submission) => submission.provenance === "DEMO_FIXTURE")).toBe(true);
  });
});

