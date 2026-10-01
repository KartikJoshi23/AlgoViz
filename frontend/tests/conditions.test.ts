import { describe, expect, it } from "vitest";

import { addLeaf, describe as describeCondition, isLeaf, leafFor, toFieldSpecs } from "@/components/conditions/ConditionEditor";

describe("condition language helpers", () => {
  it("describes leaves and groups like the backend", () => {
    expect(describeCondition({ f: "ofi_z", op: ">", v: 1.5 })).toBe("ofi_z > 1.5");
    expect(describeCondition({ f: "regime", op: "not_in", v: ["calm"] })).toBe("regime not in [calm]");
    expect(
      describeCondition({
        all: [
          { f: "ofi_z", op: ">", v: 1.5 },
          {
            any: [
              { f: "bars_held", op: ">=", v: 30 },
              { f: "ofi_z", op: "<", v: 0 },
            ],
          },
        ],
      }),
    ).toBe("(ofi_z > 1.5 AND (bars_held >= 30 OR ofi_z < 0))");
    expect(describeCondition(null)).toBe("—");
    expect(isLeaf({ f: "x", op: ">", v: 1 })).toBe(true);
    expect(isLeaf({ all: [] })).toBe(false);
  });

  it("appends context fields to catalog specs", () => {
    const specs = toFieldSpecs(
      [{ name: "spread_z", label: "Spread z", unit: "σ", kind: "zscore", group: "z", description: "", ops: ["gt"], values: [] }],
      [{ name: "bars_held", label: "Bars held", unit: "bars", kind: "quantity", group: "position", values: [], description: "" }],
    );
    expect(specs.map((s) => s.name)).toEqual(["spread_z", "bars_held"]);
  });

  it("adds a condition from the catalog to any tree shape", () => {
    const specs = toFieldSpecs([
      { name: "spread_z", label: "Spread z", unit: "σ", kind: "zscore", group: "z", description: "", ops: [], values: [] },
      {
        name: "regime",
        label: "Regime",
        unit: "",
        kind: "categorical",
        group: "state",
        description: "",
        ops: [],
        values: ["calm", "normal"],
      },
    ]);
    const z = leafFor(specs, "spread_z");
    expect(z).toEqual({ f: "spread_z", op: ">", v: 1.5 });
    expect(leafFor(specs, "regime")).toEqual({ f: "regime", op: "==", v: "calm" });
    expect(addLeaf(null, z)).toEqual(z);
    expect(addLeaf({ f: "ofi_z", op: ">", v: 1 }, z)).toEqual({ all: [{ f: "ofi_z", op: ">", v: 1 }, z] });
    expect(addLeaf({ any: [{ f: "ofi_z", op: ">", v: 1 }] }, z)).toEqual({ any: [{ f: "ofi_z", op: ">", v: 1 }, z] });
  });
});
