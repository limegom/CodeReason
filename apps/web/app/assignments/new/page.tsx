import { AssignmentSetupForm } from "@/components/assignment-setup-form";

export const metadata = { title: "New assignment" };

export default function NewAssignmentPage() {
  return <div className="shell page"><header style={{ marginBottom: 24 }}><p className="eyebrow">Assignment setup</p><h1 className="page-title">Define the execution contract first.</h1><p className="lede" style={{ fontSize: 17 }}>Rubrics created by a model remain drafts. A human must approve them before any submission can be scored.</p></header><AssignmentSetupForm /></div>;
}

