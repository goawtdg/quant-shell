"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/topbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  deleteLinkageReport,
  downloadLinkagePdf,
  fetchLinkageReportList,
  linkageHtmlUrl,
} from "@/lib/api";
import type { LinkageReportListItem } from "@/types";

function formatWhen(iso?: string) {
  if (!iso) return "-";
  const day = iso.slice(0, 10);
  const hm = iso.length >= 16 ? iso.slice(11, 16) : "";
  return hm ? `${day} ${hm}` : day;
}

export default function ReportPage() {
  const [items, setItems] = useState<LinkageReportListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pdfBusy, setPdfBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchLinkageReportList(40);
      const list = data.items || [];
      setItems(list);
      setSelectedId((prev) => {
        if (prev && list.some((x) => x.run_id === prev)) return prev;
        return list[0]?.run_id ?? null;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = items.find((x) => x.run_id === selectedId) || null;

  async function onDownloadPdf() {
    if (!selected?.run_id) return;
    setPdfBusy(true);
    setHint("正在下载 PDF…");
    setError(null);
    try {
      await downloadLinkagePdf(selected.run_id);
      setHint("已开始下载");
      window.setTimeout(() => setHint(null), 2500);
      await load();
    } catch (e) {
      setHint(null);
      setError(e instanceof Error ? e.message : "PDF 下载失败");
    } finally {
      setPdfBusy(false);
    }
  }

  async function onDeleteSelected() {
    if (!selected?.run_id) return;
    if (
      !window.confirm(
        `确认删除报告 ${selected.run_id}？\n将删除对应 json/pdf/html，不可恢复。`
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await deleteLinkageReport(selected.run_id);
      setHint(`已删除 ${selected.run_id}`);
      setSelectedId(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Topbar
        asOf={selected?.generated_at}
        runId={selected?.run_id}
        onRefresh={load}
        loading={loading}
      />
      <main className="space-y-4 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-normal tracking-tight">联动报告</h1>
            <p className="mt-1 text-xs text-subtle">
              点选后可下载或删除。详情在文件里。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Link href="/decisions" className="text-sm text-ember hover:underline">
              打开决策板
            </Link>
          </div>
        </div>

        {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}

        {error ? (
          <Card>
            <CardContent className="p-4 text-sm text-red-600 dark:text-red-400">{error}</CardContent>
          </Card>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <Card>
            <CardHeader>
              <CardTitle>历史报告</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1">
              {loading && !items.length ? (
                <Skeleton className="h-32 w-full" />
              ) : items.length ? (
                items.map((item) => {
                  const active = item.run_id === selectedId;
                  return (
                    <button
                      key={item.run_id}
                      type="button"
                      onClick={() => setSelectedId(item.run_id)}
                      className={`flex w-full items-center justify-between gap-3 rounded-[3px] border px-3 py-2.5 text-left text-sm transition-colors ${
                        active
                          ? "border-foreground/40 bg-muted"
                          : "border-border hover:bg-muted/60"
                      }`}
                    >
                      <div className="min-w-0">
                        <div className="font-medium">{formatWhen(item.generated_at)}</div>
                        <div className="truncate font-mono text-xs text-muted-foreground">
                          {item.run_id}
                        </div>
                      </div>
                      <div className="shrink-0 text-right text-[11px] text-muted-foreground">
                        <div>
                          B{item.buy ?? 0} R{item.reduce ?? 0} H{item.hold ?? 0} W
                          {item.wait ?? 0}
                        </div>
                        <div>{item.has_pdf ? "PDF ✓" : "无 PDF"}</div>
                      </div>
                    </button>
                  );
                })
              ) : (
                <p className="text-sm text-muted-foreground">
                  暂无报告。请先在任务中心跑一次 linkage。
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>当前选中</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {selected ? (
                <>
                  <div className="space-y-1 text-sm">
                    <div>{formatWhen(selected.generated_at)}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {selected.run_id}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      BUY {selected.buy ?? 0} · REDUCE {selected.reduce ?? 0} · HOLD{" "}
                      {selected.hold ?? 0} · WAIT {selected.wait ?? 0}
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button
                      disabled={pdfBusy || busy}
                      onClick={() => void onDownloadPdf()}
                    >
                      {pdfBusy ? "准备中…" : "下载 PDF"}
                    </Button>
                    <a
                      className="inline-flex h-9 items-center justify-center rounded-none border border-border px-3 text-sm hover:bg-muted"
                      href={linkageHtmlUrl(selected.run_id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      打开 HTML
                    </a>
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() => void onDeleteSelected()}
                      className="text-red-600 dark:text-red-400"
                    >
                      删除此报告
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">请先选择左侧一条报告</p>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </>
  );
}
