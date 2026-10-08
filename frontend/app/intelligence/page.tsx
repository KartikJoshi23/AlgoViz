"use client";

import { Badge } from "@/components/ds";
import { DriftPanel } from "@/components/intelligence/DriftPanel";
import { EdgeStudyPanel } from "@/components/intelligence/EdgeStudyPanel";
import { ImportancePanel, ShapPanel } from "@/components/intelligence/ExplainPanels";
import { RegistryPanel, SignalRulesPanel } from "@/components/intelligence/RegistryPanels";
import { ReliabilityPanel } from "@/components/intelligence/ReliabilityPanel";
import { WalkForwardPanel } from "@/components/intelligence/WalkForwardPanel";
import { PredictionPanel } from "@/components/panels/PredictionPanel";
import { RegimePanel } from "@/components/panels/RegimePanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { useModelInfo } from "@/lib/api/hooks";
import { useConnection, usePrediction } from "@/lib/store";

export default function IntelligencePage() {
  const conn = useConnection();
  const p = usePrediction();
  const info = useModelInfo(conn.symbol);

  return (
    <div className="space-y-3">
      <PageHeader
        eyebrow="Machine learning"
        title="Intelligence"
        subtitle={`${conn.symbol} · calibrated next-move probabilities · walk-forward validated · explained · monitored for drift`}
        actions={
          <>
            {p && (
              <Badge tone={p.status === "ready" ? "good" : "warning"}>
                {p.status.replace("_", " ")}
                {p.training ? " · training" : ""}
              </Badge>
            )}
            {info.data && (
              <Badge>
                <span className="num">
                  v{info.data.model_version} · retrain in {info.data.next_retrain_in_samples} samples
                </span>
              </Badge>
            )}
          </>
        }
      />

      <div className="grid gap-3 lg:grid-cols-12">
        <div className="grid gap-3 lg:col-span-4">
          <PredictionPanel />
          <RegimePanel />
        </div>
        <DriftPanel className="lg:col-span-8" symbol={conn.symbol} />
      </div>

      <div className="grid gap-3 lg:grid-cols-12">
        <WalkForwardPanel className="lg:col-span-7" info={info.data} />
        <div className="grid content-start gap-3 lg:col-span-5">
          <ReliabilityPanel symbol={conn.symbol} info={info.data} />
          <RegistryPanel symbol={conn.symbol} />
        </div>
      </div>

      <EdgeStudyPanel symbol={conn.symbol} />

      <div className="grid gap-3 lg:grid-cols-2">
        <ShapPanel symbol={conn.symbol} />
        <ImportancePanel info={info.data} />
      </div>

      <SignalRulesPanel symbol={conn.symbol} />
    </div>
  );
}
