export type RateBlock = {
  passes: number;
  scored: number;
  rate: number | null;
};

export type SampleMetrics = {
  exactMatch: number | null;
  jsonSchema: number | null;
  judge: number | null;
  judgeReason: string | null;
  judgeError: string | null;
  schemaErrors: string[];
  mismatchedFields: string[];
};

export type SampleRow = {
  sampleId: string;
  input: string;
  expected: unknown;
  predictionText: string | null;
  parsed: unknown;
  promptTokens: number | null;
  completionTokens: number | null;
  latencyMs: number | null;
  costUsd: number | null;
  cached: boolean;
  attempts: number;
  error: string | null;
  metrics: SampleMetrics;
};

export type Summary = {
  n: number;
  errors: number;
  exactMatch: RateBlock;
  jsonSchema: RateBlock;
  judgeMean: number | null;
  judgeScored: number;
  latencyMsMean: number | null;
  latencyMsP50: number | null;
  liveLatencyCount: number;
  costUsdTotal: number | null;
  costPer1kUsd: number | null;
  costComplete: boolean;
  targetId: string;
  model: string;
  provider: string;
};

export type TargetResult = {
  targetId: string;
  provider: string;
  model: string;
  baseUrl: string;
  summary: Summary;
  samples: SampleRow[];
  quantization?: string;
  parameterSize?: string;
  family?: string;
  digest?: string;
  contextLength?: number;
};

export type EvalRun = {
  id: string;
  taskName: string;
  taskVersion: string;
  description: string;
  createdAt: string;
  label: string | null;
  metrics: string[];
  pricing: Record<
    string,
    {
      inputPerMillion: number;
      outputPerMillion: number;
      source: string | null;
      asOf: string | null;
    }
  >;
  targets: TargetResult[];
};

export type Hardware = {
  cpuModel: string;
  cpuFamily: number;
  cpuModelId: number;
  cpuStepping: number;
  logicalCpus: number;
  memoryTotalBytes: number;
  memoryAvailableBytes: number;
  platform: string;
  kernel: string;
  backend: string;
  backendVersion: string;
  runner: string;
  ggmlLibraries: string[];
  acceleratorLibraries: string[];
  collectedAt: string;
};

export type MeasuredModel = {
  model: string;
  format: string | null;
  family: string | null;
  parameterSize: string;
  parameterCount: number | null;
  quantization: string;
  digest: string;
  sizeBytes: number;
  contextLength: number;
  ollamaDetails: {
    quantization_level?: string;
    parameter_size?: string;
    family?: string;
    format?: string;
  };
};

export type MeasuredFile = {
  kind: string;
  disclaimer: string;
  generator: string;
  judgeRan: boolean;
  procedure: string;
  hardware: Hardware;
  models: MeasuredModel[];
  runs: EvalRun[];
};

export type SampleFile = {
  kind: string;
  disclaimer: string;
  generator?: string;
  fixtures?: Record<string, string>;
  pricingNote?: string;
  run: EvalRun;
};
