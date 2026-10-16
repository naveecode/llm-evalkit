import Link from "next/link";

import { Banner } from "@/components/Banner";
import { Leaderboard } from "@/components/Leaderboard";
import { SampleCompare } from "@/components/SampleCompare";
import { stamp } from "@/lib/format";
import { sampleResults } from "@/lib/results";

const METRICS = [
  {
    name: "Exact match",
    text: "1 when the parsed JSON equals the reference, including every field. Key order does not matter. Prose scores 0.",
  },
  {
    name: "JSON schema",
    text: "1 when the output parses and a Pydantic model built from the task schema accepts it. Extra keys fail when additionalProperties is false.",
  },
  {
    name: "Judge",
    text: "A second chat completion that must return a score from 0 to 1. In this file the judge is the fixture overlap grader, not a model.",
  },
  {
    name: "Latency",
    text: "Wall time of the successful HTTP call. Cache hits are left blank in the mean so a warm cache does not look like inference speed.",
  },
  {
    name: "Cost",
    text: "Reported token counts times a price. Unknown models stay blank. The prices in this file are illustrative rates on fixture usage.",
  },
];

export const metadata = {
  title: "evalkit sample fixtures",
  description: "Fixture output from local handlers. Not a benchmark of any real model.",
};

export default function SamplePage() {
  const { run } = sampleResults;
  const fixtures = sampleResults.fixtures ?? {};

  return (
    <>
      <Banner disclaimer={sampleResults.disclaimer} />
      <main className="mx-auto grid max-w-6xl gap-10 px-5 py-10">
        <section className="grid gap-3">
          <p className="text-xs uppercase tracking-[0.16em] text-accent">Fixture output</p>
          <h1 className="max-w-3xl text-3xl font-medium tracking-tight sm:text-4xl">
            Sample handlers, kept off the leaderboard
          </h1>
          <p className="max-w-3xl text-base leading-relaxed text-muted">
            {run.description} The table is one run of that task, written by{" "}
            <span className="font-mono text-paper">{sampleResults.generator}</span> at {stamp(run.createdAt)}. The
            measured models are on the{" "}
            <Link href="/" className="text-paper underline decoration-line underline-offset-4">
              leaderboard
            </Link>
            .
          </p>
        </section>

        <Leaderboard runId={run.id} targets={run.targets} variant="sample" judgeRan />

        <section className="grid gap-3 sm:grid-cols-2">
          {Object.entries(fixtures).map(([name, note]) => (
            <article key={name} className="rounded-lg border border-line bg-panel p-4">
              <h2 className="font-mono text-sm">{name}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">{note}</p>
            </article>
          ))}
        </section>

        <SampleCompare
          targets={run.targets}
          note="Expected JSON against each fixture. Removed lines are the reference. Added lines are the prediction."
        />

        <section>
          <h2 className="text-lg font-medium">What the columns measure</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {METRICS.map((metric) => (
              <article key={metric.name} className="border-t border-line pt-3">
                <h3 className="text-sm font-medium">{metric.name}</h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{metric.text}</p>
              </article>
            ))}
          </div>
          {sampleResults.pricingNote ? (
            <p className="mt-4 text-sm leading-relaxed text-muted">{sampleResults.pricingNote}</p>
          ) : null}
        </section>
      </main>
    </>
  );
}
