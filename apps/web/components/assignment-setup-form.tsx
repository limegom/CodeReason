"use client";

import { CheckCircle2, Plus, Sparkles, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { FormEvent, useRef, useState } from "react";
import {
  ApiMutationError,
  approveRubricCriterion,
  createAssignment,
  createRubricCriterion,
  createTestCase,
  deleteRubricCriterion,
  getRubricParseJob,
  listRubricCriteria,
  requestRubricParse,
  updateRubricCriterion,
  updateAssignment,
  type AssignmentCreatePayload,
} from "@/lib/client-api";
import { PrivacyDisclosure } from "./privacy-disclosure";

type RubricDraft = {
  id: string;
  serverId?: string;
  title: string;
  max: number;
  status: "DRAFT" | "HUMAN_APPROVED";
  origin: "HUMAN" | "AI_STRUCTURED";
};

const initialRubrics: RubricDraft[] = [
  { id: "structure", title: "Function & parameters", max: 3, status: "DRAFT", origin: "HUMAN" },
  { id: "approach", title: "2D list construction", max: 5, status: "DRAFT", origin: "HUMAN" },
  { id: "dimensions", title: "Correct dimensions", max: 4, status: "DRAFT", origin: "HUMAN" },
  { id: "values", title: "Value order & output", max: 6, status: "DRAFT", origin: "HUMAN" },
  { id: "quality", title: "Code quality", max: 2, status: "DRAFT", origin: "HUMAN" },
];

function safeKey(value: string, index: number): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9_.-]+/g, "-").replace(/^-|-$/g, "") || `criterion-${index + 1}`;
}

function parseJsonObject(value: FormDataEntryValue | null, label: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(String(value ?? "{}"));
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error();
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(`${label} must be a JSON object.`);
  }
}

function parseJsonValue(value: FormDataEntryValue | null, label: string): unknown {
  try {
    return JSON.parse(String(value ?? "null"));
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
}

export function AssignmentSetupForm() {
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();
  const [rubrics, setRubrics] = useState<RubricDraft[]>(initialRubrics);
  const [natural, setNatural] = useState("Award partial credit when the code shows a correct nested-list and loop structure even if output values are wrong. Missing make_matrix receives zero for the function criterion.");
  const [mode, setMode] = useState<"FUNCTION" | "STDIN_STDOUT">("FUNCTION");
  const [assignmentId, setAssignmentId] = useState<string | null>(null);
  const [parseJobId, setParseJobId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function assignmentPayload(): AssignmentCreatePayload {
    if (!formRef.current) throw new Error("Assignment form is unavailable.");
    const data = new FormData(formRef.current);
    const executionMode = String(data.get("execution_mode")) as AssignmentCreatePayload["execution_mode"];
    return {
      title: String(data.get("title") ?? "").trim(),
      description: String(data.get("description") ?? "").trim(),
      total_score: Number(data.get("total_score")),
      time_limit_ms: Number(data.get("time_limit_ms")),
      python_version: "3.12",
      execution_mode: executionMode,
      entry_function: executionMode === "FUNCTION" ? String(data.get("entry_function") ?? "").trim() : null,
      arguments_schema: executionMode === "FUNCTION" ? parseJsonObject(data.get("arguments_schema"), "Arguments schema") : {},
      comparison_mode: String(data.get("comparison_mode")) as AssignmentCreatePayload["comparison_mode"],
    };
  }

  async function ensureAssignment(): Promise<string> {
    if (assignmentId) return assignmentId;
    const id = await createAssignment(assignmentPayload());
    setAssignmentId(id);
    return id;
  }

  async function saveAssignmentContract(): Promise<string> {
    if (!assignmentId) return ensureAssignment();
    await updateAssignment(assignmentId, assignmentPayload());
    return assignmentId;
  }

  async function structureRubric() {
    if (!natural.trim() || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const id = await ensureAssignment();
      const jobId = parseJobId ?? await requestRubricParse(id, natural.trim());
      setParseJobId(jobId);
      for (let attempt = 0; attempt < 15; attempt += 1) {
        const job = await getRubricParseJob(id, jobId);
        if (job.status === "COMPLETED") {
          const records = (await listRubricCriteria(id)).filter((criterion) => criterion.active);
          setRubrics(records.sort((left, right) => left.sortOrder - right.sortOrder).map((criterion) => ({
            id: criterion.id,
            serverId: criterion.id,
            title: criterion.title,
            max: criterion.maxScore,
            status: criterion.approvalStatus === "HUMAN_APPROVED" ? "HUMAN_APPROVED" : "DRAFT",
            origin: criterion.origin,
          })));
          setNotice(`Rubric parse job ${jobId} completed. Server-created AI_STRUCTURED criteria are loaded as DRAFT and still require explicit human approval.`);
          return;
        }
        if (job.status === "FAILED" || job.status === "STALE") throw new Error(job.errorMessage ?? `Rubric parse job ended with ${job.status}.`);
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      setNotice(`Rubric parse job ${jobId} is still processing. Use Refresh rubric job to load its DRAFT criteria when the worker finishes.`);
    } catch (caught) {
      setError(caught instanceof ApiMutationError ? `${caught.message} (${caught.code})` : caught instanceof Error ? caught.message : "Rubric parsing could not be started.");
    } finally {
      setBusy(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const totalScore = assignmentPayload().total_score;
      const rubricTotal = rubrics.reduce((sum, rubric) => sum + rubric.max, 0);
      if (Math.abs(rubricTotal - totalScore) > 0.000_001) {
        throw new Error(`Active rubric maxima total ${rubricTotal}, but the assignment total is ${totalScore}. Make them equal before saving.`);
      }
      const id = await saveAssignmentContract();
      const persisted: RubricDraft[] = [];
      for (const [index, rubric] of rubrics.entries()) {
        if (!rubric.title.trim() || rubric.max <= 0) throw new Error("Every rubric criterion needs a title and a positive maximum score.");
        const payload = {
          title: rubric.title.trim(),
          description: rubric.title.trim(),
          max_score: rubric.max,
          rules: { grading_policy: natural.trim() },
          sort_order: index,
          active: true,
        };
        const serverId = rubric.serverId ?? await createRubricCriterion(id, {
          criterion_key: safeKey(rubric.id, index),
          ...payload,
          origin: rubric.origin,
        });
        if (!rubric.serverId) {
          setRubrics((items) => items.map((item) => item.id === rubric.id ? { ...item, serverId } : item));
        }
        if (rubric.serverId) await updateRubricCriterion(id, serverId, payload);
        if (rubric.status === "HUMAN_APPROVED") await approveRubricCriterion(id, serverId, "Instructor");
        persisted.push({ ...rubric, serverId });
      }
      setRubrics(persisted);

      if (!formRef.current) throw new Error("Assignment form is unavailable.");
      const data = new FormData(formRef.current);
      const comparisonMode = assignmentPayload().comparison_mode;
      await createTestCase(id, {
        name: String(data.get("test_name") ?? "Visible example").trim(),
        input_payload: mode === "FUNCTION" ? parseJsonValue(data.get("test_input"), "Test input") : String(data.get("test_input") ?? ""),
        expected_output: mode === "FUNCTION" || comparisonMode === "JSON_VALUE" ? parseJsonValue(data.get("test_expected"), "Expected output") : String(data.get("test_expected") ?? ""),
        comparison_mode: null,
        is_hidden: data.get("test_hidden") === "on",
        active: true,
        sort_order: 0,
      });

      setNotice("Assignment, rubric drafts/approvals, and the deterministic test case were saved to the live API.");
      router.push(`/assignments/${id}`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof ApiMutationError ? `${caught.message} (${caught.code})` : caught instanceof Error ? caught.message : "Assignment setup could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function removeRubric(rubric: RubricDraft) {
    if (busy) return;
    if (!rubric.serverId) {
      setRubrics((items) => items.filter((item) => item.id !== rubric.id));
      return;
    }
    if (!assignmentId) {
      setError("The persisted assignment ID is unavailable; the server rubric was not removed.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteRubricCriterion(assignmentId, rubric.serverId);
      setRubrics((items) => items.filter((item) => item.id !== rubric.id));
      setNotice("The persisted rubric criterion was removed from the active assignment rubric.");
    } catch (caught) {
      setError(caught instanceof ApiMutationError ? `${caught.message} (${caught.code})` : "The rubric criterion could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form ref={formRef} className="stack" onSubmit={save}>
      {error ? <div className="notice" role="alert">{error}</div> : null}
      {notice ? <div className="notice" role="status">{notice}</div> : null}
      <section className="card card-pad stack">
        <div><p className="section-label">Step 1</p><h2 className="section-title">Assignment contract</h2></div>
        <div className="grid-2">
          <div className="field"><label htmlFor="title">Title</label><input className="input" id="title" name="title" defaultValue="Matrix Transformation Assignment" required /></div>
          <div className="field"><label htmlFor="total">Total score</label><input className="input" id="total" name="total_score" type="number" min="0.5" step="0.5" defaultValue={20} required /></div>
        </div>
        <div className="field"><label htmlFor="description">Problem description</label><textarea className="textarea" id="description" name="description" defaultValue="Implement make_matrix(data, rows, cols) and return a row-major two-dimensional list." /></div>
        <div className="grid-2">
          <div className="field"><label htmlFor="mode">Execution mode</label><select className="select" id="mode" name="execution_mode" value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option>FUNCTION</option><option>STDIN_STDOUT</option></select></div>
          <div className="field"><label htmlFor="function">Entry function</label><input className="input" id="function" name="entry_function" defaultValue="make_matrix" disabled={mode === "STDIN_STDOUT"} required={mode === "FUNCTION"} /></div>
          <div className="field"><label htmlFor="comparison">Default comparison</label><select className="select" id="comparison" name="comparison_mode" defaultValue="JSON_VALUE"><option>EXACT</option><option>IGNORE_FINAL_NEWLINE</option><option>TRIM_TRAILING_WHITESPACE</option><option>TOKEN_BASED</option><option>JSON_VALUE</option></select></div>
          <div className="field"><label htmlFor="time-limit">Time limit (ms)</label><input className="input" id="time-limit" name="time_limit_ms" type="number" min={50} max={5000} defaultValue={2000} /></div>
        </div>
        {mode === "FUNCTION" ? <div className="field"><label htmlFor="schema">Arguments JSON Schema</label><textarea className="textarea" id="schema" name="arguments_schema" style={{ fontFamily: "monospace" }} defaultValue={'{"type":"array","prefixItems":[{"type":"array"},{"type":"integer"},{"type":"integer"}],"minItems":3,"maxItems":3}'} /></div> : null}
      </section>

      <section className="card card-pad stack">
        <div className="row-between wrap"><div><p className="section-label">Step 2</p><h2 className="section-title">Rubric builder</h2></div><span className="badge badge-blue"><CheckCircle2 size={12} />Human approval gate</span></div>
        <div className="field"><label htmlFor="natural">Natural-language grading policy</label><textarea className="textarea" id="natural" value={natural} onChange={(event) => setNatural(event.target.value)} /></div>
        <button className="button button-secondary" type="button" onClick={structureRubric} disabled={busy} style={{ justifySelf: "start" }}><Sparkles size={16} />{parseJobId ? "Refresh rubric job" : "Structure with GPT-5.6"}</button>
        <div className="stack" style={{ gap: 10 }}>
          {rubrics.map((rubric, index) => <div className="card row-between wrap" key={rubric.id} style={{ padding: 13 }}>
            <div className="row"><span className="badge badge-gray">{index + 1}</span><span className="badge badge-gray">{rubric.origin.replaceAll("_", " ")}</span><input className="input" aria-label={`Rubric ${index + 1} title`} value={rubric.title} onChange={(event) => setRubrics((items) => items.map((item) => item.id === rubric.id ? { ...item, title: event.target.value, status: "DRAFT" } : item))} style={{ minWidth: 230 }} /></div>
            <div className="row"><input className="input" aria-label={`${rubric.title} points`} type="number" min={0.5} step={0.5} value={rubric.max} onChange={(event) => setRubrics((items) => items.map((item) => item.id === rubric.id ? { ...item, max: Number(event.target.value), status: "DRAFT" } : item))} style={{ width: 84 }} /><span className={`badge ${rubric.status === "HUMAN_APPROVED" ? "badge-green" : "badge-amber"}`}>{rubric.status.replaceAll("_", " ")}</span>{rubric.status === "DRAFT" ? <button className="button button-primary" type="button" onClick={() => setRubrics((items) => items.map((item) => item.id === rubric.id ? { ...item, status: "HUMAN_APPROVED" } : item))}>Mark approved</button> : null}<button className="icon-button" type="button" aria-label={`Delete ${rubric.title}`} onClick={() => removeRubric(rubric)} disabled={busy}><Trash2 size={15} /></button></div>
          </div>)}
        </div>
        <button className="button button-ghost" type="button" onClick={() => setRubrics((items) => [...items, { id: crypto.randomUUID(), title: "New criterion", max: 1, status: "DRAFT", origin: "HUMAN" }])} style={{ justifySelf: "start" }}><Plus size={16} />Add criterion</button>
      </section>

      <section className="card card-pad stack">
        <div><p className="section-label">Step 3</p><h2 className="section-title">Deterministic test</h2></div>
        <div className="field"><label htmlFor="test-name">Test name</label><input className="input" id="test-name" name="test_name" defaultValue="Visible basic matrix" required /></div>
        <div className="grid-2"><div className="field"><label htmlFor="test-input">{mode === "FUNCTION" ? "Arguments (JSON)" : "Standard input"}</label><textarea className="textarea" id="test-input" name="test_input" key={`input-${mode}`} defaultValue={mode === "FUNCTION" ? '[[1,2,3,4,5,6],2,3]' : "1 2 3 4 5 6\n2 3\n"} /></div><div className="field"><label htmlFor="test-expected">Expected output</label><textarea className="textarea" id="test-expected" name="test_expected" key={`expected-${mode}`} defaultValue={mode === "FUNCTION" ? '[[1,2,3],[4,5,6]]' : "[[1,2,3],[4,5,6]]\n"} /></div></div>
        <label className="row"><input type="checkbox" name="test_hidden" />Hidden test (inputs and expected values are withheld from students and CSV)</label>
      </section>

      <PrivacyDisclosure preflightFields={["natural_language_rubric_policy", "assignment_score_bounds"]} />
      <div className="row-between wrap"><p className="subtle" style={{ fontSize: 13 }}>Only HUMAN_APPROVED rubric revisions can be selected by an analysis run.</p><button className="button button-primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save assignment"}</button></div>
    </form>
  );
}
