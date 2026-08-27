"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  if (!mounted) {
    return (
      <Button variant="outline" size="icon" aria-label="切换主题" disabled>
        <Sun className="h-4 w-4" />
      </Button>
    );
  }
  const dark = theme === "dark";
  return (
    <Button
      variant="outline"
      size="icon"
      aria-label="切换主题"
      onClick={() => setTheme(dark ? "light" : "dark")}
      title={dark ? "切换亮色" : "切换暗色"}
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
