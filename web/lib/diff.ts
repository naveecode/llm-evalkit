export type DiffLine = {
  kind: "same" | "add" | "del";
  text: string;
};

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function pretty(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return JSON.stringify(value, null, 2);
}

export function lineDiff(before: string, after: string): DiffLine[] {
  const left = before.split("\n");
  const right = after.split("\n");
  const scores: number[][] = Array.from({ length: left.length + 1 }, () =>
    Array<number>(right.length + 1).fill(0),
  );
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      scores[i][j] =
        left[i] === right[j] ? scores[i + 1][j + 1] + 1 : Math.max(scores[i + 1][j], scores[i][j + 1]);
    }
  }
  const lines: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < left.length && j < right.length) {
    if (left[i] === right[j]) {
      lines.push({ kind: "same", text: left[i] });
      i += 1;
      j += 1;
    } else if (scores[i + 1][j] >= scores[i][j + 1]) {
      lines.push({ kind: "del", text: left[i] });
      i += 1;
    } else {
      lines.push({ kind: "add", text: right[j] });
      j += 1;
    }
  }
  while (i < left.length) {
    lines.push({ kind: "del", text: left[i] });
    i += 1;
  }
  while (j < right.length) {
    lines.push({ kind: "add", text: right[j] });
    j += 1;
  }
  return lines;
}
