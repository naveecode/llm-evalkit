import { isRecord, lineDiff, pretty } from "@/lib/diff";
import type { SampleRow } from "@/lib/types";

export function DiffBlock({ sample }: { sample: SampleRow }) {
  const expectedText = pretty(sample.expected);
  const predictedText =
    sample.parsed != null ? pretty(sample.parsed) : (sample.predictionText ?? sample.error ?? "");
  const lines = lineDiff(expectedText, predictedText);
  const expected = isRecord(sample.expected) ? sample.expected : null;
  const parsed = isRecord(sample.parsed) ? sample.parsed : null;
  const keys =
    expected == null
      ? []
      : Array.from(new Set([...Object.keys(expected), ...(parsed ? Object.keys(parsed) : [])]));

  return (
    <div className="grid gap-4">
      {sample.error ? (
        <p className="rounded border border-bad/40 bg-[#3a2220] px-3 py-2 text-sm text-bad">{sample.error}</p>
      ) : null}
      {keys.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="py-2 pr-3 font-medium">Field</th>
                <th className="py-2 pr-3 font-medium">Expected</th>
                <th className="py-2 pr-3 font-medium">Predicted</th>
                <th className="py-2 font-medium">Match</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => {
                const left = expected?.[key];
                const right = parsed ? parsed[key] : undefined;
                const present = parsed != null && Object.prototype.hasOwnProperty.call(parsed, key);
                const matched = present && JSON.stringify(left) === JSON.stringify(right);
                return (
                  <tr key={key} className="border-t border-line align-top">
                    <td className="py-2 pr-3 font-mono text-xs text-muted">{key}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{formatCell(left)}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{present ? formatCell(right) : "—"}</td>
                    <td className={`py-2 text-xs ${matched ? "text-good" : "text-bad"}`}>
                      {parsed == null ? "no JSON" : matched ? "match" : present ? "differs" : "missing"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {sample.metrics.schemaErrors.length > 0 ? (
        <ul className="list-disc pl-5 text-xs text-bad">
          {sample.metrics.schemaErrors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      ) : null}
      {sample.metrics.judgeError ? <p className="text-xs text-bad">{sample.metrics.judgeError}</p> : null}
      {sample.metrics.judgeReason ? (
        <p className="text-xs text-muted">Judge: {sample.metrics.judgeReason}</p>
      ) : null}
      <div className="overflow-x-auto rounded border border-line bg-ink">
        <pre className="p-3 font-mono text-xs leading-5">
          {lines.map((line, index) => (
            <div key={`${line.kind}-${index}`} className={diffClass(line.kind)}>
              {line.kind === "add" ? "+ " : line.kind === "del" ? "- " : "  "}
              {line.text || " "}
            </div>
          ))}
        </pre>
      </div>
    </div>
  );
}

function diffClass(kind: "same" | "add" | "del"): string {
  if (kind === "add") return "bg-[#1d3a2c] text-good";
  if (kind === "del") return "bg-[#3a2220] text-bad";
  return "text-muted";
}

function formatCell(value: unknown): string {
  if (value == null) return "null";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
