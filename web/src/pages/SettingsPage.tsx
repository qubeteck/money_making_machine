import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  ExternalLink,
  Gauge,
  KeyRound,
  Layers,
  ListChecks,
  Pause,
  Play,
  RefreshCw,
  Save,
  Server,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
  Wallet,
} from "lucide-react";
import { apiGet, apiPost, apiPut, errorMessage } from "../lib/api";
import {
  cn,
  fmtDateTime,
  fmtFullDateTime,
  fmtPct,
  humanize,
} from "../lib/format";
import { useDocumentTitle, usePolling } from "../lib/hooks";
import type {
  ActionResponse,
  BotSettings,
  SystemInfo,
} from "../lib/types";
import { useToast } from "../context/toast";
import {
  AlertBanner,
  Badge,
  Button,
  Card,
  CardHeader,
  ConfirmDialog,
  ErrorState,
  Field,
  KeyValue,
  ModeBadge,
  PageHeader,
  PageSkeleton,
  Select,
  TextInput,
  Toggle,
  textareaClass,
} from "../components/ui";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "8h", "1d"];
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

interface FormValues {
  symbols: string;
  trend_timeframe: string;
  structure_timeframe: string;
  entry_timeframe: string;
  risk_pct: string;
  max_daily_loss_pct: string;
  max_open_positions: string;
  min_score: string;
  leverage: string;
  starting_balance: string;
  taker_fee_pct: string;
  slippage_pct: string;
  session_filter: boolean;
  session_start_utc: string;
  session_end_utc: string;
  telegram_chat_id: string;
}

function toForm(settings: BotSettings): FormValues {
  return {
    symbols: settings.symbols,
    trend_timeframe: settings.trend_timeframe,
    structure_timeframe: settings.structure_timeframe,
    entry_timeframe: settings.entry_timeframe,
    risk_pct: String(settings.risk_pct),
    max_daily_loss_pct: String(settings.max_daily_loss_pct),
    max_open_positions: String(settings.max_open_positions),
    min_score: String(settings.min_score),
    leverage: String(settings.leverage),
    starting_balance: String(settings.starting_balance),
    taker_fee_pct: String(settings.taker_fee_pct),
    slippage_pct: String(settings.slippage_pct),
    session_filter: Boolean(settings.session_filter),
    session_start_utc: String(settings.session_start_utc),
    session_end_utc: String(settings.session_end_utc),
    telegram_chat_id: settings.telegram_chat_id ?? "",
  };
}

export function SettingsPage() {
  useDocumentTitle("Settings");
  const navigate = useNavigate();
  const toast = useToast();
  const settingsState = usePolling<BotSettings>(() => apiGet("/api/v1/settings"), 0);
  const systemState = usePolling<SystemInfo>(() => apiGet("/api/v1/system"), 30_000);
  const [modeConfirm, setModeConfirm] = useState(false);
  const [modeBusy, setModeBusy] = useState<"paper" | "live" | null>(null);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [killOpen, setKillOpen] = useState(false);
  const [killBusy, setKillBusy] = useState(false);

  const settings = settingsState.data;
  const system = systemState.data;

  const refreshAll = async () => {
    await Promise.all([settingsState.refresh(true), systemState.refresh(true)]);
  };

  const changeMode = async (target: "paper" | "live") => {
    setModeBusy(target);
    try {
      const response = await apiPost<ActionResponse>(`/api/v1/actions/mode/${target}`);
      toast.success(target === "live" ? "Live mode armed" : "Paper mode enabled", response.message);
      setModeConfirm(false);
      await refreshAll();
    } catch (cause) {
      toast.error("Could not change mode", errorMessage(cause));
    } finally {
      setModeBusy(null);
    }
  };

  const togglePause = async () => {
    if (!settings) return;
    setPauseBusy(true);
    try {
      const response = await apiPost<ActionResponse>(
        settings.paused ? "/api/v1/actions/resume" : "/api/v1/actions/pause",
      );
      toast.success(settings.paused ? "Engine resumed" : "Engine paused", response.message);
      await refreshAll();
    } catch (cause) {
      toast.error("Engine action failed", errorMessage(cause));
    } finally {
      setPauseBusy(false);
    }
  };

  const killSwitch = async () => {
    setKillBusy(true);
    try {
      const response = await apiPost<ActionResponse>("/api/v1/actions/kill");
      toast.success("Kill switch engaged", response.message);
      setKillOpen(false);
      await refreshAll();
    } catch (cause) {
      toast.error("Kill switch failed", errorMessage(cause));
    } finally {
      setKillBusy(false);
    }
  };

  if (settingsState.loading && !settings) return <PageSkeleton cards={4} rows={6} />;
  if (settingsState.error && !settings) {
    return <ErrorState message={settingsState.error} retry={() => void settingsState.refresh()} />;
  }
  if (!settings) return <ErrorState message="No settings returned." retry={() => void settingsState.refresh()} />;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <Settings2 className="h-3 w-3" /> Configuration
          </>
        }
        title="Settings"
        description="Strategy, risk, execution mode and notification configuration. Changes apply to the next scan."
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              icon={RefreshCw}
              onClick={() => void refreshAll()}
            >
              Refresh
            </Button>
            <Button variant="secondary" size="sm" icon={Server} onClick={() => navigate("/diagnostics")}>
              Diagnostics
            </Button>
          </>
        }
      />

      {settingsState.error ? (
        <AlertBanner tone="rose" title="Settings refresh failed">
          {settingsState.error}
        </AlertBanner>
      ) : null}
      {!settings.paper_mode ? (
        <AlertBanner
          tone="rose"
          icon={ShieldAlert}
          title="LIVE execution mode is armed"
        >
          Confirm MEXC keys, position size and stops before resuming entries. The engine
          pauses itself whenever live mode is armed.
        </AlertBanner>
      ) : null}

      <section className="grid gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Execution mode"
            description="Paper mode is safe. Live mode requires the environment switch and MEXC credentials."
            icon={ShieldCheck}
            action={<ModeBadge mode={settings.paper_mode ? "PAPER" : "LIVE"} paused={settings.paused} />}
          />
          <div className="space-y-4 p-4 sm:p-5">
            <div className="flex items-center justify-between rounded-xl border border-slate-800/70 bg-slate-950/40 px-4 py-3">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-600">
                  Current execution
                </p>
                <p className={cn("mt-1 text-lg font-bold", settings.paper_mode ? "text-sky-300" : "text-rose-300")}>
                  {settings.paper_mode ? "Paper simulation" : "Live exchange orders"}
                </p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  {settings.paper_mode
                    ? "Fills are journaled locally. No exchange orders are sent."
                    : "Orders are routed through the MEXC adapter."}
                </p>
              </div>
              <Badge tone={settings.paper_mode ? "sky" : "rose"} dot pulse={!settings.paper_mode}>
                {settings.paper_mode ? "SAFE" : "ARMED"}
              </Badge>
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <Button
                variant={settings.paper_mode ? "primary" : "secondary"}
                icon={ShieldCheck}
                loading={modeBusy === "paper"}
                disabled={modeBusy !== null || settings.paper_mode}
                onClick={() => void changeMode("paper")}
              >
                Use paper mode
              </Button>
              <Button
                variant={settings.paper_mode ? "danger" : "primary"}
                icon={ShieldAlert}
                loading={modeBusy === "live"}
                disabled={modeBusy !== null || !settings.paper_mode || !system?.live_allowed || !system?.mexc_configured}
                onClick={() => setModeConfirm(true)}
              >
                Arm live mode
              </Button>
            </div>

            <div className="space-y-1.5 text-[11px] leading-5 text-slate-500">
              <div className="flex items-center gap-2">
                <span className={cn("h-1.5 w-1.5 rounded-full", system?.live_allowed ? "bg-emerald-400" : "bg-rose-400")} />
                Environment switch <code className="rounded bg-slate-900 px-1 py-0.5 text-[10px] text-slate-400">LIVE_TRADING_ALLOWED</code>{" "}
                {system?.live_allowed ? "enabled" : "disabled"}
              </div>
              <div className="flex items-center gap-2">
                <span className={cn("h-1.5 w-1.5 rounded-full", system?.mexc_configured ? "bg-emerald-400" : "bg-rose-400")} />
                MEXC API credentials {system?.mexc_configured ? "configured" : "missing"}
              </div>
              {!system?.live_allowed || !system?.mexc_configured ? (
                <p className="pt-1">
                  Update <code className="rounded bg-slate-900 px-1 py-0.5 text-[10px] text-slate-400">.env</code>{" "}
                  and restart the engine to unlock live arming. The dashboard never writes secrets.
                </p>
              ) : null}
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Lifecycle controls"
            description="Pausing stops new entries but keeps managing open positions."
            icon={Timer}
            action={<Badge tone={settings.paused ? "amber" : "emerald"} dot pulse={!settings.paused}>{settings.paused ? "Paused" : "Running"}</Badge>}
          />
          <div className="space-y-4 p-4 sm:p-5">
            <div className="flex flex-wrap gap-2">
              <Button
                variant={settings.paused ? "primary" : "secondary"}
                icon={settings.paused ? Play : Pause}
                loading={pauseBusy}
                onClick={() => void togglePause()}
              >
                {settings.paused ? "Resume engine" : "Pause engine"}
              </Button>
              <Button variant="danger" icon={ShieldAlert} onClick={() => setKillOpen(true)}>
                Kill switch
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-slate-800/60 bg-slate-950/40 px-3 py-2.5">
                <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-600">Last scan</p>
                <p className="num mt-1 text-xs text-slate-300">{settings.last_scan_at ? fmtDateTime(settings.last_scan_at) : "Never"}</p>
              </div>
              <div className="rounded-xl border border-slate-800/60 bg-slate-950/40 px-3 py-2.5">
                <p className="text-[9px] font-semibold uppercase tracking-[0.14em] text-slate-600">Settings updated</p>
                <p className="num mt-1 text-xs text-slate-300">{settings.updated_at ? fmtDateTime(settings.updated_at) : "—"}</p>
              </div>
            </div>
            <p className="text-[11px] leading-5 text-slate-500">
              The kill switch closes every open position at market, pauses the engine and
              stops new entries. Use it when a market event invalidates the current risk
              plan.
            </p>
          </div>
        </Card>
      </section>

      <section className="grid items-start gap-3 xl:grid-cols-[minmax(0,1fr)_380px]">
        <SettingsForm
          settings={settings}
          onSaved={() => void refreshAll()}
        />

        <div className="space-y-3 xl:sticky xl:top-24">
          <Card>
            <CardHeader
              title="System configuration"
              description="Environment-level capabilities, read-only."
              icon={Server}
              action={<Badge tone={system?.environment === "production" ? "rose" : "sky"}>{system?.environment ?? "—"}</Badge>}
            />
            <div className="px-4 py-2">
              <KeyValue label="Version" value={system?.version ?? "—"} />
              <KeyValue label="Mode" value={system?.mode ?? "—"} />
              <KeyValue label="Database" value={system?.database ?? "—"} />
              <KeyValue label="Scheduler" value={system ? (system.paused ? "Paused" : "Enabled") : "—"} />
              <KeyValue label="Telegram bot" value={system?.telegram_configured ? "Configured" : "Not configured"} />
              <KeyValue label="Dashboard auth" value={system?.dashboard_auth ? "Enabled" : "Disabled"} />
              <KeyValue label="API bearer token" value={system?.api_token_configured ? "Configured" : "Not configured"} />
              <KeyValue label="Scan interval" value={system ? `${system.scan_interval_seconds}s` : "—"} />
              <KeyValue label="SSE interval" value={system ? `${system.sse_interval_seconds}s` : "—"} />
            </div>
            <div className="border-t border-slate-800/60 px-4 py-3">
              <Button size="sm" variant="ghost" icon={ExternalLink} className="px-0" onClick={() => navigate("/diagnostics")}>
                Open diagnostics
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader title="Safety checklist" description="Before you arm live orders." icon={ListChecks} />
            <div className="space-y-2.5 p-4">
              {[
                "Paper results reviewed for several weeks",
                "Backtest matches the current settings",
                "Position size is affordable if stopped out",
                "MEXC keys are trade-only, not withdrawal",
                "Telegram alerts reach your phone",
                "Kill switch location memorized",
              ].map((item) => (
                <div key={item} className="flex items-start gap-2 text-[11px] leading-5 text-slate-400">
                  <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500/70" />
                  {item}
                </div>
              ))}
              <p className="border-t border-slate-800/60 pt-2.5 text-[10px] leading-5 text-slate-600">
                A strict strategy can look inactive for long periods. That is a feature,
                not a reason to lower the threshold impulsively.
              </p>
            </div>
          </Card>
        </div>
      </section>

      <ConfirmDialog
        open={modeConfirm}
        title="Arm LIVE trading?"
        message={
          <span>
            The engine will be switched to the live MEXC adapter and paused. Review
            leverage, symbols, risk percentage and stop behavior before resuming. Real
            money can be lost.
          </span>
        }
        confirmLabel="Arm live execution"
        loading={modeBusy === "live"}
        onCancel={() => setModeConfirm(false)}
        onConfirm={() => void changeMode("live")}
      />

      <ConfirmDialog
        open={killOpen}
        title="Engage the kill switch?"
        message="Every open position will be closed at market and the engine will pause. This action is recorded in the journal."
        confirmLabel="Close all & pause"
        loading={killBusy}
        onCancel={() => setKillOpen(false)}
        onConfirm={() => void killSwitch()}
      />
    </div>
  );
}

function SettingsForm({
  settings,
  onSaved,
}: {
  settings: BotSettings;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [values, setValues] = useState<FormValues>(() => toForm(settings));
  const [baseline, setBaseline] = useState(() => JSON.stringify(toForm(settings)));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const set = <K extends keyof FormValues>(key: K, value: FormValues[K]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const dirty = JSON.stringify(values) !== baseline;

  const reset = () => {
    setValues(JSON.parse(baseline) as FormValues);
    setSaveError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaveError(null);

    const numbers = {
      risk_pct: Number(values.risk_pct),
      max_daily_loss_pct: Number(values.max_daily_loss_pct),
      max_open_positions: Number(values.max_open_positions),
      min_score: Number(values.min_score),
      leverage: Number(values.leverage),
      starting_balance: Number(values.starting_balance),
      taker_fee_pct: Number(values.taker_fee_pct),
      slippage_pct: Number(values.slippage_pct),
      session_start_utc: Number(values.session_start_utc),
      session_end_utc: Number(values.session_end_utc),
    };

    if (!values.symbols.trim()) {
      setSaveError("At least one symbol is required.");
      return;
    }
    if (Object.values(numbers).some((value) => !Number.isFinite(value))) {
      setSaveError("Every numeric field must contain a valid number.");
      return;
    }
    if (numbers.risk_pct < 0.05 || numbers.risk_pct > 5) {
      setSaveError("Risk per trade must be between 0.05% and 5%.");
      return;
    }
    if (numbers.max_daily_loss_pct < 0.1 || numbers.max_daily_loss_pct > 20) {
      setSaveError("Daily loss stop must be between 0.1% and 20%.");
      return;
    }
    if (numbers.max_open_positions < 1 || numbers.max_open_positions > 10) {
      setSaveError("Max open positions must be between 1 and 10.");
      return;
    }
    if (numbers.min_score < 0 || numbers.min_score > 100) {
      setSaveError("Minimum score must be between 0 and 100.");
      return;
    }
    if (numbers.leverage < 1 || numbers.leverage > 50) {
      setSaveError("Leverage must be between 1x and 50x.");
      return;
    }
    if (numbers.starting_balance < 10) {
      setSaveError("Starting balance must be at least $10.");
      return;
    }
    if (numbers.taker_fee_pct < 0 || numbers.taker_fee_pct > 1) {
      setSaveError("Taker fee must be between 0% and 1%.");
      return;
    }
    if (numbers.slippage_pct < 0 || numbers.slippage_pct > 1) {
      setSaveError("Slippage must be between 0% and 1%.");
      return;
    }

    setSaving(true);
    const payload = {
      symbols: values.symbols.trim(),
      trend_timeframe: values.trend_timeframe,
      structure_timeframe: values.structure_timeframe,
      entry_timeframe: values.entry_timeframe,
      risk_pct: numbers.risk_pct,
      max_daily_loss_pct: numbers.max_daily_loss_pct,
      max_open_positions: numbers.max_open_positions,
      min_score: numbers.min_score,
      leverage: numbers.leverage,
      starting_balance: numbers.starting_balance,
      taker_fee_pct: numbers.taker_fee_pct,
      slippage_pct: numbers.slippage_pct,
      session_filter: values.session_filter,
      session_start_utc: numbers.session_start_utc,
      session_end_utc: numbers.session_end_utc,
      telegram_chat_id: values.telegram_chat_id.trim(),
    };

    try {
      const updated = await apiPut<BotSettings>("/api/v1/settings", payload);
      const normalized = toForm(updated);
      setValues(normalized);
      setBaseline(JSON.stringify(normalized));
      toast.success("Settings saved", "The engine will use these values on its next scan.");
      onSaved();
    } catch (cause) {
      setSaveError(errorMessage(cause));
      toast.error("Could not save settings", errorMessage(cause));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <form onSubmit={submit}>
        <CardHeader
          title="Strategy configuration"
          description="All times are UTC. The engine reloads this configuration before every scan."
          icon={SlidersHorizontal}
          action={dirty ? <Badge tone="amber" dot>Unsaved changes</Badge> : <Badge tone="slate">Saved</Badge>}
        />

        <div className="space-y-6 p-4 sm:p-5">
          {saveError ? (
            <div className="rounded-xl border border-rose-500/25 bg-rose-500/[0.07] px-3.5 py-2.5 text-xs leading-5 text-rose-200">
              {saveError}
            </div>
          ) : null}

          <section className="space-y-3">
            <div className="flex items-center gap-2">
              <Layers className="h-3.5 w-3.5 text-slate-500" />
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Instruments & timeframes
              </h3>
            </div>
            <Field
              label="Symbols"
              htmlFor="symbols"
              hint="Comma-separated MEXC USDT perpetuals. BTC/USDT, ETH/USDT or BTC/USDT:USDT are accepted."
            >
              <textarea
                id="symbols"
                className={textareaClass}
                rows={2}
                value={values.symbols}
                onChange={(event) => set("symbols", event.target.value)}
                placeholder="BTC/USDT, ETH/USDT, SOL/USDT"
                required
              />
            </Field>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Trend filter" htmlFor="trend-timeframe">
                <Select
                  id="trend-timeframe"
                  value={values.trend_timeframe}
                  onChange={(event) => set("trend_timeframe", event.target.value)}
                >
                  {TIMEFRAMES.map((timeframe) => (
                    <option key={timeframe} value={timeframe}>
                      {timeframe}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Structure" htmlFor="structure-timeframe">
                <Select
                  id="structure-timeframe"
                  value={values.structure_timeframe}
                  onChange={(event) => set("structure_timeframe", event.target.value)}
                >
                  {TIMEFRAMES.map((timeframe) => (
                    <option key={timeframe} value={timeframe}>
                      {timeframe}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Entry trigger" htmlFor="entry-timeframe">
                <Select
                  id="entry-timeframe"
                  value={values.entry_timeframe}
                  onChange={(event) => set("entry_timeframe", event.target.value)}
                >
                  {TIMEFRAMES.map((timeframe) => (
                    <option key={timeframe} value={timeframe}>
                      {timeframe}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </section>

          <section className="space-y-3 border-t border-slate-800/60 pt-5">
            <div className="flex items-center gap-2">
              <Gauge className="h-3.5 w-3.5 text-slate-500" />
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Risk & scoring
              </h3>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Risk per trade %" htmlFor="risk-pct">
                <TextInput
                  id="risk-pct"
                  type="number"
                  min={0.05}
                  max={5}
                  step={0.01}
                  value={values.risk_pct}
                  onChange={(event) => set("risk_pct", event.target.value)}
                  required
                />
              </Field>
              <Field label="Daily loss stop %" htmlFor="daily-loss">
                <TextInput
                  id="daily-loss"
                  type="number"
                  min={0.1}
                  max={20}
                  step={0.1}
                  value={values.max_daily_loss_pct}
                  onChange={(event) => set("max_daily_loss_pct", event.target.value)}
                  required
                />
              </Field>
              <Field label="Max open positions" htmlFor="max-positions">
                <TextInput
                  id="max-positions"
                  type="number"
                  min={1}
                  max={10}
                  step={1}
                  value={values.max_open_positions}
                  onChange={(event) => set("max_open_positions", event.target.value)}
                  required
                />
              </Field>
              <Field label="Minimum confluence" htmlFor="min-score" hint="0–100. The default is deliberately strict.">
                <TextInput
                  id="min-score"
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={values.min_score}
                  onChange={(event) => set("min_score", event.target.value)}
                  required
                />
              </Field>
              <Field label="Leverage cap" htmlFor="leverage" hint="Caps notional, not stop distance.">
                <TextInput
                  id="leverage"
                  type="number"
                  min={1}
                  max={50}
                  step={1}
                  value={values.leverage}
                  onChange={(event) => set("leverage", event.target.value)}
                  required
                />
              </Field>
              <Field label="Starting balance" htmlFor="starting-balance">
                <TextInput
                  id="starting-balance"
                  type="number"
                  min={10}
                  max={10000000}
                  step={10}
                  value={values.starting_balance}
                  onChange={(event) => set("starting_balance", event.target.value)}
                  required
                />
              </Field>
            </div>
          </section>

          <section className="space-y-3 border-t border-slate-800/60 pt-5">
            <div className="flex items-center gap-2">
              <Wallet className="h-3.5 w-3.5 text-slate-500" />
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Execution costs
              </h3>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Taker fee %" htmlFor="taker-fee" hint="Charged on entry and exit.">
                <TextInput
                  id="taker-fee"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={values.taker_fee_pct}
                  onChange={(event) => set("taker_fee_pct", event.target.value)}
                  required
                />
              </Field>
              <Field label="Slippage %" htmlFor="slippage" hint="Applied to simulated fills.">
                <TextInput
                  id="slippage"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={values.slippage_pct}
                  onChange={(event) => set("slippage_pct", event.target.value)}
                  required
                />
              </Field>
            </div>
          </section>

          <section className="space-y-3 border-t border-slate-800/60 pt-5">
            <div className="flex items-center gap-2">
              <Timer className="h-3.5 w-3.5 text-slate-500" />
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Session window
              </h3>
            </div>
            <Toggle
              checked={values.session_filter}
              onChange={(value) => set("session_filter", value)}
              label="Restrict new entries to a UTC session"
              description="Open positions are always managed. The window only gates new entries."
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Session start (UTC)" htmlFor="session-start">
                <Select
                  id="session-start"
                  value={values.session_start_utc}
                  onChange={(event) => set("session_start_utc", event.target.value)}
                  disabled={!values.session_filter}
                >
                  {HOURS.map((hour) => (
                    <option key={hour} value={hour}>
                      {String(hour).padStart(2, "0")}:00 UTC
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Session end (UTC)" htmlFor="session-end">
                <Select
                  id="session-end"
                  value={values.session_end_utc}
                  onChange={(event) => set("session_end_utc", event.target.value)}
                  disabled={!values.session_filter}
                >
                  {HOURS.map((hour) => (
                    <option key={hour} value={hour}>
                      {String(hour).padStart(2, "0")}:00 UTC
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
          </section>

          <section className="space-y-3 border-t border-slate-800/60 pt-5">
            <div className="flex items-center gap-2">
              <KeyRound className="h-3.5 w-3.5 text-slate-500" />
              <h3 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Telegram notifications
              </h3>
            </div>
            <Field
              label="Telegram chat ID"
              htmlFor="telegram-chat"
              hint="Numeric chat ID used by the bot for fills, risk events and daily reports. Leave empty to disable."
            >
              <TextInput
                id="telegram-chat"
                className="num"
                value={values.telegram_chat_id}
                onChange={(event) => set("telegram_chat_id", event.target.value)}
                placeholder="123456789"
              />
            </Field>
            <div className="rounded-xl border border-slate-800/60 bg-slate-950/40 px-3.5 py-3 text-[11px] leading-5 text-slate-500">
              Secrets such as the Telegram bot token and MEXC keys live in
              <code className="mx-1 rounded bg-slate-900 px-1 py-0.5 text-[10px] text-slate-400">.env</code>
              only. The dashboard does not read or display them.
            </div>
          </section>

          <section className="space-y-2 rounded-xl border border-rose-500/15 bg-rose-500/[0.035] p-4">
            <div className="flex items-center gap-2 text-rose-200">
              <AlertTriangle className="h-3.5 w-3.5" />
              <h3 className="text-xs font-semibold">Risk warning</h3>
            </div>
            <p className="text-[11px] leading-5 text-rose-200/60">
              Raising risk per trade, removing the daily loss stop or arming live mode can
              turn a testable system into an expensive lesson. Change one variable at a
              time, then compare the journal.
            </p>
          </section>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/70 bg-slate-950/50 px-4 py-3 sm:px-5">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em] text-slate-600">
            <span className={cn("h-1.5 w-1.5 rounded-full", dirty ? "bg-amber-400" : "bg-emerald-500/60")} />
            {dirty ? "Unsaved changes" : `Saved ${settings.updated_at ? fmtFullDateTime(settings.updated_at) : ""}`}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={reset} disabled={!dirty || saving}>
              Reset
            </Button>
            <Button
              type="submit"
              variant="primary"
              size="sm"
              icon={Save}
              loading={saving}
              disabled={!dirty}
            >
              Save settings
            </Button>
          </div>
        </div>
      </form>
    </Card>
  );
}
