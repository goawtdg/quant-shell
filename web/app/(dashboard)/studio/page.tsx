"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  compileStudioIdea,
  fetchJob,
  fetchStudioModel,
  saveStudioModel,
  startJob,
  type StudioCatalogItem,
  type StudioModel,
} from "@/lib/api";

const PRESETS = [
  "用20日动量追涨，回撤超过12%就不要开仓",
  "低波动稳健一些，宁可少买，单票不超过8%",
  "价格在均线上方才买，放量更好",
];

function pct(n: number) {
  return Math.round(n * 1000) / 10;
}

function labelOf(catalog: StudioCatalogItem[], id: string) {
  return catalog.find((c) => c.id === id)?.label || id;
}

function hintOf(catalog: StudioCatalogItem[], id: string) {
  return catalog.find((c) => c.id === id)?.hint || "";
}

export default function StudioPage() {
  const [idea, setIdea] = useState("");
  const [model, setModel] = useState<StudioModel | null>(null);
  const [catalog, setCatalog] = useState<StudioCatalogItem[]>([]);
  const [active, setActive] = useState(false);
  const [compiler, setCompiler] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runLog, setRunLog] = useState("");
  const [runId, setRunId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchStudioModel();
      setModel(data.model);
      setCatalog(data.catalog || []);
      setActive(Boolean(data.active));
      setError(data.available === false ? data.detail || "quant-shell 未安装" : null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!runId) return;
    let stop = false;
    const tick = async () => {
      try {
        const job = await fetchJob(runId);
        if (stop) return;
        setRunLog(job.log_tail || "");
        if (job.status === "running" || job.status === "starting") {
          window.setTimeout(() => void tick(), 2000);
        }
      } catch {
        /* ignore poll errors */
      }
    };
    void tick();
    return () => {
      stop = true;
    };
  }, [runId]);

  const enabledCount = useMemo(
    () => (model?.factors || []).filter((f) => f.enabled).length,
    [model]
  );

  async function compile(text: string) {
    const ideaText = text.trim();
    if (!ideaText || busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = await compileStudioIdea(ideaText);
      setModel(data.model);
      setCatalog(data.catalog || catalog);
      setCompiler(data.compiler || null);
      setIdea(data.model.idea || ideaText);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!model || busy) return;
    setBusy(true);
    setError(null);
    try {
      const data = await saveStudioModel(model);
      setModel(data.model);
      setActive(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function runPaper() {
    if (!model || busy) return;
    setBusy(true);
    setError(null);
    try {
      await saveStudioModel(model);
      setActive(true);
      const job = await startJob("shell_paper", { symbol: model.symbol }, true);
      setRunId(job.id);
      setRunLog("已启动模拟盘…");
    } catch (e) {
      setError(e instanceof Error ? e.message : "启动失败");
    } finally {
      setBusy(false);
    }
  }

  function patchFactor(id: string, patch: Partial<StudioModel["factors"][number]>) {
    if (!model) return;
    setModel({
      ...model,
      factors: model.factors.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    });
  }

  return (
    <>
      <Topbar />
      <main className="grid min-h-[calc(100vh-3.5rem)] gap-4 p-6 lg:grid-cols-[minmax(280px,1fr)_minmax(320px,1.2fr)]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>写下你的交易想法</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              不用写代码。用白话说清楚：看什么、什么时候买、亏多少就停。生成后可以再改卡片。
            </p>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="rounded-[3px] border border-border px-2.5 py-1.5 text-left text-xs text-foreground hover:bg-muted"
                  onClick={() => {
                    setIdea(p);
                    void compile(p);
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
            <textarea
              className="min-h-[140px] w-full rounded-none border border-border bg-background px-3 py-2 text-sm text-foreground"
              placeholder="例如：追20日动量，回撤超过12%就不要开仓，单票仓位小一点。"
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
            />
            <Button
              type="button"
              disabled={busy || !idea.trim()}
              onClick={() => void compile(idea)}
            >
              {busy ? "生成中…" : "生成交易模型"}
            </Button>
            {compiler ? (
              <p className="text-xs text-muted-foreground">
                编译方式：{compiler === "llm" ? "DeepSeek 理解想法" : "关键词规则（无 Key 时也能用）"}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>
              {model?.name || "交易模型"}
              {active ? " · 已启用" : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}
            {!model ? (
              <p className="text-sm text-muted-foreground">生成后会出现可改的卡片。</p>
            ) : (
              <>
                <p className="text-sm text-foreground">{model.summary || "-"}</p>
                {model.notes?.length ? (
                  <ul className="list-disc space-y-1 pl-5 text-xs text-amber-600 dark:text-amber-400">
                    {model.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                ) : null}

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs text-muted-foreground">
                    模拟标的
                    <input
                      className="mt-1 h-9 w-full rounded-none border border-border bg-background px-3 text-sm text-foreground"
                      value={model.symbol}
                      onChange={(e) => setModel({ ...model, symbol: e.target.value })}
                    />
                  </label>
                  <div className="text-xs text-muted-foreground">
                    已启用因子 {enabledCount} 个
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">看什么</div>
                  {model.factors.map((f) => (
                    <label
                      key={f.id}
                      className="flex items-start gap-3 rounded-[3px] border border-border px-3 py-2"
                    >
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={f.enabled}
                        onChange={(e) => patchFactor(f.id, { enabled: e.target.checked })}
                      />
                      <span className="flex-1">
                        <span className="block text-sm text-foreground">
                          {labelOf(catalog, f.id)}
                        </span>
                        <span className="block text-xs text-muted-foreground">
                          {hintOf(catalog, f.id)}
                        </span>
                      </span>
                      <input
                        type="range"
                        min={1}
                        max={100}
                        value={Math.round(f.weight * 100)}
                        disabled={!f.enabled}
                        onChange={(e) =>
                          patchFactor(f.id, { weight: Number(e.target.value) / 100 })
                        }
                      />
                    </label>
                  ))}
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  <label className="text-xs text-muted-foreground">
                    开仓线 {pct(model.entry.moderate_threshold)}%
                    <input
                      type="range"
                      min={2}
                      max={20}
                      className="mt-1 w-full"
                      value={Math.round(model.entry.moderate_threshold * 100)}
                      onChange={(e) =>
                        setModel({
                          ...model,
                          entry: {
                            ...model.entry,
                            moderate_threshold: Number(e.target.value) / 100,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    最大回撤 {pct(model.risk.max_drawdown)}%
                    <input
                      type="range"
                      min={5}
                      max={30}
                      className="mt-1 w-full"
                      value={Math.round(model.risk.max_drawdown * 100)}
                      onChange={(e) =>
                        setModel({
                          ...model,
                          risk: {
                            ...model.risk,
                            max_drawdown: Number(e.target.value) / 100,
                          },
                        })
                      }
                    />
                  </label>
                  <label className="text-xs text-muted-foreground">
                    单票上限 {pct(model.risk.single_stock_limit)}%
                    <input
                      type="range"
                      min={3}
                      max={25}
                      className="mt-1 w-full"
                      value={Math.round(model.risk.single_stock_limit * 100)}
                      onChange={(e) =>
                        setModel({
                          ...model,
                          risk: {
                            ...model.risk,
                            single_stock_limit: Number(e.target.value) / 100,
                          },
                        })
                      }
                    />
                  </label>
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" disabled={busy} onClick={() => void save()}>
                    保存并启用
                  </Button>
                  <Button type="button" disabled={busy} onClick={() => void runPaper()}>
                    跑一次模拟盘
                  </Button>
                </div>
                {runLog ? (
                  <pre className="max-h-48 overflow-auto rounded-[3px] border border-border bg-muted/40 p-3 text-[11px] leading-5 text-muted-foreground">
                    {runLog}
                  </pre>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
