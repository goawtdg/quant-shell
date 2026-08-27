"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { ActionBadge, TrustBadge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ManualOrderForm } from "@/components/decisions/manual-order-form";
import { formatPct } from "@/lib/format";
import type { DecisionItem } from "@/types";

function needsManualQueue(item: DecisionItem): boolean {
  if (item.human_review_required) return true;
  const action = (item.trade_action || "").toUpperCase();
  const exec = (item.execution || "").toLowerCase();
  return action === "WAIT" && exec !== "filled";
}

export function DecisionCard({
  item,
  runId,
  isLatest = true,
  onOrderDone,
}: {
  item: DecisionItem;
  runId?: string;
  isLatest?: boolean;
  onOrderDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const oppRaw =
    item.opportunity !== undefined && item.opportunity !== null
      ? Number(item.opportunity)
      : Number(item.signal || 0);
  const oppAbs = Math.abs(Number.isFinite(oppRaw) ? oppRaw : 0);
  const signalPct = Math.round(Math.min(1, Math.max(0, oppAbs)) * 100);
  const pnl = item.unrealized_pnl_pct ?? 0;
  const pe = item.pe_percentile;
  const showManual = needsManualQueue(item);

  return (
    <Card>
      <CardContent className="p-4">
        <button
          type="button"
          className="flex w-full items-start justify-between gap-3 text-left"
          onClick={() => setOpen((v) => !v)}
        >
          <div className="min-w-0 flex-1 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-base font-medium text-foreground">
                {item.symbol}
              </span>
              {item.name ? (
                <span className="text-sm text-muted-foreground">{item.name}</span>
              ) : null}
              {item.verdict ? (
                <span className="rounded-[3px] bg-muted px-2 py-0.5 text-xs text-foreground">
                  {item.verdict}
                </span>
              ) : null}
              <ActionBadge action={item.trade_action} />
              {item.execution === "filled" ? (
                <span className="rounded-[3px] border border-ember/40 bg-ember/10 px-2 py-0.5 font-mono text-xs text-ember">
                  filled
                </span>
              ) : null}
              {item.human_review_required ? (
                <span className="rounded-[3px] border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">
                  需人审
                </span>
              ) : null}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <div className="mb-1 text-xs text-subtle">机会</div>
                <div className="font-mono text-sm text-foreground">
                  {oppAbs.toFixed(2)}
                  <span className="ml-1 text-xs text-subtle">({signalPct}%)</span>
                </div>
                <div
                  className="mt-1 h-[3px] bg-ember"
                  style={{ width: `${signalPct}%` }}
                />
              </div>
              <div>
                <div className="mb-1 flex items-center gap-2 text-xs text-subtle">
                  PE 分位
                  <TrustBadge
                    reliable={item.pe_reliable}
                    fallback={item.pe_fallback}
                  />
                </div>
                <div className="font-mono text-sm text-foreground">
                  {pe == null ? "-" : `${Math.round(pe * 100)}%`}
                  {item.pe_ttm != null ? (
                    <span className="ml-2 text-subtle">
                      TTM {item.pe_ttm.toFixed(1)}
                    </span>
                  ) : null}
                </div>
              </div>
              <div>
                <div className="mb-1 text-xs text-subtle">浮盈</div>
                <div
                  className={`font-mono text-sm ${
                    pnl > 0
                      ? "text-emerald-600 dark:text-emerald-400"
                      : pnl < 0
                        ? "text-red-600 dark:text-red-400"
                        : "text-foreground"
                  }`}
                >
                  {formatPct(pnl)}
                </div>
              </div>
            </div>
          </div>
          {open ? (
            <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-subtle" strokeWidth={1.5} />
          ) : (
            <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-subtle" strokeWidth={1.5} />
          )}
        </button>
        {open ? (
          <div className="mt-4 space-y-3 border-t border-border pt-3">
            <div>
              <div className="mb-2 text-xs text-subtle">Reasons</div>
              <ul className="space-y-1.5">
                {(item.reasons || []).map((r) => (
                  <li
                    key={r}
                    className="flex gap-2 text-sm text-foreground before:mt-2 before:h-1 before:w-1 before:shrink-0 before:rounded-full before:bg-subtle"
                  >
                    {r}
                  </li>
                ))}
                {!item.reasons?.length ? (
                  <li className="text-sm text-muted-foreground">无</li>
                ) : null}
              </ul>
            </div>
            {(item.risk_flags || []).length ? (
              <div className="flex flex-wrap gap-1.5">
                {item.risk_flags!.map((f) => (
                  <span
                    key={f}
                    className="rounded-[3px] border border-red-400/30 bg-red-500/10 px-2 py-0.5 text-xs text-red-600 dark:text-red-400"
                  >
                    {f}
                  </span>
                ))}
              </div>
            ) : null}
            {showManual ? (
              <ManualOrderForm
                defaultSymbol={item.symbol}
                runId={runId}
                disabled={!isLatest}
                onDone={onOrderDone}
              />
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
