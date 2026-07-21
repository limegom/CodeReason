"use client";

import { ArrowUpDown, Download, Search, Upload } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { publicApiUrl } from "@/lib/client-api";
import type { Submission } from "@/lib/types";
import { ProvenanceBadge, StatusBadge } from "./status-badge";

function suggestedTotal(submission: Submission): number {
  return submission.aiSuggestedTotal ?? Number.NEGATIVE_INFINITY;
}

function lowestConfidence(submission: Submission): number | undefined {
  const values = submission.scores
    .map((score) => score.modelReportedConfidence)
    .filter((value): value is number => value !== null);
  return values.length ? Math.min(...values) : undefined;
}

export function GradingTable({ submissions, assignmentId, totalScore }: { submissions: Submission[]; assignmentId: string; totalScore: number }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [descending, setDescending] = useState(true);
  const filtered = useMemo(
    () =>
      [...submissions]
        .filter((item) => `${item.studentId} ${item.filename}`.toLowerCase().includes(query.toLowerCase()))
        .filter((item) => status === "ALL" || item.status === status)
        .sort((a, b) => descending ? suggestedTotal(b) - suggestedTotal(a) : suggestedTotal(a) - suggestedTotal(b)),
    [descending, query, status, submissions],
  );

  return <section className="card card-strong">
    <div className="row-between wrap" style={{ padding: 16 }}>
      <div className="row wrap">
        <label className="row" style={{ position: "relative" }}><Search size={15} style={{ position: "absolute", left: 11, color: "var(--muted)" }} /><span className="sr-only">Search submissions</span><input className="input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Student or filename" style={{ paddingLeft: 34, width: 220 }} /></label>
        <select className="select" aria-label="Filter by review status" value={status} onChange={(event) => setStatus(event.target.value)} style={{ width: 185 }}><option>ALL</option><option>REVIEW_REQUIRED</option><option>APPROVED</option><option>STALE</option></select>
        <button className="button button-secondary" type="button" onClick={() => setDescending((value) => !value)}><ArrowUpDown size={14} />AI score</button>
      </div>
      <div className="row"><Link className="button button-secondary" href={`/assignments/${assignmentId}/upload`}><Upload size={15} />Upload</Link><a className="button button-primary" href={publicApiUrl(`/assignments/${encodeURIComponent(assignmentId)}/export.csv`)}><Download size={15} />Export CSV</a></div>
    </div>
    <div className="table-wrap"><table className="table"><thead><tr><th>Submission</th><th>Error</th><th>AI suggestion</th><th>Final total</th><th>Model confidence</th><th>Status</th><th>Provenance</th></tr></thead><tbody>{filtered.map((submission) => {
      const confidence = lowestConfidence(submission);
      const confidencePercent = confidence === undefined ? undefined : Math.round(confidence * 100);
      return <tr key={submission.id}>
        <td><Link href={`/submissions/${submission.id}`}><strong>{submission.studentId}</strong><div className="subtle" style={{ fontSize: 12, marginTop: 3 }}>{submission.filename}</div></Link></td>
        <td><span className={`badge ${submission.errorCategory === "NONE" ? "badge-green" : submission.errorCategory.includes("RUNTIME") || submission.errorCategory.includes("SYNTAX") ? "badge-red" : "badge-amber"}`}>{submission.errorCategory}</span></td>
        <td>{submission.aiSuggestedTotal === null ? <span className="subtle">Unavailable</span> : <><strong>{submission.aiSuggestedTotal}</strong><span className="subtle"> / {totalScore}</span></>}</td>
        <td>{submission.finalTotal === undefined ? <span className="subtle">Pending human approval</span> : <strong style={{ color: "var(--blue)" }}>{submission.finalTotal} / {totalScore}</strong>}</td>
        <td>{confidencePercent === undefined ? <span className="subtle">Unavailable</span> : <div className="row"><div className="progress-track" style={{ width: 70 }}><div className="progress-value" style={{ width: `${confidencePercent}%`, background: confidencePercent < 70 ? "var(--amber)" : "var(--green)" }} /></div><span>{confidencePercent}%</span></div>}</td>
        <td><StatusBadge status={submission.status} /></td><td><ProvenanceBadge provenance={submission.provenance} /></td>
      </tr>;
    })}{filtered.length === 0 ? <tr><td colSpan={7}><span className="subtle">No submissions match the current filters.</span></td></tr> : null}</tbody></table></div>
    <div style={{ padding: 14, borderTop: "1px solid var(--border)" }} className="subtle">{filtered.length} of {submissions.length} submissions · model-reported confidence is an uncalibrated review-priority signal.</div>
  </section>;
}
