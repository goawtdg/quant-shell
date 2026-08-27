"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  Briefcase,
  Bot,
  Play,
  Puzzle,
  FileText,
  Lightbulb,
} from "lucide-react";
import { cn } from "@/lib/utils";

const decisionLinks = [
  { href: "/", label: "总览", icon: LayoutDashboard },
  { href: "/report", label: "联动报告", icon: FileText },
  { href: "/decisions", label: "决策板", icon: ListChecks },
  { href: "/positions", label: "持仓", icon: Briefcase },
  { href: "/assistant", label: "AI 助手", icon: Bot },
];

const runLinks = [{ href: "/jobs", label: "任务中心", icon: Play }];

const strategyLinks = [
  { href: "/studio", label: "交易想法", icon: Lightbulb },
  { href: "/strategies", label: "因子插件", icon: Puzzle },
];

function NavGroup({
  title,
  links,
  pathname,
}: {
  title: string;
  links: { href: string; label: string; icon: React.ComponentType<{ className?: string; strokeWidth?: number }> }[];
  pathname: string;
}) {
  return (
    <div className="mb-5">
      <div className="mb-1.5 px-3 text-[11px] text-subtle">{title}</div>
      <nav className="flex flex-col gap-0.5">
        {links.map(({ href, label, icon: Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-full px-3 py-1.5 text-sm tracking-tight transition-colors",
                active
                  ? "border border-border bg-card text-foreground"
                  : "border border-transparent text-muted-foreground hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" strokeWidth={1.5} />
              {label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-border bg-muted px-3 py-5">
      <div className="mb-7 px-3">
        <div className="text-[15px] tracking-tight text-foreground">
          quant-shell
        </div>
        <div className="mt-0.5 text-xs text-subtle">模拟盘决策台</div>
      </div>
      <NavGroup title="决策" links={decisionLinks} pathname={pathname} />
      <NavGroup title="运行" links={runLinks} pathname={pathname} />
      <NavGroup title="策略" links={strategyLinks} pathname={pathname} />
    </aside>
  );
}
