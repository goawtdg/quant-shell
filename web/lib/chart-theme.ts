"use client";

import { useTheme } from "next-themes";

/*
  图表值层：Ventriloc 暖纸天文台的中性色阶 + 一枚余烬橙。
  涨跌为数据语义色（emerald / red），其余一律无彩。
*/

export type ChartTheme = {
  grid: string;
  axis: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
  ember: string;
  brass: string;
  ink: string;
  up: string;
  down: string;
  series: string[];
  donut: Record<string, string>;
};

const LIGHT: ChartTheme = {
  grid: "#e8e8e8",
  axis: "#828282",
  tooltipBg: "#ffffff",
  tooltipBorder: "#e8e8e8",
  tooltipText: "#202020",
  ember: "#ff682c",
  brass: "#816729",
  ink: "#202020",
  up: "#059669",
  down: "#dc2626",
  series: ["#ff682c", "#202020", "#816729", "#828282", "#c9c9c9", "#4d4d4d", "#ebe6dd"],
  donut: { WAIT: "#c9c9c9", HOLD: "#202020", REDUCE: "#816729", BUY: "#ff682c" },
};

const DARK: ChartTheme = {
  grid: "#333130",
  axis: "#8f8a83",
  tooltipBg: "#1a1917",
  tooltipBorder: "#333130",
  tooltipText: "#eae6de",
  ember: "#ff682c",
  brass: "#b99a55",
  ink: "#eae6de",
  up: "#34d399",
  down: "#f87171",
  series: ["#ff682c", "#eae6de", "#b99a55", "#8f8a83", "#5a5650", "#c2bcb2", "#3a3835"],
  donut: { WAIT: "#5a5650", HOLD: "#eae6de", REDUCE: "#b99a55", BUY: "#ff682c" },
};

export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? DARK : LIGHT;
}

export function tooltipStyle(t: ChartTheme): React.CSSProperties {
  return {
    background: t.tooltipBg,
    border: `1px solid ${t.tooltipBorder}`,
    borderRadius: 3,
    color: t.tooltipText,
    fontSize: 12,
  };
}
