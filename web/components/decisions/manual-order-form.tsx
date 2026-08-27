"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { submitPaperOrder } from "@/lib/api";

type Props = {
  defaultSymbol: string;
  runId?: string;
  disabled?: boolean;
  onDone?: () => void;
};

const ACTIONS = ["BUY", "REDUCE", "EXIT"] as const;

export function ManualOrderForm({
  defaultSymbol,
  runId,
  disabled,
  onDone,
}: Props) {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("BUY");
  const [quantity, setQuantity] = useState("100");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const out = await submitPaperOrder({
        symbol: symbol.trim(),
        action,
        quantity: Number(quantity),
        reason: reason.trim(),
        confirm: true,
        run_id: runId || "",
      });
      setMsg(`${out.status}: ${out.message}`);
      onDone?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "下单失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-[3px] border border-amber-500/30 bg-amber-500/5 p-3">
      <div className="text-xs font-medium text-amber-600 dark:text-amber-400">
        人工覆盖（模拟盘）
      </div>
      <div className="grid gap-2 sm:grid-cols-4">
        <input
          className="h-9 rounded-none border border-border bg-background px-2 font-mono text-sm"
          value={symbol}
          disabled={disabled || busy}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="600183"
          maxLength={6}
        />
        <select
          className="h-9 rounded-none border border-border bg-background px-2 text-sm"
          value={action}
          disabled={disabled || busy}
          onChange={(e) => setAction(e.target.value as (typeof ACTIONS)[number])}
        >
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <input
          className="h-9 rounded-none border border-border bg-background px-2 font-mono text-sm"
          value={quantity}
          disabled={disabled || busy}
          onChange={(e) => setQuantity(e.target.value)}
          placeholder="股数"
          inputMode="numeric"
        />
        <Button
          type="button"
          size="sm"
          className="h-9"
          disabled={disabled || busy || !reason.trim()}
          onClick={() => void submit()}
        >
          {busy ? "提交中…" : "确认下单"}
        </Button>
      </div>
      <input
        className="h-9 w-full rounded-none border border-border bg-background px-2 text-sm"
        value={reason}
        disabled={disabled || busy}
        onChange={(e) => setReason(e.target.value)}
        placeholder="理由（必填）"
      />
      {disabled ? (
        <p className="text-xs text-muted-foreground">历史 run 只读，不可下单</p>
      ) : null}
      {msg ? <p className="text-xs text-emerald-600 dark:text-emerald-400">{msg}</p> : null}
      {err ? <p className="text-xs text-red-600 dark:text-red-400">{err}</p> : null}
    </div>
  );
}
