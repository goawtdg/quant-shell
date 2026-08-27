import { cn } from "@/lib/utils";
import { actionTone } from "@/lib/format";

const toneClass: Record<string, string> = {
  buy: "text-emerald-700 dark:text-emerald-400 border-emerald-600/30 bg-emerald-600/5 dark:border-emerald-400/30 dark:bg-emerald-400/10",
  reduce: "text-ember border-ember/40 bg-ember/10",
  hold: "text-foreground border-border bg-muted",
  wait: "text-subtle border-border bg-transparent",
  alert: "text-red-600 dark:text-red-400 border-red-500/30 bg-red-500/5 dark:border-red-400/30 dark:bg-red-400/10",
};

export function ActionBadge({ action }: { action?: string | null }) {
  const tone = actionTone(action);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[3px] border px-2 py-0.5 text-xs font-medium font-mono",
        toneClass[tone]
      )}
    >
      {action || "WAIT"}
    </span>
  );
}

export function TrustBadge({
  reliable,
  fallback,
}: {
  reliable?: boolean;
  fallback?: boolean;
}) {
  if (fallback || reliable === false) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
        Fallback
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 dark:text-emerald-400">
      <span className="h-1.5 w-1.5 rounded-full bg-emerald-600 dark:bg-emerald-400" />
      Reliable
    </span>
  );
}

export function SimBadge() {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-subtle">
      <span className="h-1.5 w-1.5 rounded-full bg-subtle" />
      Sim
    </span>
  );
}
