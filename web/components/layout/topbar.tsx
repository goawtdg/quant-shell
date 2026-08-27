"use client";

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SimBadge } from "@/components/ui/badge";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { formatTs } from "@/lib/format";

export function Topbar({
  asOf,
  runId,
  onRefresh,
  loading,
  trailing,
}: {
  asOf?: string;
  runId?: string;
  onRefresh?: () => void;
  loading?: boolean;
  trailing?: React.ReactNode;
}) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-subtle">
          数据截止：
          <span className="ml-1 font-mono text-foreground">{formatTs(asOf)}</span>
        </span>
        {runId ? (
          <span className="font-mono text-xs text-subtle">
            run={runId}
          </span>
        ) : null}
        <SimBadge />
      </div>
      <div className="flex items-center gap-2">
        {trailing}
        <ThemeToggle />
        {onRefresh ? (
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw
              className={loading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
            />
            刷新
          </Button>
        ) : null}
      </div>
    </header>
  );
}
