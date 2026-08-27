"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ActionBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MiniOhlcv } from "@/components/charts/mini-ohlcv";
import { fetchOhlcv, fetchPositions, fetchRunDiff, saveNote } from "@/lib/api";
import { formatMoney, formatPct } from "@/lib/format";
import { ManualOrderForm } from "@/components/decisions/manual-order-form";
import type { DiffChange, OhlcvBar, PositionRow, PositionsResponse } from "@/types";

export default function PositionsPage() {
  const [data, setData] = useState<PositionsResponse | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [ohlcv, setOhlcv] = useState<OhlcvBar[]>([]);
  const [diff, setDiff] = useState<DiffChange[]>([]);
  const [noteDraft, setNoteDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (live = false) => {
    setLoading(true);
    setError(null);
    try {
      const [p, d] = await Promise.all([fetchPositions(live), fetchRunDiff()]);
      setData(p);
      setDiff(d.changes || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleRow(row: PositionRow) {
    if (open === row.symbol) {
      setOpen(null);
      return;
    }
    setOpen(row.symbol);
    setNoteDraft(row.note || "");
    try {
      const o = await fetchOhlcv(row.symbol);
      setOhlcv(o.data || []);
    } catch {
      setOhlcv([]);
    }
  }

  async function onSaveNote(symbol: string) {
    await saveNote(symbol, noteDraft);
    await load();
  }

  return (
    <>
      <Topbar
        asOf={data?.generated_at || data?.updated_at}
        runId={data?.run_id}
        onRefresh={() => void load(true)}
        loading={loading}
        trailing={
          data?.price_stale ? (
            <span className="text-xs text-amber-600 dark:text-amber-400">行情为缓存/估算</span>
          ) : data?.price_as_of ? (
            <span className="text-xs text-muted-foreground">
              行情 {data.price_as_of.slice(11, 16)}
            </span>
          ) : null
        }
      />
      <main className="space-y-4 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-normal tracking-tight">持仓</h1>
            <p className="mt-0.5 text-xs text-subtle">
              总浮盈{" "}
              <span className="font-mono text-foreground">
                {data ? formatMoney(data.total_pnl) : "-"} (
                {data ? formatPct(data.total_pnl_pct) : "-"})
              </span>
              {data?.price_stale ? (
                <span className="ml-2 text-amber-600 dark:text-amber-400">现价来自缓存/估算</span>
              ) : null}
            </p>
          </div>
        </div>

        {error ? (
          <Card>
            <CardContent className="p-4 text-sm text-red-400">{error}</CardContent>
          </Card>
        ) : null}

        <Card>
          <CardContent className="overflow-x-auto p-0">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead className="border-b border-border text-xs text-subtle">
                <tr>
                  <th className="px-4 py-3 font-medium">代码</th>
                  <th className="px-4 py-3 font-medium">成本</th>
                  <th className="px-4 py-3 font-medium">现价</th>
                  <th className="px-4 py-3 font-medium">数量</th>
                  <th className="px-4 py-3 font-medium">浮盈%</th>
                  <th className="px-4 py-3 font-medium">持有天</th>
                  <th className="px-4 py-3 font-medium">Peak%</th>
                  <th className="px-4 py-3 font-medium">最近决策</th>
                </tr>
              </thead>
              <tbody>
                {loading || !data ? (
                  <tr>
                    <td colSpan={8} className="p-4">
                      <Skeleton className="h-20 w-full" />
                    </td>
                  </tr>
                ) : (
                  data.positions.map((row) => (
                    <Fragment key={row.symbol}>
                      <tr
                        className="h-14 cursor-pointer border-b border-border hover:bg-muted/60"
                        onClick={() => void toggleRow(row)}
                      >
                        <td className="px-4">
                          <div className="font-mono font-medium">{row.symbol}</div>
                          <div className="text-xs text-muted-foreground">{row.name}</div>
                        </td>
                        <td className="px-4 font-mono">{row.avg_cost.toFixed(2)}</td>
                        <td className="px-4 font-mono">{row.price.toFixed(2)}</td>
                        <td className="px-4 font-mono">{row.quantity}</td>
                        <td
                          className={`px-4 font-mono ${
                            row.unrealized_pnl_pct >= 0
                              ? "text-emerald-600 dark:text-emerald-400"
                              : "text-red-600 dark:text-red-400"
                          }`}
                        >
                          {formatPct(row.unrealized_pnl_pct)}
                        </td>
                        <td className="px-4 font-mono">{row.holding_days}</td>
                        <td className="px-4 font-mono">{formatPct(row.peak_pct)}</td>
                        <td className="px-4">
                          <ActionBadge action={row.last_action || "HOLD"} />
                        </td>
                      </tr>
                      {open === row.symbol ? (
                        <tr key={`${row.symbol}-detail`} className="border-b border-border">
                          <td colSpan={8} className="bg-muted/40 px-4 py-4">
                            <div className="grid gap-4 lg:grid-cols-2">
                              <div>
                                <div className="mb-2 text-xs text-muted-foreground">收盘价走势</div>
                                <MiniOhlcv data={ohlcv} />
                              </div>
                              <div className="space-y-3">
                                <div>
                                  <div className="mb-2 text-xs text-muted-foreground">
                                    相对上次 run 变化（该标的）
                                  </div>
                                  <ul className="space-y-1 text-xs text-muted-foreground">
                                    {diff
                                      .filter((c) => c.symbol === row.symbol)
                                      .map((c, i) => (
                                        <li key={i} className="font-mono">
                                          {c.from_action || "-"} → {c.to_action || "-"} ({c.change})
                                        </li>
                                      ))}
                                    {!diff.some((c) => c.symbol === row.symbol) ? (
                                      <li>无动作变化</li>
                                    ) : null}
                                  </ul>
                                </div>
                                <div>
                                  <div className="mb-2 text-xs text-muted-foreground">人工批注</div>
                                  <textarea
                                    className="min-h-20 w-full rounded-none border border-border bg-background p-2 text-sm text-foreground"
                                    value={noteDraft}
                                    onChange={(e) => setNoteDraft(e.target.value)}
                                    onClick={(e) => e.stopPropagation()}
                                  />
                                  <Button
                                    size="sm"
                                    className="mt-2"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      void onSaveNote(row.symbol);
                                    }}
                                  >
                                    保存批注
                                  </Button>
                                </div>
                                <div onClick={(e) => e.stopPropagation()}>
                                  <ManualOrderForm
                                    defaultSymbol={row.symbol}
                                    onDone={() => void load()}
                                  />
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  ))
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Run Diff（相对上一轮）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {diff.length ? (
              diff.slice(0, 12).map((c, i) => (
                <div key={i} className="flex flex-wrap gap-2 text-sm">
                  <span className="font-mono">{c.symbol}</span>
                  <span className="text-muted-foreground">{c.tab}</span>
                  <span className="font-mono text-foreground">
                    {c.from_action || "-"} → {c.to_action || "-"}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">无差异或缺少历史 run</p>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
