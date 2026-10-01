/** A resolved prediction: the class probabilities and what happened (0 down, 1 flat, 2 up). */
export interface Outcome {
  p_up: number;
  p_down: number;
  realised: number;
}

export type ClassFilter = "all" | "down" | "flat" | "up";

export interface ReliabilityBin {
  lo: number;
  hi: number;
  n: number;
  predicted: number; // mean predicted probability in the bin
  observed: number; // share of those predictions whose class happened
}

const CLASS_CODE = { down: 0, flat: 1, up: 2 } as const;

const probs = (o: Outcome): [number, number, number] => [o.p_down, Math.max(0, 1 - o.p_up - o.p_down), o.p_up];

/**
 * Class-wise reliability of resolved predictions: every (class probability,
 * did that class happen) pair — all three classes pooled, or one class — in
 * equal-width probability bins. ECE is the count-weighted gap between
 * predicted and observed; Brier is the mean squared error of the
 * probabilities (summed over classes when pooled).
 */
export function reliability(outcomes: Outcome[], cls: ClassFilter, nBins = 10) {
  const sums = Array.from({ length: nBins }, () => ({ n: 0, p: 0, hit: 0 }));
  const classes = cls === "all" ? [0, 1, 2] : [CLASS_CODE[cls]];
  let pairs = 0;
  let brier = 0;
  for (const o of outcomes) {
    const p = probs(o);
    for (const k of classes) {
      const pk = p[k]!;
      const hit = o.realised === k ? 1 : 0;
      const b = sums[Math.min(nBins - 1, Math.floor(pk * nBins))]!;
      b.n += 1;
      b.p += pk;
      b.hit += hit;
      brier += (pk - hit) ** 2;
      pairs += 1;
    }
  }
  return { ...finish(sums, pairs), brier: outcomes.length ? brier / outcomes.length : null, outcomes: outcomes.length };
}

type Sums = { n: number; p: number; hit: number }[];

function finish(sums: Sums, pairs: number) {
  const nBins = sums.length;
  const bins: ReliabilityBin[] = sums.map((b, i) => ({
    lo: i / nBins,
    hi: (i + 1) / nBins,
    n: b.n,
    predicted: b.n ? b.p / b.n : Number.NaN,
    observed: b.n ? b.hit / b.n : Number.NaN,
  }));
  const ece = pairs ? bins.reduce((acc, b) => acc + (b.n ? (b.n / pairs) * Math.abs(b.observed - b.predicted) : 0), 0) : null;
  return { bins, ece, pairs };
}

/** One class's bins in a held-out curve (backend `ml/evaluation.py`: 10 bins by forecast, empty ones omitted). */
export type CurveBin = { n: number; forecast: number; observed: number };

/**
 * The same read-out from the walk-forward folds' held-out curve: each bin
 * carries its count, mean forecast and hit rate, so pooling classes is a
 * count-weighted merge. The Brier score isn't recoverable from bins.
 */
export function reliabilityFromCurve(curve: Record<"down" | "flat" | "up", CurveBin[]> | null | undefined, cls: ClassFilter, nBins = 10) {
  const sums: Sums = Array.from({ length: nBins }, () => ({ n: 0, p: 0, hit: 0 }));
  const names = cls === "all" ? (["down", "flat", "up"] as const) : [cls];
  let pairs = 0;
  for (const name of names) {
    for (const b of curve?.[name] ?? []) {
      const s = sums[Math.min(nBins - 1, Math.floor(b.forecast * nBins))]!;
      s.n += b.n;
      s.p += b.forecast * b.n;
      s.hit += b.observed * b.n;
      pairs += b.n;
    }
  }
  return { ...finish(sums, pairs), brier: null, outcomes: Math.round(pairs / names.length) };
}
