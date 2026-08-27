"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/topbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionBadge } from "@/components/ui/badge";
import { ActionDonut } from "@/components/charts/action-donut";
import { WeightPie } from "@/components/charts/weight-pie";
import { PnlBars } from "@/components/charts/pnl-bars";
import { fetchOverview } from "@/lib/api";
import { formatMoney, formatPct, formatTs } from "@/lib/format";
import type { PositionsResponse, RunMeta, Snapshot } from "@/types";

export default function OverviewPage() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [pos, setPos] = useState<PositionsResponse | null>(null);
  const [runs, setRuns] = useState<RunMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (live = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOverview(live, 40);
      setSnap(data.snapshot);
      setPos(data.positions);
      setRuns((data.runs || []).slice(0, 5));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <>
      <Topbar
        asOf={snap?.last_run_at}
        runId={snap?.run_id}
        onRefresh={() => void load(true)}
        loading={loading}
        trailing={
          snap?.price_stale ? (
            <span className="text-xs text-amber-500">行情为缓存/估算</span>
          ) : snap?.price_as_of ? (
            <span className="text-xs text-muted-foreground">
              行情 {snap.price_as_of.slice(11, 16)}
            </span>
          ) : null
        }
      />
      <main className="space-y-6 p-6">
        {error ? (
          <Card>
            <CardContent className="p-4 text-sm text-red-400">
              API 不可用：{error}。请先在仓库根启动{" "}
              <span className="font-mono">python -m quant_shell.desk</span>
            </CardContent>
          </Card>
        ) : null}

        <div className="grid gap-4 md:grid-cols-3">
          <KpiCard
            title="组合权益"
            loading={loading}
            value={snap ? formatMoney(snap.equity) : "-"}
            sub={
              snap?.equity_change_pct != null
                ? `较基线 ${formatPct(snap.equity_change_pct)}${
                    snap.equity_prev != null
                      ? `（${formatMoney(snap.equity_prev)}）`
                      : ""
                  }`
                : "模拟盘 · 暂无对比基线"
            }
          />
          <KpiCard
            title="现金 / 仓位"
            loading={loading}
            value={snap ? formatMoney(snap.cash) : "-"}
            sub={
              snap
                ? `仓位占比 ${(snap.position_pct * 100).toFixed(1)}% · 持仓市值 ${formatMoney(snap.position_value)}`
                : "-"
            }
          />
          <Card>
            <CardHeader>
              <CardTitle>本轮动作计数</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !snap ? (
                <Skeleton className="h-16 w-full" />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(["WAIT", "HOLD", "REDUCE", "BUY"] as const).map((k) => (
                    <div
                      key={k}
                      className="rounded-[3px] border border-border px-3 py-2"
                    >
                      <div className="text-[11px] text-subtle">{k}</div>
                      <div className="font-mono text-lg">
                        {snap.action_counts[k] || 0}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>持仓权重</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !pos ? (
                <Skeleton className="h-56 w-full" />
              ) : (
                <WeightPie
                  positions={pos.positions}
                  cash={pos.cash}
                  equity={pos.equity}
                />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>浮盈%（按标的）</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !pos ? (
                <Skeleton className="h-56 w-full" />
              ) : (
                <PnlBars positions={pos.positions} />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle>动作分布</CardTitle>
            </CardHeader>
            <CardContent>
              {loading || !snap ? (
                <Skeleton className="h-48 w-full" />
              ) : (
                <ActionDonut counts={snap.action_counts} />
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>最近告警</CardTitle>
              <Link href="/decisions" className="text-xs text-subtle hover:text-foreground">
                决策板
              </Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <Skeleton className="h-24 w-full" />
              ) : snap?.alerts?.length ? (
                snap.alerts.map((a) => (
                  <div key={`${a.symbol}-${a.level}-${a.message.slice(0, 20)}`} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm">{a.symbol}</span>
                      <ActionBadge action={a.level === "ACTION" ? "ALERT" : "WAIT"} />
                    </div>
                    <p className="line-clamp-2 text-xs text-muted-foreground">{a.message}</p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">无告警</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>最近成交</CardTitle>
              <Link href="/positions" className="text-xs text-subtle hover:text-foreground">
                持仓
              </Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {loading ? (
                <Skeleton className="h-24 w-full" />
              ) : snap?.recent_trades?.length ? (
                snap.recent_trades.map((t, i) => (
                  <div key={`${t.symbol}-${t.timestamp}-${i}`} className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm">{t.symbol}</span>
                      <ActionBadge action={t.action} />
                      <span className="font-mono text-xs text-muted-foreground">
                        {formatTs(t.timestamp)}
                      </span>
                    </div>
                    <p className="line-clamp-2 text-xs text-muted-foreground">
                      {t.reason || `${t.quantity} @ ${t.fill_price}`}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">暂无成交</p>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>最近联动 Runs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : runs.length ? (
              runs.map((r) => (
                <Link
                  key={r.filename}
                  href={`/decisions?run=${encodeURIComponent(r.run_id)}`}
                  className="flex flex-wrap items-center gap-3 rounded-[3px] px-2 py-1.5 text-sm hover:bg-muted"
                >
                  <span className="font-mono text-foreground">{r.run_id}</span>
                  <span className="font-mono text-xs text-subtle">
                    {formatTs(r.created_at)}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    决策 {r.decision_count} · 成交 {r.trade_count}
                  </span>
                  <span className="text-xs text-ember">查看决策板 →</span>
                </Link>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">无历史 run</p>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}

function KpiCard({
  title,
  value,
  sub,
  loading,
}: {
  title: string;
  value: string;
  sub: string;
  loading: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-12 w-40" />
        ) : (
          <>
            <div className="font-mono text-[26px] font-medium tracking-tight">
              {value}
            </div>
            <div className="mt-1 text-xs text-subtle">{sub}</div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
