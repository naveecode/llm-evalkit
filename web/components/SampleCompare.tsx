"use client";

import { useState } from "react";

import { DiffBlock } from "@/components/DiffBlock";
import { latency, tokens, usd } from "@/lib/format";
import type { TargetResult } from "@/lib/types";

export function SampleCompare({ targets, note }: { targets: TargetResult[]; note: string }) {
  const sampleIds = targets[0]?.samples.map((sample) => sample.sampleId) ?? [];
  const [sampleId, setSampleId] = useState(sampleIds[0] ?? "");
  const selected = targets.map((target) => ({
    target,
    sample: target.samples.find((sample) => sample.sampleId === sampleId),
  }));
  const ticket = selected.find((item) => item.sample)?.sample?.input ?? "";

  return (
    <section className="grid gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-medium">Per-sample diff</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">{note}</p>
        </div>
        <label className="grid gap-1 text-xs uppercase tracking-wide text-muted">
          Ticket
          <select
            value={sampleId}
            onChange={(event) => setSampleId(event.target.value)}
            className="min-w-40 border border-line bg-panel px-3 py-2 font-mono text-sm normal-case tracking-normal text-paper focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
          >
            {sampleIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="rounded border border-line bg-panel px-4 py-3 text-sm leading-relaxed">{ticket}</p>
      <div className="grid gap-4 lg:grid-cols-3">
        {selected.map(({ target, sample }) => (
          <article key={target.targetId} className="rounded-lg border border-line bg-panel p-4">
            <h3 className="font-mono text-sm">{target.targetId}</h3>
            {sample ? (
              <>
                <dl className="mt-3 grid grid-cols-3 gap-2 text-xs text-muted">
                  <div>
                    <dt>Exact</dt>
                    <dd className="mt-1 font-mono text-paper">{scoreLabel(sample.metrics.exactMatch)}</dd>
                  </div>
                  <div>
                    <dt>Schema</dt>
                    <dd className="mt-1 font-mono text-paper">{scoreLabel(sample.metrics.jsonSchema)}</dd>
                  </div>
                  <div>
                    <dt>Judge</dt>
                    <dd className="mt-1 font-mono text-paper">{scoreLabel(sample.metrics.judge)}</dd>
                  </div>
                  <div>
                    <dt>Latency</dt>
                    <dd className="mt-1 font-mono text-paper">
                      {sample.cached ? "cached" : latency(sample.latencyMs)}
                    </dd>
                  </div>
                  <div>
                    <dt>Tokens</dt>
                    <dd className="mt-1 font-mono text-paper">{tokens(sample.promptTokens, sample.completionTokens)}</dd>
                  </div>
                  <div>
                    <dt>Cost</dt>
                    <dd className="mt-1 font-mono text-paper">{usd(sample.costUsd)}</dd>
                  </div>
                </dl>
                <div className="mt-4">
                  <DiffBlock sample={sample} />
                </div>
              </>
            ) : (
              <p className="mt-3 text-sm text-muted">This target has no row for the selected ticket.</p>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function scoreLabel(value: number | null): string {
  if (value == null) return "—";
  return value.toFixed(3);
}
