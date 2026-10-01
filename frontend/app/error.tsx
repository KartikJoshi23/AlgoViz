"use client";

import { useEffect } from "react";

import { Button } from "@/components/ds";
import { EmptyState, PageHeader } from "@/components/ui/PageHeader";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <div className="mx-auto mt-6 max-w-lg space-y-3">
      <PageHeader title="Something broke" subtitle={error.digest ? `digest ${error.digest}` : undefined} />
      <EmptyState
        title={error.message || "An unexpected error occurred while rendering this view."}
        action={
          <div className="flex gap-2">
            <Button variant="primary" onClick={reset}>
              Try again
            </Button>
            <Button onClick={() => window.location.reload()}>Reload</Button>
          </div>
        }
      />
    </div>
  );
}
