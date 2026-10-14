import raw from "../data/sample-results.json";

import type { SampleFile } from "./types";

export const sampleResults = raw as unknown as SampleFile;

if (sampleResults.kind !== "sample") {
  throw new Error('web/data/sample-results.json must have kind "sample". This dashboard does not publish benchmark scores.');
}
