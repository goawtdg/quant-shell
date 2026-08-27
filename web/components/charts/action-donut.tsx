"use client";

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { tooltipStyle, useChartTheme } from "@/lib/chart-theme";
import type { ActionCounts } from "@/types";

export function ActionDonut({ counts }: { counts: ActionCounts }) {
  const t = useChartTheme();
  const data = (["WAIT", "HOLD", "REDUCE", "BUY"] as const)
    .map((k) => ({ name: k, value: counts[k] || 0 }))
    .filter((d) => d.value > 0);
  if (!data.length) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
        暂无动作分布
      </div>
    );
  }
  return (
    <div className="h-48 w-full">
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={48}
            outerRadius={72}
            paddingAngle={2}
          >
            {data.map((d) => (
              <Cell key={d.name} fill={t.donut[d.name] || t.axis} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle(t)} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
