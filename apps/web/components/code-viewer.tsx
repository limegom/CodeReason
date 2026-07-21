import type { Evidence } from "@/lib/types";

export function CodeViewer({ source, evidence }: { source: string; evidence: Evidence[] }) {
  const highlighted = new Set<number>();
  for (const item of evidence) {
    if (!item.lineStart) continue;
    for (let line = item.lineStart; line <= (item.lineEnd ?? item.lineStart); line += 1) highlighted.add(line);
  }
  return (
    <div className="code-viewer" aria-label="Read-only student source code">
      {source.split("\n").map((line, index) => {
        const number = index + 1;
        return (
          <div className={`code-line ${highlighted.has(number) ? "code-line-highlight" : ""}`} key={number}>
            <span className="line-number">{number}</span>
            <span className="code-content">{line || " "}</span>
          </div>
        );
      })}
    </div>
  );
}

