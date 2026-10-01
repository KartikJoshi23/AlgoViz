/**
 * Fixed-capacity typed-array ring buffers.
 *
 * `push()` is O(1) with no allocation; `head` increases monotonically so React
 * subscribers can detect new data without diffing arrays, and Three.js can
 * read the underlying buffer directly in `useFrame`.
 */
export class RingF64 {
  readonly capacity: number;
  readonly buf: Float64Array;
  head = 0; // total pushes
  private size = 0;

  constructor(capacity: number) {
    this.capacity = capacity;
    this.buf = new Float64Array(capacity);
    this.buf.fill(Number.NaN);
  }

  push(v: number): void {
    this.buf[this.head % this.capacity] = v;
    this.head += 1;
    if (this.size < this.capacity) this.size += 1;
  }

  get length(): number {
    return this.size;
  }

  /** i-th oldest value (0 = oldest). */
  at(i: number): number {
    if (i < 0 || i >= this.size) return Number.NaN;
    const start = this.head - this.size;
    return this.buf[(start + i) % this.capacity] as number;
  }

  get latest(): number {
    return this.size === 0 ? Number.NaN : (this.buf[(this.head - 1) % this.capacity] as number);
  }

  /** Oldest → newest as a fresh array (allocates; use for chart hydration, not per frame). */
  toArray(): number[] {
    const out = new Array<number>(this.size);
    for (let i = 0; i < this.size; i += 1) out[i] = this.at(i);
    return out;
  }

  /** Copy oldest → newest into `target` (no allocation when reused). Returns count. */
  copyTo(target: Float32Array | Float64Array): number {
    const n = Math.min(this.size, target.length);
    const offset = this.size - n;
    for (let i = 0; i < n; i += 1) target[i] = this.at(offset + i);
    return n;
  }

  clear(): void {
    this.buf.fill(Number.NaN);
    this.head = 0;
    this.size = 0;
  }
}

/** A set of parallel rings addressed by column name (the bar table). */
export class RingTable<K extends string> {
  readonly cols: Record<K, RingF64>;
  readonly keys: readonly K[];
  head = 0;

  constructor(keys: readonly K[], capacity: number) {
    this.keys = keys;
    this.cols = Object.fromEntries(keys.map((k) => [k, new RingF64(capacity)])) as Record<K, RingF64>;
  }

  pushRow(row: Partial<Record<K, number | null | undefined>>): void {
    for (const k of this.keys) {
      const v = row[k];
      this.cols[k].push(v == null ? Number.NaN : v);
    }
    this.head += 1;
  }

  get length(): number {
    return this.cols[this.keys[0] as K].length;
  }

  latest(k: K): number {
    return this.cols[k].latest;
  }

  clear(): void {
    for (const k of this.keys) this.cols[k].clear();
    this.head = 0;
  }
}
