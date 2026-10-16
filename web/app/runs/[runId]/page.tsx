import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Banner } from "@/components/Banner";
import { DiffBlock } from "@/components/DiffBlock";
import { HardwareStrip } from "@/components/HardwareStrip";
import { latency, ratio, tokens, usd } from "@/lib/format";
import { measuredResults, publishedRun, publishedRunIds } from "@/lib/results";

export function generateStaticParams() {
  return publishedRunIds().map((runId) => ({ runId }));
}

export const dynamicParams = false;

export function generateMetadata({ params }: { params: { runId: string } }): Metadata {
  return { title: `evalkit run ${params.runId.slice(0, 8)}` };
}

export default function RunPage({ params }: { params: { runId: string } }) {
  const published = publishedRun(params.runId);
  if (!published) notFound();
  const { run, source, judgeRan } = published;

  return (
    <>
      <Banner tone={source === "measured" ? "measured" : "sample"} disclaimer={published.disclaimer} />
      <main className="mx-auto grid max-w-6xl gap-8 px-5 py-10">
        <div>
          <Link href={source === "measured" ? "/" : "/sample"} className="text-sm text-muted hover:text-paper">
            Back to {source === "measured" ? "leaderboard" : "sample"}
          </Link>
          <h1 className="mt-3 text-2xl font-medium tracking-tight">{run.taskName}</h1>
          <p className="mt-2 font-mono text-xs text-muted">{run.id}</p>
        </div>
        {source === "measured" ? <HardwareStrip hardware={measuredResults.hardware} /> : null}
        {run.targets.map((target) => (
          <section key={target.targetId} id={target.targetId} className="scroll-mt-6">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <h2 className="font-mono text-lg">{source === "measured" ? target.model : target.targetId}</h2>
              <p className="text-sm text-muted">
                {target.quantization ? `${target.quantization} · ` : ""}
                n {target.summary.n} · exact {ratio(target.summary.exactMatch)} · schema{" "}
                {ratio(target.summary.jsonSchema)}
              </p>
            </div>
            <div className="mt-4 grid gap-3">
              {target.samples.map((sample) => (
                <details key={sample.sampleId} className="rounded-lg border border-line bg-panel px-4 py-3">
                  <summary className="cursor-pointer font-mono text-sm">
                    {sample.sampleId}
                    <span className="ml-3 text-xs text-muted">
                      exact {flag(sample.metrics.exactMatch)} · schema {flag(sample.metrics.jsonSchema)} · judge{" "}
                      {judgeRan ? flag(sample.metrics.judge) : "not run"}
                    </span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed">{sample.input}</p>
                  <p className="mt-2 font-mono text-xs text-muted">
                    {sample.cached ? "cached" : latency(sample.latencyMs)} ·{" "}
                    {tokens(sample.promptTokens, sample.completionTokens)} · {usd(sample.costUsd)}
                    {sample.attempts > 1 ? ` · ${sample.attempts} attempts` : ""}
                  </p>
                  <div className="mt-4">
                    <DiffBlock sample={sample} />
                  </div>
                </details>
              ))}
            </div>
          </section>
        ))}
      </main>
    </>
  );
}

function flag(value: number | null): string {
  if (value == null) return "—";
  return value.toFixed(3);
}
