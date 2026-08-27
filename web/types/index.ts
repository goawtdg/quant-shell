export type ActionCounts = {
  WAIT: number;
  HOLD: number;
  REDUCE: number;
  BUY: number;
  OTHER?: number;
};

export type AlertItem = {
  symbol: string;
  level: string;
  message: string;
};

export type TradeItem = {
  timestamp?: string;
  symbol: string;
  action: string;
  quantity?: number;
  fill_price?: number;
  reason?: string;
  equity?: number;
};

export type Snapshot = {
  equity: number;
  cash: number;
  position_value: number;
  position_pct: number;
  initial_cash: number;
  last_run_at: string;
  run_id?: string;
  action_counts: ActionCounts;
  alerts: AlertItem[];
  recent_trades: TradeItem[];
  price_stale: boolean;
  price_as_of?: string | null;
  equity_change_pct: number | null;
  equity_prev?: number | null;
  sim: boolean;
};

export type DecisionItem = {
  symbol: string;
  name?: string;
  tab?: string;
  asset_type?: string;
  evaluation_mode?: string;
  verdict?: string;
  trade_action?: string;
  execution?: string;
  signal?: number;
  /** L3 机会分（有符号）；展示用绝对值 */
  opportunity?: number;
  quality?: number | null;
  suggested_position?: number | null;
  unrealized_pnl_pct?: number;
  reasons?: string[];
  risk_flags?: string[];
  pe_percentile?: number;
  pe_ttm?: number;
  pe_percentile_source?: string;
  pe_reliable?: boolean;
  pe_fallback?: boolean;
  human_review_required?: boolean;
  pick_rank?: number;
  pick_score?: number;
  entry_eligible?: boolean;
  factor_active?: number;
  factor_disabled?: number;
};

export type DecisionsResponse = {
  items: DecisionItem[];
  run_id?: string;
  generated_at?: string;
  tab: string;
  filter: string;
  is_latest?: boolean;
  action_counts?: ActionCounts;
  error?: string;
};

export type PositionRow = {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  holding_days: number;
  peak_price: number;
  peak_pct: number;
  opened_at?: string;
  last_action?: string;
  last_verdict?: string;
  note?: string;
  weight: number;
};

export type PositionsResponse = {
  positions: PositionRow[];
  cash: number;
  equity: number;
  total_pnl: number;
  total_pnl_pct: number;
  price_stale: boolean;
  price_as_of?: string | null;
  updated_at?: string;
  run_id?: string;
  generated_at?: string;
};

export type RunMeta = {
  run_id: string;
  created_at: string;
  decision_count: number;
  trade_count: number;
  filename: string;
};

export type OverviewResponse = {
  snapshot: Snapshot;
  positions: PositionsResponse;
  runs: RunMeta[];
  generated_at?: string;
};

export type OhlcvBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type AskResponse = {
  answer: string;
  sources: string[];
  generated_at: string;
  error?: string | null;
};

export type DiffChange = {
  symbol?: string;
  tab?: string;
  change: string;
  from_action?: string | null;
  to_action?: string | null;
};

export type JobStatus =
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";

export type DeskJob = {
  id: string;
  type: string;
  lane?: "trade" | "eval" | string;
  params?: Record<string, unknown>;
  command?: string[];
  status: JobStatus | string;
  created_at?: string;
  finished_at?: string | null;
  returncode?: number | null;
  pid?: number | null;
  log_tail?: string;
  error?: string;
};

export type JobsListResponse = {
  lanes: {
    trade: DeskJob | null;
    eval: DeskJob | null;
  };
  recent: DeskJob[];
};

export type FactorItem = {
  name: string;
  category: string;
  description: string;
  weight: number;
  effective_weight: number;
  status: "active" | "degraded" | "disabled" | string;
  source?: "builtin" | "plugin" | string;
  expression?: string;
};

export type FactorsResponse = {
  scope: string;
  counts: { active: number; degraded: number; disabled: number };
  factors: FactorItem[];
  meta?: Record<string, unknown>;
};

export type LinkageReportAction = {
  symbol: string;
  tab: string;
  verdict?: string;
  trade_action?: string;
  execution?: string;
  trade_sleeve?: string;
  sleeve_reason?: string;
  decision_logic?: {
    reasoning_chain?: string[];
    policy_path?: string;
    signal?: { confidence?: number; direction?: string };
    gates?: Record<string, unknown>;
    risk_flags?: string[];
    valuation?: Record<string, unknown>;
  };
  intel?: {
    available?: boolean;
    source_hint?: string;
    analyst_summary?: string;
    analyst_action?: string;
    analyst_confidence?: number;
    cross_validation?: number;
    key_events?: string[];
    alerts_for_symbol?: { level: string; message: string }[];
  };
};

export type LinkageReport = {
  schema_version?: string;
  run_id?: string;
  generated_at?: string;
  action_summary?: Record<string, number>;
  factor_health?: string;
  equity_ok?: boolean;
  equity_snapshot?: {
    equity?: number;
    cash?: number;
    position_value?: number;
  } | null;
  intel_overview?: {
    intel_ran?: boolean;
    source_hint?: string;
    alert_count?: number;
    stock_intel_symbols?: string[];
  };
  alerts?: { symbol: string; level: string; message: string }[];
  actions?: LinkageReportAction[];
};

export type LinkageReportListItem = {
  run_id: string;
  generated_at?: string;
  label: string;
  has_pdf?: boolean;
  has_html?: boolean;
  buy?: number;
  reduce?: number;
  hold?: number;
  wait?: number;
};

export type LinkageReportListResponse = {
  items: LinkageReportListItem[];
  count: number;
};
