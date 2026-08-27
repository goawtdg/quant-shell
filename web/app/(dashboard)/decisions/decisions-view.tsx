"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Topbar } from "@/components/layout/topbar";
import { DecisionCard } from "@/components/decisions/decision-card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionDonut } from "@/components/charts/action-donut";
import { fetchDecisions, fetchRuns } from "@/lib/api";
import { formatTs } from "@/lib/format";
import type { ActionCounts, DecisionItem, RunMeta } from "@/types";

type TabKey = "etf" | "hold" | "stock";
type FilterKey = "all" | "buyable" | "executed" | "manual";

export function DecisionsView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const runFromUrl = searchParams.get("run") || "";

  const [tab, setTab] = useState<TabKey>("hold");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [runId, setRunId] = useState<string>(runFromUrl);
  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [items, setItems] = useState<DecisionItem[]>([]);
  const [meta, setMeta] = useState<{
    runId?: string;
    asOf?: string;
    isLatest?: boolean;
  }>({});
  const [counts, setCounts] = useState<ActionCounts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRunId(runFromUrl);
  }, [runFromUrl]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, r] = await Promise.all([
        fetchDecisions(tab, filter, runId || null),
        fetchRuns(),
      ]);
      setItems(d.items);
      setMeta({
        runId: d.run_id,
        asOf: d.generated_at,
        isLatest: d.is_latest !== false,
      });
      setCounts(d.action_counts || null);
      setRuns(r.runs || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [tab, filter, runId]);

  useEffect(() => {
    void load();
  }, [load]);

  function onSelectRun(next: string) {
    setRunId(next);
    const q = new URLSearchParams();
    if (next) q.set("run", next);
    const qs = q.toString();
    router.replace(qs ? `/decisions?${qs}` : "/decisions");
  }

  return (
    <>
      <Topbar
        asOf={meta.asOf}
        runId={meta.runId}
        onRefresh={load}
        loading={loading}
      />
      <main className="space-y-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-normal tracking-tight">决策板</h1>
            {!meta.isLatest && meta.runId ? (
              <p className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">
                正在查看历史 run（只读重放）
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="h-9 max-w-[280px] rounded-none border border-border bg-card px-3 font-mono text-sm"
              value={runId}
              onChange={(e) => onSelectRun(e.target.value)}
            >
              <option value="">最新 (latest)</option>
              {runs.map((r) => (
                <option key={r.filename} value={r.run_id}>
                  {r.run_id} · {formatTs(r.created_at)}
                </option>
              ))}
            </select>
            <select
              className="h-9 rounded-none border border-border bg-card px-3 text-sm"
              value={filter}
              onChange={(e) => setFilter(e.target.value as FilterKey)}
            >
              <option value="all">全部</option>
              <option value="buyable">可买</option>
              <option value="executed">已成交</option>
              <option value="manual">需人工</option>
            </select>
          </div>
        </div>

        {error ? (
          <Card>
            <CardContent className="p-4 text-sm text-red-400">{error}</CardContent>
          </Card>
        ) : null}

        <Tabs value={tab} onValueChange={(v: string) => setTab(v as TabKey)}>
          <TabsList>
            <TabsTrigger value="etf">ETF 策略</TabsTrigger>
            <TabsTrigger value="hold">持仓审视</TabsTrigger>
            <TabsTrigger value="stock">个股入场</TabsTrigger>
          </TabsList>
          {(["etf", "hold", "stock"] as TabKey[]).map((t) => (
            <TabsContent key={t} value={t} className="space-y-3">
              {loading ? (
                <>
                  <Skeleton className="h-28 w-full" />
                  <Skeleton className="h-28 w-full" />
                </>
              ) : items.length ? (
                items.map((item) => (
                  <DecisionCard
                    key={`${item.symbol}-${item.tab}`}
                    item={item}
                    runId={meta.runId}
                    isLatest={meta.isLatest !== false}
                    onOrderDone={() => void load()}
                  />
                ))
              ) : (
                <p className="text-sm text-muted-foreground">当前筛选无结果</p>
              )}
            </TabsContent>
          ))}
        </Tabs>

        <Card>
          <CardHeader>
            <CardTitle>本轮动作分布</CardTitle>
          </CardHeader>
          <CardContent>
            {counts ? <ActionDonut counts={counts} /> : <Skeleton className="h-48" />}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
