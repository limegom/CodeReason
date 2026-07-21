import { Braces } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { ThemeToggle } from "./theme-toggle";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="topbar">
        <div className="shell row-between">
          <Link className="row" href="/" aria-label="CodeReason home">
            <span className="brand-mark"><Braces size={18} strokeWidth={2.4} /></span>
            <span style={{ fontWeight: 780, letterSpacing: "-0.03em" }}>CodeReason</span>
          </Link>
          <nav className="row" aria-label="Primary navigation">
            <Link className="nav-link" href="/assignments">Assignments</Link>
            <Link className="nav-link" href="/assignments/new">New assignment</Link>
          </nav>
          <div className="row">
            <span className="badge badge-blue">Reviewer workspace</span>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main>{children}</main>
    </>
  );
}
