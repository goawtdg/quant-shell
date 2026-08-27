export function formatMoney(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "-";
  return n.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatPct(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "-";
  const sign = n > 0 ? "+" : "";
  return `${sign}${(n * 100).toFixed(digits)}%`;
}

export function formatTs(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace("T", " ");
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${h}:${min}`;
}

export function actionTone(
  action: string | null | undefined
): "buy" | "reduce" | "hold" | "wait" | "alert" {
  const a = (action || "").toUpperCase();
  if (a === "BUY") return "buy";
  if (a === "REDUCE" || a === "SELL") return "reduce";
  if (a === "HOLD") return "hold";
  if (a.includes("ALERT") || a === "ACTION") return "alert";
  return "wait";
}
