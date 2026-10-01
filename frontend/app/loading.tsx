export default function Loading() {
  return (
    <div className="grid gap-3 md:grid-cols-12" role="status" aria-busy="true" aria-label="Loading">
      <div className="skeleton h-28 md:col-span-12" />
      <div className="skeleton h-72 md:col-span-8" />
      <div className="skeleton h-72 md:col-span-4" />
      <div className="skeleton h-56 md:col-span-4" />
      <div className="skeleton h-56 md:col-span-4" />
      <div className="skeleton h-56 md:col-span-4" />
    </div>
  );
}
