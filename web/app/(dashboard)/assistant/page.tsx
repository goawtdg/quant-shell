"use client";

import { useState } from "react";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { askAssistant } from "@/lib/api";
import { formatTs } from "@/lib/format";

const PRESETS = [
  "当前有没有持仓？",
  "最近一次 linkage 结论是什么？",
  "为什么还没下单？",
  "怎么从交易想法开始第一次跑模拟盘？",
];

type Msg = {
  role: "user" | "assistant";
  content: string;
  generatedAt?: string;
};

export default function AssistantPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [asOf, setAsOf] = useState<string | undefined>();

  async function send(q: string) {
    const question = q.trim();
    if (!question || loading) return;
    setMessages((m) => [...m, { role: "user", content: question }]);
    setInput("");
    setLoading(true);
    try {
      const res = await askAssistant(question);
      setAsOf(res.generated_at);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          generatedAt: res.generated_at,
        },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `请求失败：${e instanceof Error ? e.message : e}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <Topbar asOf={asOf} loading={loading} />
      <main className="grid min-h-[calc(100vh-3.5rem)] gap-4 p-6 lg:grid-cols-[240px_1fr]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>预置问题</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                className="w-full rounded-[3px] border border-border px-3 py-2 text-left text-sm text-foreground hover:bg-muted"
                onClick={() => void send(p)}
              >
                {p}
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="flex min-h-[520px] flex-col">
          <CardHeader>
            <CardTitle>对话</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col gap-3">
            <div className="flex-1 space-y-3 overflow-y-auto rounded-[3px] border border-border bg-muted/40 p-3">
              {!messages.length ? (
                <p className="text-sm text-muted-foreground">
                  基于最新 linkage / portfolio / alerts 缓存回答，不会触发交易。
                </p>
              ) : null}
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={
                    m.role === "user"
                      ? "ml-8 rounded-[3px] bg-muted px-3 py-2 text-sm"
                      : "mr-8 rounded-[3px] border border-border px-3 py-2 text-sm whitespace-pre-wrap"
                  }
                >
                  {m.content}
                  {m.role === "assistant" && m.generatedAt ? (
                    <div className="mt-2 text-[11px] text-muted-foreground">
                      基于 {formatTs(m.generatedAt)} 缓存数据回答
                    </div>
                  ) : null}
                </div>
              ))}
              {loading ? (
                <div className="text-sm text-muted-foreground">思考中…</div>
              ) : null}
            </div>
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void send(input);
              }}
            >
              <input
                className="h-10 flex-1 rounded-none border border-border bg-background px-3 text-sm text-foreground"
                placeholder="询问本轮决策、持仓或止盈依据…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
              <Button type="submit" disabled={loading}>
                发送
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
