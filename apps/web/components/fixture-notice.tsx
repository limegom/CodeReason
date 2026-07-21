import { CircleAlert } from "lucide-react";

export function FixtureNotice({ children }: { children: string }) {
  return <div className="notice"><CircleAlert size={18} style={{ flex: "0 0 auto", marginTop: 1 }} /><span>{children}</span></div>;
}

