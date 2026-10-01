import Link from "next/link";

import { EmptyState, PageHeader } from "@/components/ui/PageHeader";

export default function NotFound() {
  return (
    <div className="mx-auto mt-6 max-w-lg space-y-3">
      <PageHeader title="Page not found" subtitle="404" />
      <EmptyState
        title="That level isn't on the book."
        body="The page you asked for doesn't exist. The overview has the live market."
        action={
          <Link href="/" className="btn btn-primary">
            Back to the overview
          </Link>
        }
      />
    </div>
  );
}
