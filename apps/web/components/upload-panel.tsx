"use client";

import { FileCode2, ShieldAlert, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import { ApiMutationError, executeSubmission, uploadSubmissions } from "@/lib/client-api";
import type { DataSource, Provenance } from "@/lib/types";
import { PrivacyDisclosure } from "./privacy-disclosure";

export function UploadPanel({ assignmentId, dataSource, provenance }: { assignmentId: string; dataSource: DataSource; provenance: Provenance }) {
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [studentPrefix, setStudentPrefix] = useState("student");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function accept(list: FileList | null) {
    if (!list) return;
    const selected = Array.from(list);
    const rejected = selected.filter((file) => !file.name.toLowerCase().endsWith(".py") || file.size > 256 * 1024);
    setFiles((current) => [...current, ...selected.filter((file) => !rejected.includes(file))]);
    setError(rejected.length ? `${rejected.length} file(s) rejected. Only .py files up to 256 KiB are accepted; ZIP files are excluded.` : null);
  }

  async function upload() {
    if (!files.length || submitting) return;
    if (provenance === "DEMO_FIXTURE") {
      setError("Demo Fixture assignments are read-only. Create a live assignment before uploading student code.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const ids = await uploadSubmissions(assignmentId, files, studentPrefix);
      const executions = await Promise.allSettled(ids.map((id) => executeSubmission(id)));
      const failed = executions.filter((result) => result.status === "rejected").length;
      setFiles([]);
      if (input.current) input.current.value = "";
      setNotice(failed
        ? `${ids.length} submissions were created, but ${failed} execution job(s) could not be queued. The submissions remain available for retry.`
        : `${ids.length} immutable submissions were created and queued for deterministic execution.`);
    } catch (caught) {
      const message = caught instanceof ApiMutationError ? `${caught.message} (${caught.code})` : "The upload could not be completed.";
      setError(dataSource === "LOCAL_FIXTURE" ? `${message} Local Demo Fixture data is read-only.` : message);
    } finally {
      setSubmitting(false);
    }
  }

  return <div className="stack">
    {error ? <div className="notice" role="alert"><ShieldAlert size={18} />{error}</div> : null}
    {notice ? <div className="notice" role="status">{notice}</div> : null}
    <div className="card card-pad" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); accept(event.dataTransfer.files); }} style={{ display: "grid", minHeight: 280, placeItems: "center", borderStyle: "dashed" }}>
      <div style={{ maxWidth: 530, textAlign: "center" }}><span className="brand-mark" style={{ width: 48, height: 48, margin: "0 auto 18px" }}><UploadCloud size={22} /></span><h2 className="section-title">Drop Python submissions here</h2><p className="subtle" style={{ lineHeight: 1.6 }}>Single or batch upload. Filenames are sanitized, source is preserved immutably, and execution requires the Docker worker.</p><button className="button button-secondary" type="button" onClick={() => input.current?.click()}>Choose files</button><input ref={input} type="file" accept=".py,text/x-python" multiple hidden onChange={(event) => accept(event.target.files)} /></div>
    </div>
    {files.length ? <section className="card card-pad stack">
      <div className="row-between"><h2 className="section-title">Ready to upload</h2><span className="badge badge-blue">{files.length} files</span></div>
      <div className="field"><label htmlFor="student-prefix">Student reference prefix</label><input className="input" id="student-prefix" value={studentPrefix} maxLength={80} onChange={(event) => setStudentPrefix(event.target.value)} placeholder="student" /></div>
      {files.map((file) => <div className="row-between" key={`${file.name}-${file.lastModified}`}><div className="row"><FileCode2 size={16} /><div><strong style={{ fontSize: 13 }}>{file.name}</strong><div className="subtle" style={{ fontSize: 11 }}>{Math.ceil(file.size / 1024)} KiB</div></div></div><button className="icon-button" type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((items) => items.filter((item) => item !== file))}><X size={15} /></button></div>)}
      <button className="button button-primary" type="button" onClick={upload} disabled={submitting}>{submitting ? "Uploading…" : "Upload and enqueue"}</button>
    </section> : null}
    <div className="notice"><ShieldAlert size={18} />Student code is untrusted. It is never executed by the web process. Docker-unavailable environments report execution as unavailable instead of returning a mock success.</div>
    <PrivacyDisclosure />
  </div>;
}
