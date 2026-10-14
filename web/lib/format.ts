import type { RateBlock } from "./types";

export function ratio(block: RateBlock): string {
  if (!block.scored) return "—";
  return `${block.passes}/${block.scored}`;
}

export function judgeMean(value: number | null, scored: number): string {
  if (value == null || scored === 0) return "—";
  return value.toFixed(3);
}

export function latency(value: number | null): string {
  if (value == null) return "—";
  return `${value.toFixed(1)} ms`;
}

export function usd(value: number | null): string {
  if (value == null) return "—";
  if (value === 0) return "$0";
  if (Math.abs(value) < 0.001) return `$${value.toExponential(2)}`;
  return `$${value.toFixed(6)}`;
}

export function tokens(prompt: number | null, completion: number | null): string {
  if (prompt == null && completion == null) return "—";
  return `${prompt ?? "—"} in / ${completion ?? "—"} out`;
}

export function stamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toISOString().replace("T", " ").replace(".000Z", " UTC").replace("Z", " UTC");
}
