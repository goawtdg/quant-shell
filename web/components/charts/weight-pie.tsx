"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { tooltipStyle, useChartTheme } from "@/lib/chart-theme";
import type { PositionRow } from "@/types";

export function WeightPie({
  positions,
  cash,
  equity,
}: {
  positions: PositionRow[];
  cash: number;
  equity: number;
}) {
  const t = useChartTheme();
  const data = [
    ...positions.map((p) => ({
      name: p.symbol,
      value: Math.max(0, p.market_value),
    })),
    { name: "现金", value: Math.max(0, cash) },
  ].filter((d) => d.value > 0);

  if (!data.length || equity <= 0) {
    return (
      <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">
        暂无持仓权重
      </div>
    );
  }

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" outerRadius={80}>
            {data.map((d, i) => (
              <Cell key={d.name} fill={t.series[i % t.series.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(v) => {
              const n = Number(v ?? 0);
              return `${((n / equity) * 100).toFixed(1)}% / ${n.toFixed(0)}`;
            }}
            contentStyle={tooltipStyle(t)}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
