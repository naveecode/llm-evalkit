import Link from "next/link";

import { judgeMean, latency, ratio, usd } from "@/lib/format";
import type { TargetResult } from "@/lib/types";

export function Leaderboard({
  runId,
  targets,
  variant,
  judgeRan,
}: {
  runId: string;
  targets: TargetResult[];
  variant: "sample" | "measured";
  judgeRan: boolean;
}) {
  const ranked = [...targets].sort((left, right) => {
    const leftRate = left.summary.exactMatch.rate ?? -1;
    const rightRate = right.summary.exactMatch.rate ?? -1;
    if (rightRate !== leftRate) return rightRate - leftRate;
    return (right.summary.jsonSchema.rate ?? -1) - (left.summary.jsonSchema.rate ?? -1);
  });
  const measured = variant === "measured";

  return (
    <div className="overflow-x-auto rounded-lg border border-line bg-panel">
      <table className="min-w-full text-left text-sm">
        <caption className="sr-only">
          {measured ? "Measured leaderboard" : "Sample leaderboard for fixture endpoints"}
        </caption>
        <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
          <tr>
            <th className="px-4 py-3 font-medium">{measured ? "Model" : "Target"}</th>
            {measured ? <th className="px-4 py-3 font-medium">Quant</th> : null}
            {measured ? <th className="px-4 py-3 font-medium">n</th> : null}
            <th className="px-4 py-3 font-medium">Exact</th>
            <th className="px-4 py-3 font-medium">Schema</th>
            <th className="px-4 py-3 font-medium">Judge</th>
            <th className="px-4 py-3 font-medium">
              p50 latency
              <span className="mt-1 block font-normal normal-case tracking-normal text-muted">
                {measured ? "wall clock" : "localhost"}
              </span>
            </th>
            <th className="px-4 py-3 font-medium">
              $ / 1k
              <span className="mt-1 block font-normal normal-case tracking-normal text-muted">
                {measured ? "no provider bill" : "illustrative"}
              </span>
            </th>
            <th className="px-4 py-3 font-medium">Errors</th>
          </tr>
        </thead>
        <tbody>
          {ranked.map((target) => {
            const summary = target.summary;
            return (
              <tr key={target.targetId} className="border-b border-line last:border-0">
                <td className="px-4 py-4">
                  <Link
                    href={`/runs/${runId}#${target.targetId}`}
                    className="font-mono text-paper underline decoration-line underline-offset-4 hover:decoration-accent"
                  >
                    {measured ? target.model : target.targetId}
                  </Link>
                  <div className="mt-1 text-xs text-muted">
                    {measured
                      ? [target.parameterSize, target.family, target.contextLength ? `ctx ${target.contextLength}` : null]
                          .filter(Boolean)
                          .join(" · ")
                      : target.provider}
                  </div>
                </td>
                {measured ? <td className="px-4 py-4 font-mono">{target.quantization}</td> : null}
                {measured ? <td className="px-4 py-4 font-mono">{summary.n}</td> : null}
                <td className="px-4 py-4 font-mono">
                  <Score value={ratio(summary.exactMatch)} rate={summary.exactMatch.rate} />
                </td>
                <td className="px-4 py-4 font-mono">
                  <Score value={ratio(summary.jsonSchema)} rate={summary.jsonSchema.rate} />
                </td>
                <td className="px-4 py-4 font-mono">
                  {judgeRan ? (
                    <>
                      {judgeMean(summary.judgeMean, summary.judgeScored)}
                      <div className="mt-1 text-xs text-muted">{summary.judgeScored} scored</div>
                    </>
                  ) : (
                    "not run"
                  )}
                </td>
                <td className="px-4 py-4 font-mono">
                  {latency(summary.latencyMsP50)}
                  <div className="mt-1 text-xs text-muted">{summary.liveLatencyCount} live</div>
                </td>
                <td className="px-4 py-4 font-mono">{summary.costComplete ? usd(summary.costPer1kUsd) : "—"}</td>
                <td className="px-4 py-4 font-mono">{summary.errors}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Score({ value, rate }: { value: string; rate: number | null }) {
  return (
    <div>
      <div>{value}</div>
      {rate != null ? (
        <div className="mt-2 h-1 w-16 bg-line">
          <div className="h-1 bg-accent" style={{ width: `${Math.max(0, Math.min(1, rate)) * 100}%` }} />
        </div>
      ) : null}
    </div>
  );
}
