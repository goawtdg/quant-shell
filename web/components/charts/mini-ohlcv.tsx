"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { OhlcvBar } from "@/types";
import { tooltipStyle, useChartTheme } from "@/lib/chart-theme";

export function MiniOhlcv({ data }: { data: OhlcvBar[] }) {
  const t = useChartTheme();
  if (!data.length) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        无 K 线缓存
      </div>
    );
  }
  return (
    <div className="h-40 w-full">
      <ResponsiveContainer>
        <LineChart data={data}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis
            dataKey="date"
            hide
          />
          <YAxis
            domain={["auto", "auto"]}
            width={48}
            tick={{ fill: t.axis, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip contentStyle={tooltipStyle(t)} />
          <Line
            type="monotone"
            dataKey="close"
            stroke={t.ember}
            dot={false}
            strokeWidth={1.5}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
