import Link from "next/link";

import { Banner } from "@/components/Banner";
import { HardwareStrip } from "@/components/HardwareStrip";
import { Leaderboard } from "@/components/Leaderboard";
import { SampleCompare } from "@/components/SampleCompare";
import { stamp } from "@/lib/format";
import { measuredResults } from "@/lib/results";

const METRICS = [
  {
    name: "Exact match",
    text: "1 when the parsed JSON equals the reference. Key order does not matter. A wrong string in any field scores 0.",
  },
  {
    name: "JSON schema",
    text: "1 when the output parses and a Pydantic model built from the task schema accepts it. Extra keys fail when additionalProperties is false.",
  },
  {
    name: "Judge",
    text: "Not called. The task files point this metric at gpt-4o-mini. This run did not use a paid API or a substitute grader, so the column says not run.",
  },
  {
    name: "Latency",
    text: "Wall time of the successful call. Models were stopped before each task, so the first row can include weight load. Cache hits are left blank; this file has none.",
  },
  {
    name: "Cost",
    text: "Reported token counts times the price stored on the run. These tags are priced at $0, source “local Ollama; no provider bill”.",
  },
];

const DIFF_NOTE =
  "Expected JSON against each model. Removed lines are the reference. Added lines are the prediction.";

export default function HomePage() {
  const { hardware, runs } = measuredResults;

  return (
    <>
      <Banner tone="measured" disclaimer={measuredResults.disclaimer} />
      <main className="mx-auto grid max-w-6xl gap-10 px-5 py-10">
        <section className="grid gap-3">
          <p className="text-xs uppercase tracking-[0.16em] text-accent">Local CPU run</p>
          <h1 className="max-w-3xl text-3xl font-medium tracking-tight sm:text-4xl">
            Three small instruct models, two tasks
          </h1>
          <p className="max-w-3xl text-base leading-relaxed text-muted">
            Ollama {hardware.backendVersion} served {measuredResults.models.map((model) => model.model).join(", ")}{" "}
            through its OpenAI-compatible API. Each table is the full task file. The fixture dashboard stays on{" "}
            <Link href="/sample" className="text-paper underline decoration-line underline-offset-4">
              the sample page
            </Link>
            .
          </p>
        </section>

        <HardwareStrip hardware={hardware} />
        <p className="text-sm leading-relaxed text-muted">{measuredResults.procedure}</p>

        {runs.map((run) => (
          <section key={run.id} className="grid gap-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="font-mono text-lg">{run.taskName}</h2>
                <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted">{run.description}</p>
              </div>
              <p className="font-mono text-xs text-muted">
                {stamp(run.createdAt)} · n={run.targets[0]?.summary.n ?? 0}
              </p>
            </div>
            <Leaderboard runId={run.id} targets={run.targets} variant="measured" judgeRan={measuredResults.judgeRan} />
            <SampleCompare targets={run.targets} note={DIFF_NOTE} />
          </section>
        ))}

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
        </section>
      </main>
    </>
  );
}
