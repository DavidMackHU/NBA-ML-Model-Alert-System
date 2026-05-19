export function Sk({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-zinc-800 ${className}`} />;
}

export function AlertCardSkeleton() {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <Sk className="h-3 w-16" />
          <Sk className="h-5 w-48" />
          <Sk className="h-4 w-36" />
        </div>
        <div className="shrink-0 space-y-1.5">
          <Sk className="ml-auto h-7 w-16" />
          <Sk className="ml-auto h-3 w-14" />
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 divide-x divide-zinc-800">
        {[0, 1, 2].map((i) => (
          <div key={i} className="space-y-1.5 px-2 text-center">
            <Sk className="mx-auto h-3 w-10" />
            <Sk className="mx-auto h-4 w-14" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function StatCardSkeleton() {
  return (
    <div className="space-y-2 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
      <Sk className="h-3 w-16" />
      <Sk className="h-7 w-24" />
    </div>
  );
}

const BAR_HEIGHTS = [40, 70, 55, 85, 60, 90, 45, 75, 65, 80];

export function ChartSkeleton({ className = "h-60" }: { className?: string }) {
  return (
    <div
      className={`flex items-end gap-2 rounded-xl border border-zinc-800 bg-zinc-900 px-6 pb-8 pt-4 ${className}`}
    >
      {BAR_HEIGHTS.map((h, i) => (
        <div
          key={i}
          className="flex-1 animate-pulse rounded-t bg-zinc-800"
          style={{ height: `${h}%` }}
        />
      ))}
    </div>
  );
}
