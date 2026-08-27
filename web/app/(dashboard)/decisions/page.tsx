import { Suspense } from "react";
import { DecisionsView } from "./decisions-view";
import { Skeleton } from "@/components/ui/skeleton";

export default function DecisionsPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4 p-6">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      }
    >
      <DecisionsView />
    </Suspense>
  );
}
