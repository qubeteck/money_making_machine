/* Shared API contracts for the Money Machine dashboard. */

export type Direction = "long" | "short";
export type Tone =
  | "emerald"
  | "rose"
  | "amber"
  | "sky"
  | "violet"
  | "slate"
  | "blue";

export interface EquitySeries {
  labels: string[];
  values: number[];
}

export interface BotSettings {
  symbols: string;
  trend_timeframe: string;
  structure_timeframe: string;
  entry_timeframe: string;
  risk_pct: number;
  max_daily_loss_pct: number;
  max_open_positions: number;
  min_score: number;
  leverage: number;
  starting_balance: number;
  taker_fee_pct: number;
  slippage_pct: number;
  paper_mode: boolean;
  paused: boolean;
  session_filter: boolean;
  session_start_utc: number;
  session_end_utc: number;
  telegram_chat_id: string;
  pricing_tier?: string;
  last_scan_at?: string | null;
  updated_at?: string;
}

export interface DashboardStatus {
  mode: "PAPER" | "LIVE";
  paper_mode: boolean;
  paused: boolean;
  equity: number;
  balance: number;
  open_pnl: number;
  today_pnl: number;
  today_pnl_pct: number;
  win_rate: number;
  trades: number;
  wins: number;
  losses: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_r: number;
  open_positions: number;
  max_open_positions: number;
  signals_today: number;
  last_scan_at: string | null;
  symbols: string[];
  entry_timeframe: string;
}

export interface Position {
  id: number;
  symbol: string;
  side: Direction;
  qty: number;
  entry: number;
  current: number;
  stop: number;
  take_profit: number;
  unrealized: number;
  unrealized_pct: number;
  mode: string;
  leverage: number;
  risk: string;
  opened_at: string | null;
}

export interface Scan {
  id: number;
  created_at: string | null;
  symbol: string;
  price: number;
  trend: string;
  structure: string;
  score: number;
  status: string;
  reason: string;
}

export interface Signal {
  id: number;
  created_at: string;
  symbol: string;
  side: Direction;
  score: number;
  entry: number;
  stop: number;
  take_profit: number;
  rr: number;
  status: string;
  reasons: string[];
  components: Record<string, number>;
  reject_reason: string;
  htf_trend: string;
  trend_timeframe: string;
  structure_timeframe: string;
  entry_timeframe: string;
}

export interface LogEntry {
  id?: number;
  created_at: string;
  level: string;
  message: string;
}

export interface DailyBacktestGate {
  enabled: boolean;
  ready: boolean;
  running: boolean;
  signature: string;
  days: number;
  symbols: string[];
  checked_at: string;
  completed_at: string | null;
  last_error_at: string | null;
  reason: string;
}

export interface DashboardData {
  status: DashboardStatus;
  settings: BotSettings;
  daily_backtest?: DailyBacktestGate;
  equity: EquitySeries;
  positions: Position[];
  scans: Scan[];
  signals: Signal[];
  logs: LogEntry[];
}

export interface TradeRow {
  id: number;
  signal_id: number | null;
  symbol: string;
  side: Direction;
  qty: number;
  entry: number;
  current: number;
  stop: number;
  take_profit: number;
  exit_price: number | null;
  pnl: number;
  unrealized: number;
  fees: number;
  r_multiple: number;
  status: "open" | "closed";
  mode: string;
  leverage: number;
  exit_reason: string;
  opened_at: string | null;
  closed_at: string | null;
  notes: string;
}

export interface TradeStats {
  net_pnl: number;
  today_pnl: number;
  win_rate: number;
  wins: number;
  losses: number;
  trades: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_r: number;
  open_positions: number;
  starting_balance: number;
}

export interface TradesResponse {
  trades: TradeRow[];
  stats: TradeStats;
  filters: { status: string; mode: string; symbol: string };
  limit: number;
}

export interface ScansResponse {
  scans: Scan[];
}

export interface BacktestRequest {
  symbol: string;
  days: number;
  starting_balance: number;
  risk_pct: number;
  min_score: number;
  leverage: number;
  fee_pct: number;
  slippage_pct: number;
}

export interface BacktestTrade {
  side: Direction;
  entry: number;
  exit: number;
  qty: number;
  pnl: number;
  r_multiple: number;
  stop: number;
  take_profit: number;
  opened_at: string | null;
  closed_at: string | null;
  reason: string;
  score: number;
}

export interface BacktestResult {
  symbol: string;
  days: number;
  starting_balance: number;
  final_equity: number;
  net_pnl: number;
  return_pct: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown_pct: number;
  avg_r: number;
  expectancy: number;
  candles: number;
  data_start: string | null;
  data_end: string | null;
  curve: [string, number][];
  trade_list: BacktestTrade[];
  warnings: string[];
}

export interface JobRun {
  id: number;
  job_name: string;
  started_at: string;
  finished_at?: string | null;
  status: string;
  duration_seconds: number;
  message: string;
  attempts: number;
}

export interface SystemInfo {
  version: string;
  environment: string;
  mode: string;
  paper_mode: boolean;
  paused: boolean;
  live_allowed: boolean;
  mexc_configured: boolean;
  telegram_configured: boolean;
  dashboard_auth: boolean;
  api_token_configured: boolean;
  database: string;
  scan_interval_seconds: number;
  sse_interval_seconds: number;
  ws_interval_seconds: number;
  risk_pct: number;
  symbols: string[];
  daily_backtest?: DailyBacktestGate;
  jobs: JobRun[];
}

export interface Metrics {
  version: string;
  environment: string;
  uptime_seconds: number | null;
  scheduler_running: boolean;
  mode: string;
  paused: boolean;
  equity: number;
  balance: number;
  open_pnl: number;
  trades_total: number;
  trades_open: number;
  trades_closed: number;
  signals_24h: number;
  jobs_total: number;
  jobs_errors_24h: number;
  bot_errors_24h: number;
}

export interface Ticker {
  symbol: string;
  price: number;
  trend: string;
  structure: string;
  score: number;
  status: string;
  updated_at: string | null;
}

export interface TickersResponse {
  tickers: Ticker[];
  updated_at: string;
}

export interface MeInfo {
  authenticated: boolean;
  auth_required: boolean;
  method: string;
  subject: string | null;
  username: string | null;
  expires_at: string | null;
  app: string;
  version: string;
  environment: string;
  mode: string;
  paused: boolean;
  symbols: string[];
  permissions: string[];
}

export interface AuthMe {
  authenticated: boolean;
  user: {
    id: number;
    username: string;
    email: string | null;
    is_active: boolean;
    is_superuser: boolean;
    telegram_chat_id: string | null;
    telegram_verified: boolean;
  } | null;
  method?: string;
  settings?: BotSettings | null;
}

export interface AuthProviders {
  telegram: boolean;
  telegram_widget: boolean;
  telegram_bot_username: string;
  google: boolean;
  auth_required: boolean;
  frontend: string;
}

/* --- Command center ------------------------------------------------------ */

export interface AdvancedOverview {
  mode: "PAPER" | "LIVE";
  paused: boolean;
  updated_at: string;
  balance: number;
  equity: number;
  open_pnl: number;
  daily_pnl: number;
  daily_pnl_pct: number;
  win_rate: number;
  trades: number;
  open_positions: number;
  signals_today: number;
  drawdown: number;
  symbols: string[];
  entry_timeframe: string;
}

export interface AdvancedMarket {
  symbol: string;
  name: string;
  price: number;
  trend: string;
  structure: string;
  score: number;
  status: string;
  updated_at: string | null;
}

export interface AdvancedPosition {
  id: number;
  symbol: string;
  side: "BUY" | "SELL";
  entry: number;
  current: number;
  sl: number;
  tp: number;
  qty: number;
  pnl: number;
  risk: string;
  mode: string;
  opened_at: string | null;
}

export interface AdvancedSignal {
  time: string;
  created_at: string | null;
  symbol: string;
  side: "BUY" | "SELL";
  strategy: string;
  tf: string;
  confidence: number;
  status: string;
  entry: number;
  stop: number;
  take_profit: number;
  rr: number;
}

export interface DashboardSnapshot {
  overview: AdvancedOverview;
  markets: AdvancedMarket[];
  positions: AdvancedPosition[];
  signals: AdvancedSignal[];
  allocation: EquitySeries;
  server_time: string;
  metadata?: {
    generated_at: string;
    execution_time_ms: number;
    database_queries: number;
    cache_status: string;
  };
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  symbol: string;
  timeframe: string;
  candles: Candle[];
}

export interface WsTokenResponse {
  token: string;
  token_type: string;
  expires_in: number;
  ws_url: string;
  auth_required: boolean;
}

export interface TickerMessage {
  type?: string;
  tickers?: Ticker[];
  updated_at?: string;
  interval_seconds?: number;
  client_id?: string;
  timestamp?: string;
}

export interface ScanTriggerResult {
  ok: boolean;
  status: string;
  result: {
    skipped?: boolean;
    reason?: string;
    evaluated?: number;
    opened?: number;
    closed?: number;
    errors?: string[];
  };
}

export interface ActionResponse {
  ok: boolean;
  message: string;
  closed?: number;
}
