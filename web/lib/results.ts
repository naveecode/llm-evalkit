import measuredRaw from "../data/measured-results.json";
import sampleRaw from "../data/sample-results.json";

import type { EvalRun, MeasuredFile, SampleFile } from "./types";

export const sampleResults = sampleRaw as unknown as SampleFile;
export const measuredResults = measuredRaw as unknown as MeasuredFile;

if (sampleResults.kind !== "sample") {
  throw new Error('web/data/sample-results.json must have kind "sample".');
}

if (measuredResults.kind !== "measured") {
  throw new Error('web/data/measured-results.json must have kind "measured".');
}

export type PublishedRun = {
  source: "sample" | "measured";
  disclaimer: string;
  run: EvalRun;
  judgeRan: boolean;
};

export function publishedRun(runId: string): PublishedRun | null {
  if (runId === sampleResults.run.id) {
    return {
      source: "sample",
      disclaimer: sampleResults.disclaimer,
      run: sampleResults.run,
      judgeRan: true,
    };
  }
  const run = measuredResults.runs.find((item) => item.id === runId);
  if (!run) return null;
  return {
    source: "measured",
    disclaimer: measuredResults.disclaimer,
    run,
    judgeRan: measuredResults.judgeRan,
  };
}

export function publishedRunIds(): string[] {
  return [sampleResults.run.id, ...measuredResults.runs.map((run) => run.id)];
}
