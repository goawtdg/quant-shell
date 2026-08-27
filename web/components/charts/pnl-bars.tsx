"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { tooltipStyle, useChartTheme } from "@/lib/chart-theme";
import type { PositionRow } from "@/types";

export function PnlBars({ positions }: { positions: PositionRow[] }) {
  const t = useChartTheme();
  const data = [...positions]
    .sort((a, b) => b.unrealized_pnl_pct - a.unrealized_pnl_pct)
    .map((p) => ({
      symbol: p.symbol,
      pnl: Number((p.unrealized_pnl_pct * 100).toFixed(2)),
    }));

  if (!data.length) {
    return (
      <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">
        暂无浮盈数据
      </div>
    );
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis
            dataKey="symbol"
            tick={{ fill: t.axis, fontSize: 11 }}
            axisLine={{ stroke: t.grid }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: t.axis, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            unit="%"
            width={40}
          />
          <Tooltip
            formatter={(v) => [`${Number(v ?? 0)}%`, "浮盈"]}
            contentStyle={tooltipStyle(t)}
            cursor={{ fill: t.grid, opacity: 0.4 }}
          />
          <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.symbol} fill={d.pnl >= 0 ? t.up : t.down} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
