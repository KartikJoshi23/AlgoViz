import { render, screen, within } from "@testing-library/react";

import { StudyReport } from "@/components/intelligence/EdgeStudyPanel";
import type { EdgeStudy } from "@/lib/api/hooks";

type Study = NonNullable<EdgeStudy["study"]>;
type Config = Study["top"][number];

const config = (label: string, edge: number, beating: number): Config => ({
  label,
  horizon_s: 5,
  barrier_k: 1,
  floor_bps: 0.5,
  features: "all features",
  training: "served window",
  samples: 23_244,
  flat_share: 0.83,
  edge_vs_prior: edge + 0.01,
  edge_vs_trailing_prior: edge,
  edge,
  edge_sd: 0.047,
  quarters_beating: beating,
  quarters: 4,
});

const study = (overrides: Partial<Study> = {}): Study => {
  const top = Array.from({ length: 10 }, (_, i) => config(`label ${i}`, 0.015 - i * 0.004, 2));
  return {
    generated_ms: 1_791_480_000_000,
    protocol: "b0d882428954f5df",
    freeze_ms: 1_791_471_300_000,
    deciding: false,
    data: { bars: 24_018, days: 0.278, sessions: 13, first_ms: 1, last_ms: 2, samples: 23_244 },
    rule: { min_quarters_beating: 3, quarters: 4, min_days: 7, block: 600, blocks_per_quarter: 8 },
    verdict: { kind: "exploratory", reason: "exploratory: bars from before the protocol was frozen; nothing is decided" },
    best: top[0]!,
    holdout: { samples: 5806, log_loss: 0.6219, prior_log_loss: 0.6735, trailing_prior_log_loss: 0.662, edge: 0.0401 },
    configurations: 75,
    top,
    ...overrides,
  };
};

describe("edge study report", () => {
  it("states the verdict, the best edge, the holdout against the better prior, and the rule", () => {
    render(<StudyReport study={study()} />);
    expect(screen.getByText("Exploratory: bars from before the protocol was frozen; nothing is decided.")).toBeInTheDocument();
    expect(screen.getByText("Best in development").parentElement).toHaveTextContent("+0.015");
    expect(screen.getByText("2 of 4 quarters beat both priors")).toBeInTheDocument();
    // the holdout is compared with the better of the two priors (here the trailing prior)
    expect(screen.getByText("log-loss 0.622 vs 0.662")).toBeInTheDocument();
    expect(screen.getByText("Rule").parentElement).toHaveTextContent("3 of 4");
    expect(screen.getByText("from before the freeze · 13 sessions")).toBeInTheDocument();
  });

  it("lists at most eight configurations, best first, with their spread", () => {
    render(<StudyReport study={study()} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(8);
    expect(rows[0]).toHaveTextContent("label 0");
    expect(rows[0]).toHaveTextContent("± 0.047");
    expect(rows[0]).toHaveTextContent("2 of 4");
  });

  it("says when there is no holdout to compare", () => {
    render(
      <StudyReport study={study({ holdout: null, verdict: { kind: "no_holdout", reason: "no holdout to score; nothing is decided" } })} />,
    );
    expect(screen.getByText("Holdout").parentElement).toHaveTextContent("—");
    expect(screen.getByText("not scored")).toBeInTheDocument();
  });
});
