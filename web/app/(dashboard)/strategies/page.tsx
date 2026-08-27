"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/topbar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  createFactor,
  deleteFactor,
  fetchFactors,
  fetchShellPlugins,
  patchFactor,
} from "@/lib/api";
import type { FactorItem, FactorsResponse } from "@/types";
import type { ShellPluginsResponse } from "@/lib/api";

function StatusDot({ status }: { status: string }) {
  const color =
    status === "active"
      ? "bg-emerald-500 dark:bg-emerald-400"
      : status === "degraded"
        ? "bg-amber-500 dark:bg-amber-400"
        : "bg-slate-400";
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${color}`} />;
}

export default function StrategiesPage() {
  const [scope, setScope] = useState<"etf" | "stock">("etf");
  const [data, setData] = useState<FactorsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openDesc, setOpenDesc] = useState<string | null>(null);

  const [edit, setEdit] = useState<null | {
    factor: FactorItem;
    status: string;
    reason: string;
  }>(null);
  const [saving, setSaving] = useState(false);

  const [newName, setNewName] = useState("");
  const [newExpr, setNewExpr] = useState("");
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [shell, setShell] = useState<ShellPluginsResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchFactors(scope));
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [scope]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void fetchShellPlugins()
      .then(setShell)
      .catch(() =>
        setShell({
          ok: false,
          available: false,
          detail: "shell API 不可用",
        })
      );
  }, []);

  const grouped = useMemo(() => {
    const map = new Map<string, FactorItem[]>();
    for (const f of data?.factors || []) {
      const list = map.get(f.category) || [];
      list.push(f);
      map.set(f.category, list);
    }
    return [...map.entries()];
  }, [data]);

  async function onCreate() {
    setCreating(true);
    setError(null);
    try {
      const name =
        newName.trim() ||
        `user_${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`;
      await createFactor({
        scope,
        name,
        expression: newExpr.trim(),
      });
      setNewName("");
      setNewExpr("");
      setMessage(`已添加插件因子 ${name}（默认 disabled）`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "添加失败");
    } finally {
      setCreating(false);
    }
  }

  async function onDeletePlugin(name: string) {
    if (!window.confirm(`删除插件因子 ${name}？`)) return;
    setError(null);
    try {
      await deleteFactor(scope, name);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "删除失败");
    }
  }

  async function onSave() {
    if (!edit) return;
    setSaving(true);
    setError(null);
    try {
      await patchFactor(scope, edit.factor.name, edit.status, edit.reason);
      setEdit(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Topbar onRefresh={load} loading={loading} />
      <main className="space-y-6 p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-normal tracking-tight">因子插件</h1>
            <p className="mt-1 text-xs text-subtle">
              初始化为空。交易想法里启用的菜谱会出现在这里；也可粘贴表达式添加插件因子。
              更推荐到「交易想法」改模型。
            </p>
          </div>
          <Link href="/studio" className="text-sm text-ember hover:underline">
            去交易想法 →
          </Link>
        </div>

        {error ? (
          <Card>
            <CardContent className="p-4 text-sm text-red-600 dark:text-red-400">{error}</CardContent>
          </Card>
        ) : null}
        {message ? (
          <Card>
            <CardContent className="p-4 text-sm text-emerald-600 dark:text-emerald-400">{message}</CardContent>
          </Card>
        ) : null}

        {shell ? (
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">quant-shell 插件</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 font-mono text-[11px] text-muted-foreground">
              <p>
                available={shell.available ? "true" : "false"}
                {shell.reference_installed != null
                  ? ` · reference=${shell.reference_installed ? "on" : "off"}`
                  : ""}
              </p>
              {shell.available && shell.plugins ? (
                <>
                  <p>strategy={shell.plugins.strategy_module || "-"}</p>
                  <p>factor={shell.plugins.factor_module || "-"}</p>
                  <p>studio={shell.plugins.studio_model || "-"}</p>
                </>
              ) : (
                <p>{shell.detail || "Desk API 未就绪"}</p>
              )}
            </CardContent>
          </Card>
        ) : null}

        <Tabs value={scope} onValueChange={(v: string) => setScope(v as "etf" | "stock")}>
          <TabsList>
            <TabsTrigger value="etf">ETF</TabsTrigger>
            <TabsTrigger value="stock">个股</TabsTrigger>
          </TabsList>
          <TabsContent value={scope} className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">添加表达式插件</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <input
                  className="h-9 rounded-none border border-border bg-background px-3 font-mono text-sm"
                  placeholder="name (可选)"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                />
                <input
                  className="h-9 min-w-[240px] flex-1 rounded-none border border-border bg-background px-3 font-mono text-sm"
                  placeholder="pct_change(close, 20)"
                  value={newExpr}
                  onChange={(e) => setNewExpr(e.target.value)}
                />
                <Button
                  disabled={creating || !newExpr.trim()}
                  onClick={() => void onCreate()}
                >
                  {creating ? "添加中…" : "添加"}
                </Button>
              </CardContent>
            </Card>

            {loading ? (
              <Skeleton className="h-40 w-full" />
            ) : !grouped.length ? (
              <Card>
                <CardContent className="p-6 text-sm text-muted-foreground">
                  尚无因子（初始化空系统）。去「交易想法」生成模型，或上方添加表达式。
                </CardContent>
              </Card>
            ) : (
              grouped.map(([category, factors]) => (
                <Card key={category}>
                  <CardHeader>
                    <CardTitle className="text-sm">{category}</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {factors.map((f) => (
                      <div
                        key={f.name}
                        className="flex flex-wrap items-center gap-3 rounded-[3px] border border-border px-3 py-2 text-sm"
                      >
                        <StatusDot status={f.status} />
                        <button
                          type="button"
                          className="font-mono text-left hover:underline"
                          onClick={() =>
                            setOpenDesc(openDesc === f.name ? null : f.name)
                          }
                        >
                          {f.name}
                        </button>
                        <span className="text-xs text-muted-foreground">{f.source}</span>
                        <span className="font-mono text-xs text-muted-foreground">
                          w={f.weight}
                        </span>
                        <span className="ml-auto flex gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              setEdit({
                                factor: f,
                                status: f.status,
                                reason: "",
                              })
                            }
                          >
                            改状态
                          </Button>
                          {f.source === "plugin" ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void onDeletePlugin(f.name)}
                            >
                              删除
                            </Button>
                          ) : null}
                        </span>
                        {openDesc === f.name ? (
                          <p className="w-full text-xs text-muted-foreground">
                            {f.description}
                            {f.expression ? ` · ${f.expression}` : ""}
                          </p>
                        ) : null}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))
            )}
          </TabsContent>
        </Tabs>
      </main>

      <Dialog open={!!edit} onClose={() => setEdit(null)} title="修改因子状态">
        {edit ? (
          <div className="space-y-3">
            <p className="text-sm">
              {edit.factor.name}: {edit.factor.status} → {edit.status}
            </p>
            <select
              className="h-9 w-full rounded-none border border-border bg-background px-2 text-sm"
              value={edit.status}
              onChange={(e) => setEdit({ ...edit, status: e.target.value })}
            >
              <option value="active">active</option>
              <option value="degraded">degraded</option>
              <option value="disabled">disabled</option>
            </select>
            <input
              className="h-9 w-full rounded-none border border-border bg-background px-3 text-sm"
              placeholder="原因（必填）"
              value={edit.reason}
              onChange={(e) => setEdit({ ...edit, reason: e.target.value })}
            />
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEdit(null)}>
                取消
              </Button>
              <Button
                disabled={saving || !edit.reason.trim()}
                onClick={() => void onSave()}
              >
                {saving ? "保存中…" : "保存"}
              </Button>
            </div>
          </div>
        ) : null}
      </Dialog>
    </>
  );
}
