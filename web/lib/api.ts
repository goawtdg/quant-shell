import type {
  AskResponse,
  DecisionsResponse,
  DeskJob,
  DiffChange,
  FactorsResponse,
  JobsListResponse,
  OhlcvBar,
  PositionsResponse,
  RunMeta,
  Snapshot,
  OverviewResponse,
} from "@/types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8766";

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function sendJson<T>(
  path: string,
  method: string,
  body?: unknown
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}${detail ? `: ${detail}` : ""}`);
  }
  return res.json() as Promise<T>;
}

export function fetchOverview(live = false, runsLimit = 40) {
  const q = new URLSearchParams();
  if (live) q.set("live", "true");
  q.set("runs_limit", String(runsLimit));
  const qs = q.toString();
  return getJson<OverviewResponse>(
    `/api/v1/dashboard/overview${qs ? `?${qs}` : ""}`
  );
}

export function fetchSnapshot(live = false) {
  const q = live ? "?live=true" : "";
  return getJson<Snapshot>(`/api/v1/dashboard/snapshot${q}`);
}

export function fetchDecisions(
  tab: string,
  filter: string,
  runId?: string | null
) {
  const q = new URLSearchParams({ tab, filter });
  if (runId) q.set("run_id", runId);
  return getJson<DecisionsResponse>(`/api/v1/decisions?${q}`);
}

export function fetchPositions(live = false) {
  const q = live ? "?live=true" : "";
  return getJson<PositionsResponse>(`/api/v1/positions${q}`);
}

export function fetchRuns() {
  return getJson<{ runs: RunMeta[] }>("/api/v1/runs");
}

export function fetchOhlcv(code: string) {
  return getJson<{ symbol: string; data: OhlcvBar[]; error?: string }>(
    `/api/v1/positions/${code}/ohlcv`
  );
}

export function fetchRunDiff(baseRunId?: string) {
  const q = baseRunId ? `?base_run_id=${encodeURIComponent(baseRunId)}` : "";
  return getJson<{
    latest_run_id?: string;
    previous_run_id?: string;
    changes: DiffChange[];
    generated_at?: string;
  }>(`/api/v1/runs/diff${q}`);
}

export function askAssistant(question: string) {
  return sendJson<AskResponse>("/api/v1/assistant/ask", "POST", { question });
}

export function saveNote(code: string, note: string) {
  return sendJson<{ symbol: string; note: string }>(
    `/api/v1/positions/${code}/note`,
    "PUT",
    { note }
  );
}

export function submitPaperOrder(body: {
  symbol: string;
  action: string;
  quantity: number;
  reason: string;
  confirm?: boolean;
  run_id?: string;
  sleeve?: string;
}) {
  return sendJson<{
    status: string;
    symbol: string;
    action: string;
    quantity: number;
    fill_price: number;
    message: string;
    cash_after?: number;
    equity?: number;
  }>("/api/v1/paper/orders", "POST", { confirm: true, ...body });
}

export function fetchJobs() {
  return getJson<JobsListResponse>("/api/v1/jobs");
}

export function fetchJob(id: string) {
  return getJson<DeskJob>(`/api/v1/jobs/${id}`);
}

export function startJob(
  type: string,
  params: Record<string, unknown> = {},
  confirm = true
) {
  return sendJson<DeskJob>("/api/v1/jobs", "POST", { type, params, confirm });
}

export function cancelJob(id: string) {
  return sendJson<DeskJob>(`/api/v1/jobs/${id}/cancel`, "POST");
}

export function fetchFactors(scope: "etf" | "stock") {
  return getJson<FactorsResponse>(`/api/v1/factors?scope=${scope}`);
}

export function patchFactor(
  scope: "etf" | "stock",
  name: string,
  status: string,
  reason: string
) {
  return sendJson<{
    scope: string;
    name: string;
    status: string;
    previous: string;
    reason: string;
  }>(`/api/v1/factors/${scope}/${name}`, "PATCH", { status, reason });
}

export function createFactor(body: {
  scope: "etf" | "stock";
  name: string;
  expression: string;
  description?: string;
  category?: string;
  weight?: number;
}) {
  return sendJson<{ scope: string; name: string; status: string }>(
    "/api/v1/factors",
    "POST",
    body
  );
}

export function deleteFactor(scope: "etf" | "stock", name: string) {
  return sendJson<{ scope: string; name: string; deleted: boolean }>(
    `/api/v1/factors/${scope}/${name}`,
    "DELETE"
  );
}

export function fetchLinkageReport(runId?: string | null) {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return getJson<import("@/types").LinkageReport>(
    `/api/v1/reports/linkage${q}`
  );
}

export function fetchLinkageReportList(limit = 40) {
  return getJson<import("@/types").LinkageReportListResponse>(
    `/api/v1/reports/linkage/list?limit=${limit}`
  );
}

export function deleteLinkageReport(runId: string) {
  return sendJson<{ run_id: string; deleted: string[]; ok: boolean }>(
    `/api/v1/reports/linkage/${encodeURIComponent(runId)}`,
    "DELETE"
  );
}

export function linkagePdfUrl(runId?: string | null): string {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return `${BASE}/api/v1/reports/linkage.pdf${q}`;
}

export function linkageHtmlUrl(runId?: string | null): string {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  return `${BASE}/api/v1/reports/linkage.html${q}`;
}

/**
 * 下载联动报告 PDF。
 * 用直链 + Content-Disposition，避免 blob 误判 / 立刻 revoke 导致「总是失败」。
 */
export async function downloadLinkagePdf(runId?: string | null): Promise<void> {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const url = `${BASE}/api/v1/reports/linkage.pdf${q}`;

  // 先 HEAD/探测是否可用（部分环境 HEAD 不可用则改 GET 只取前几字节）
  const probe = await fetch(url, { method: "GET", cache: "no-store" });
  if (!probe.ok) {
    const detail = await probe.text().catch(() => "");
    throw new Error(
      `${probe.status} PDF 不可用${detail ? `: ${detail.slice(0, 200)}` : ""}`
    );
  }
  const buf = await probe.arrayBuffer();
  const head = new TextDecoder("ascii").decode(buf.slice(0, 5));
  if (buf.byteLength < 64 || head !== "%PDF-") {
    const text = new TextDecoder("utf-8").decode(buf.slice(0, 200));
    throw new Error(`PDF 无效响应: ${text}`);
  }

  const blob = new Blob([buf], { type: "application/pdf" });
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = `linkage_report_${runId || "latest"}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // 延迟释放，避免 Chromium 还没开始下载就被 revoke
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

export { BASE as API_BASE };

export type ShellPluginsResponse = {
  ok: boolean;
  available: boolean;
  plugins?: Record<string, string | null>;
  reference_installed?: boolean;
  detail?: string;
  narrative?: string;
};

export function fetchShellPlugins() {
  return getJson<ShellPluginsResponse>("/api/v1/shell/plugins");
}

export function fetchShellHealth() {
  return getJson<{
    ok: boolean;
    available: boolean;
    framework?: string | null;
    reference_installed?: boolean;
    detail?: string;
  }>("/api/v1/shell/health");
}

export type StudioFactor = {
  id: string;
  enabled: boolean;
  weight: number;
};

export type StudioModel = {
  name: string;
  idea: string;
  summary: string;
  symbol: string;
  factors: StudioFactor[];
  entry: {
    moderate_threshold: number;
    strong_threshold: number;
    moderate_buy_scale: number;
  };
  risk: {
    max_drawdown: number;
    single_stock_limit: number;
    total_position_limit: number;
  };
  notes: string[];
};

export type StudioCatalogItem = {
  id: string;
  label: string;
  hint: string;
  category: string;
  default_weight: number;
};

export type StudioResponse = {
  ok: boolean;
  available?: boolean;
  active?: boolean;
  compiler?: string;
  saved?: boolean;
  model: StudioModel;
  catalog: StudioCatalogItem[];
  detail?: string;
};

export function fetchStudioModel() {
  return getJson<StudioResponse>("/api/v1/studio/model");
}

export function compileStudioIdea(idea: string) {
  return sendJson<StudioResponse>("/api/v1/studio/compile", "POST", { idea });
}

export function saveStudioModel(model: StudioModel) {
  return sendJson<StudioResponse>("/api/v1/studio/model", "PUT", { model });
}
