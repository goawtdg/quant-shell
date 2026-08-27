"use client";

import { useCallback, useEffect, useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cancelJob, fetchJob, fetchJobs, startJob } from "@/lib/api";
import { formatTs } from "@/lib/format";
import type { DeskJob } from "@/types";

function statusTone(status: string) {
  if (status === "running" || status === "starting") return "text-ember";
  if (status === "succeeded") return "text-emerald-600 dark:text-emerald-400";
  if (status === "failed") return "text-red-600 dark:text-red-400";
  if (status === "cancelled") return "text-brass dark:text-brass";
  return "text-subtle";
}

export default function JobsPage() {
  const [tradeJob, setTradeJob] = useState<DeskJob | null>(null);
  const [recent, setRecent] = useState<DeskJob[]>([]);
  const [log, setLog] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [skipIntel, setSkipIntel] = useState(true);
  const [skipStocks, setSkipStocks] = useState(true);
  const [symbol, setSymbol] = useState("510300");

  const [confirm, setConfirm] = useState<null | {
    type: "shell_paper" | "linkage";
    title: string;
  }>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJobs();
      const trade = data.lanes.trade || null;
      setTradeJob(trade);
      setRecent(data.recent || []);

      const focusId = selectedId || trade?.id || data.recent?.[0]?.id || null;
      if (focusId) {
        const detail = await fetchJob(focusId);
        setLog(detail.log_tail || "");
        if (!selectedId) setSelectedId(focusId);
      }
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const tradeBusy = tradeJob?.status === "running" || tradeJob?.status === "starting";

  useEffect(() => {
    if (!tradeBusy) return;
    const t = setInterval(() => void refresh(), 2000);
    return () => clearInterval(t);
  }, [tradeBusy, refresh]);

  async function onConfirmStart() {
    if (!confirm) return;
    setBusy(true);
    setError(null);
    try {
      const params =
        confirm.type === "shell_paper"
          ? { symbol: symbol.trim() || "510300" }
          : {
              skip_intel: skipIntel,
              skip_stocks: skipStocks,
              skip_hold_review: true,
              symbol: skipStocks ? symbol.trim() || "510300" : undefined,
            };
      const started = await startJob(confirm.type, params, true);
      setConfirm(null);
      setSelectedId(started.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }

  async function onCancel(jobId: string) {
    setBusy(true);
    try {
      await cancelJob(jobId);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "取消失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Topbar
        asOf={tradeJob?.created_at || recent[0]?.created_at}
        runId={tradeJob?.id}
        onRefresh={refresh}
        loading={loading}
        trailing={
          tradeBusy ? (
            <span className="rounded-[3px] border border-ember/40 bg-ember/10 px-2 py-1 font-mono text-xs text-ember">
              运行中…
            </span>
          ) : null
        }
      />
      <main className="space-y-6 p-6">
        <div>
          <h1 className="text-xl font-normal tracking-tight">任务中心</h1>
          <p className="mt-1 text-xs text-subtle">
            本仓任务：纸面七层 / linkage。请先在「交易想法」保存模型。不触发实盘。
          </p>
        </div>

        {error ? (
          <Card>
            <CardContent className="p-4 text-sm text-red-600 dark:text-red-400">{error}</CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>当前任务</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {loading ? (
              <Skeleton className="h-12 w-full" />
            ) : tradeBusy && tradeJob ? (
              <>
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span className="font-mono">{tradeJob.id}</span>
                  <span className="font-mono text-muted-foreground">{tradeJob.type}</span>
                  <span className={`font-mono ${statusTone(tradeJob.status)}`}>
                    {tradeJob.status}
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={busy}
                  onClick={() => void onCancel(tradeJob.id)}
                >
                  取消
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">空闲 · 尚无历史任务</p>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>跑一次纸面</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                `python -m quant_shell.cli run --symbol …` 单标的七层管道。
              </p>
              <label className="block text-xs text-muted-foreground">
                标的
                <input
                  className="mt-1 h-9 w-full rounded-none border border-border bg-background px-3 font-mono text-sm"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                />
              </label>
              <Button
                disabled={tradeBusy || busy}
                onClick={() =>
                  setConfirm({ type: "shell_paper", title: "确认跑一次纸面？" })
                }
              >
                启动纸面
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Linkage</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                `python -m quant_shell.cli linkage`。默认跳过情报与选股，适合本仓自测。
              </p>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={skipIntel}
                  onChange={(e) => setSkipIntel(e.target.checked)}
                />
                跳过情报
              </label>
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input
                  type="checkbox"
                  checked={skipStocks}
                  onChange={(e) => setSkipStocks(e.target.checked)}
                />
                跳过截面选股
              </label>
              <Button
                disabled={tradeBusy || busy}
                onClick={() =>
                  setConfirm({ type: "linkage", title: "确认启动 linkage？" })
                }
              >
                启动 linkage
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>最近任务</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {recent.length ? (
                recent.slice(0, 8).map((j) => (
                  <button
                    key={j.id}
                    type="button"
                    className="flex w-full flex-wrap items-center gap-2 rounded-[3px] px-2 py-1.5 text-left text-sm hover:bg-muted"
                    onClick={() => {
                      setSelectedId(j.id);
                      void fetchJob(j.id).then((d) => setLog(d.log_tail || ""));
                    }}
                  >
                    <span className="font-mono">{j.id}</span>
                    <span className="font-mono text-xs text-muted-foreground">{j.type}</span>
                    <span className={`font-mono text-xs ${statusTone(j.status)}`}>
                      {j.status}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {formatTs(j.created_at)}
                    </span>
                  </button>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">暂无历史（初始化空系统）</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>日志尾部</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="max-h-72 overflow-auto rounded-[3px] border border-border bg-muted/40 p-3 font-mono text-[11px] leading-relaxed text-muted-foreground whitespace-pre-wrap">
                {log || "（选择任务或等待运行）"}
              </pre>
            </CardContent>
          </Card>
        </div>
      </main>

      <Dialog
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={confirm?.title || "确认"}
      >
        <p className="mb-4 text-sm text-muted-foreground">
          {confirm?.type === "shell_paper"
            ? `将执行 quant_shell.cli run --symbol ${symbol.trim() || "510300"}`
            : `将执行 quant_shell.cli linkage${skipIntel ? " --skip-intel" : ""}${skipStocks ? " --skip-stocks" : ""}`}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setConfirm(null)}>
            取消
          </Button>
          <Button disabled={busy} onClick={() => void onConfirmStart()}>
            确认启动
          </Button>
        </div>
      </Dialog>
    </>
  );
}
