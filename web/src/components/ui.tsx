import {
  useEffect,
  useId,
  type ButtonHTMLAttributes,
  type HTMLAttributes,
  type ComponentType,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, CheckCircle2, Inbox, Loader2, RefreshCw, X } from "lucide-react";
import { cn, fmtPct, scoreTone, sideLabel, signalStatusTone } from "../lib/format";
import type { Tone } from "../lib/types";

export type IconComponent = ComponentType<
  SVGProps<SVGSVGElement> & { size?: number | string | undefined }
>;

/* ------------------------------------------------------------------ cards */

export function Card({ className, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-800/70 bg-[#0a1120]/80 shadow-[inset_0_1px_0_rgba(255,255,255,.03),0_30px_80px_-60px_rgba(0,0,0,.9)] backdrop-blur-sm",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
  icon: Icon,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  icon?: IconComponent;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 border-b border-slate-800/60 px-4 py-4 sm:px-5",
        className,
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        {Icon ? (
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/80 text-slate-400">
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-tight text-white">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-[11px] leading-5 text-slate-500">{description}</p>
          ) : null}
        </div>
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div className="min-w-0">
        {eyebrow ? (
          <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">
            {eyebrow}
          </div>
        ) : null}
        <h1 className="text-2xl font-bold tracking-tight text-white sm:text-[28px]">{title}</h1>
        {description ? (
          <p className="mt-1.5 max-w-3xl text-sm leading-6 text-slate-500">{description}</p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex flex-wrap items-center gap-2 xl:shrink-0 xl:justify-end">{actions}</div>
      ) : null}
    </header>
  );
}

/* ------------------------------------------------------------------ buttons */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type ButtonSize = "sm" | "md" | "icon";

const buttonVariants: Record<ButtonVariant, string> = {
  primary:
    "bg-emerald-400 text-slate-950 shadow-[0_10px_30px_-12px_rgba(52,211,153,.6)] hover:bg-emerald-300 focus-visible:outline-emerald-300",
  secondary:
    "border border-slate-700/80 bg-slate-800/60 text-slate-200 hover:border-slate-600 hover:bg-slate-800 hover:text-white",
  ghost:
    "text-slate-400 hover:bg-white/[0.05] hover:text-slate-100 focus-visible:outline-slate-400",
  danger:
    "border border-rose-500/30 bg-rose-500/10 text-rose-300 hover:border-rose-400/50 hover:bg-rose-500/20",
  outline:
    "border border-slate-800 bg-transparent text-slate-300 hover:border-slate-700 hover:bg-white/[0.03] hover:text-white",
};

const buttonSizes: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 rounded-lg px-2.5 text-xs",
  md: "h-10 gap-2 rounded-xl px-3.5 text-sm",
  icon: "h-9 w-9 rounded-lg",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: IconComponent;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon: Icon,
  className,
  children,
  disabled,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center font-semibold transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        buttonVariants[variant],
        buttonSizes[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : Icon ? (
        <Icon className={size === "icon" ? "h-4 w-4" : "h-4 w-4"} aria-hidden />
      ) : null}
      {size !== "icon" && children ? <span className="truncate">{children}</span> : null}
    </button>
  );
}

export function IconButton({
  icon: Icon,
  label,
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconComponent; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/50 text-slate-400 transition hover:border-slate-700 hover:text-white disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

/* ------------------------------------------------------------------ badges */

const badgeTones: Record<Tone, string> = {
  emerald: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  rose: "border-rose-500/25 bg-rose-500/10 text-rose-300",
  amber: "border-amber-500/25 bg-amber-500/10 text-amber-300",
  sky: "border-sky-500/25 bg-sky-500/10 text-sky-300",
  violet: "border-violet-500/25 bg-violet-500/10 text-violet-300",
  slate: "border-slate-700/70 bg-slate-800/50 text-slate-300",
  blue: "border-blue-500/25 bg-blue-500/10 text-blue-300",
};

const dotTones: Record<Tone, string> = {
  emerald: "bg-emerald-400",
  rose: "bg-rose-400",
  amber: "bg-amber-400",
  sky: "bg-sky-400",
  violet: "bg-violet-400",
  slate: "bg-slate-400",
  blue: "bg-blue-400",
};

export function Badge({
  children,
  tone = "slate",
  dot = false,
  pulse = false,
  className,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.08em]",
        badgeTones[tone],
        className,
      )}
    >
      {dot ? (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full",
            dotTones[tone],
            pulse && "animate-pulse",
          )}
        />
      ) : null}
      {children}
    </span>
  );
}

export function SideBadge({ side }: { side: string }) {
  const long = String(side).toLowerCase() === "long" || String(side).toUpperCase() === "BUY";
  return <Badge tone={long ? "emerald" : "rose"}>{sideLabel(side.toLowerCase())}</Badge>;
}

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={signalStatusTone(status)}>{status.replace(/_/g, " ")}</Badge>;
}

export function ModeBadge({ mode, paused }: { mode: string; paused?: boolean }) {
  const live = String(mode).toUpperCase() === "LIVE";
  return (
    <div className="flex items-center gap-2">
      <Badge tone={live ? "rose" : "sky"} dot pulse={!paused && !live}>
        {live ? "Live" : "Paper"}
      </Badge>
      <Badge tone={paused ? "amber" : "emerald"} dot pulse={!paused}>
        {paused ? "Paused" : "Running"}
      </Badge>
    </div>
  );
}

/* ------------------------------------------------------------------ stats */

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "slate",
  trend,
  className,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: IconComponent;
  tone?: Tone;
  trend?: "up" | "down" | "flat";
  className?: string;
}) {
  return (
    <Card className={cn("relative overflow-hidden p-4 sm:p-5", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">
            {label}
          </p>
          <div
            className={cn(
              "num mt-2 text-xl font-semibold tracking-tight text-white sm:text-2xl",
              trend === "up" && "text-emerald-300",
              trend === "down" && "text-rose-300",
            )}
          >
            {value}
          </div>
          {hint ? <div className="mt-1.5 text-[11px] leading-4 text-slate-500">{hint}</div> : null}
        </div>
        {Icon ? (
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border",
              badgeTones[tone],
            )}
          >
            <Icon className="h-4 w-4" />
          </span>
        ) : null}
      </div>
    </Card>
  );
}

export function MiniStat({
  label,
  value,
  tone = "slate",
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="rounded-xl border border-slate-800/60 bg-slate-950/40 px-3 py-2.5">
      <p className="text-[10px] font-medium uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p
        className={cn(
          "num mt-1 text-sm font-semibold",
          tone === "emerald" && "text-emerald-300",
          tone === "rose" && "text-rose-300",
          tone === "amber" && "text-amber-300",
          tone === "sky" && "text-sky-300",
          tone === "slate" && "text-slate-200",
        )}
      >
        {value}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ score */

export function ScoreBar({
  score,
  max = 100,
  showLabel = false,
  className,
}: {
  score: number;
  max?: number;
  showLabel?: boolean;
  className?: string;
}) {
  const clamped = Math.max(0, Math.min(100, (score / max) * 100));
  const tone = scoreTone(score);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-1.5 min-w-12 flex-1 overflow-hidden rounded-full bg-slate-800">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            tone === "emerald" && "bg-emerald-400",
            tone === "amber" && "bg-amber-400",
            tone === "rose" && "bg-rose-400",
          )}
          style={{ width: `${clamped}%` }}
        />
      </div>
      {showLabel ? (
        <span className="num w-10 text-right text-[11px] font-semibold text-slate-300">
          {Math.round(score)}
        </span>
      ) : null}
    </div>
  );
}

export function ScoreRing({ score, size = 92 }: { score: number; size?: number }) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, score));
  const offset = circumference - (clamped / 100) * circumference;
  const tone = scoreTone(score);
  const color = tone === "emerald" ? "#34d399" : tone === "amber" ? "#fbbf24" : "#fb7185";
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="rgba(148,163,184,.14)"
          strokeWidth="7"
          fill="transparent"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          fill="transparent"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="num text-xl font-bold text-white">{Math.round(score)}</span>
        <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-500">
          score
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ banners */

const bannerTones = {
  emerald: "border-emerald-500/25 bg-emerald-500/[0.07] text-emerald-200",
  rose: "border-rose-500/25 bg-rose-500/[0.07] text-rose-200",
  amber: "border-amber-500/25 bg-amber-500/[0.07] text-amber-200",
  sky: "border-sky-500/25 bg-sky-500/[0.07] text-sky-200",
  slate: "border-slate-700/60 bg-slate-800/30 text-slate-300",
};

export function AlertBanner({
  tone = "sky",
  title,
  icon: Icon = AlertTriangle,
  children,
  action,
}: {
  tone?: keyof typeof bannerTones;
  title: ReactNode;
  icon?: IconComponent;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={cn("flex items-start gap-3 rounded-xl border px-4 py-3", bannerTones[tone])}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold">{title}</p>
        {children ? <div className="mt-0.5 text-xs leading-5 opacity-75">{children}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ states */

export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  action,
  className,
}: {
  title: string;
  description?: ReactNode;
  icon?: IconComponent;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-slate-800 bg-slate-900/60 text-slate-500">
        <Icon className="h-5 w-5" />
      </span>
      <p className="mt-3 text-sm font-semibold text-slate-300">{title}</p>
      {description ? (
        <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  retry,
  compact = false,
}: {
  message: string;
  retry?: () => void;
  compact?: boolean;
}) {
  if (compact) {
    return (
      <div className="flex items-center justify-between gap-3 px-4 py-3 text-xs text-rose-300">
        <span className="min-w-0 truncate">{message}</span>
        {retry ? (
          <Button size="sm" variant="ghost" icon={RefreshCw} onClick={retry}>
            Retry
          </Button>
        ) : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-rose-500/25 bg-rose-500/10 text-rose-400">
        <AlertTriangle className="h-5 w-5" />
      </span>
      <p className="mt-3 text-sm font-semibold text-slate-200">Could not load this view</p>
      <p className="mt-1 max-w-md text-xs leading-5 text-slate-500">{message}</p>
      {retry ? (
        <Button variant="secondary" size="sm" icon={RefreshCw} onClick={retry} className="mt-4">
          Try again
        </Button>
      ) : null}
    </div>
  );
}

export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("skeleton rounded-lg bg-slate-800/60", className)} {...props} />;
}

export function PageSkeleton({ cards = 4, rows = 5 }: { cards?: number; rows?: number }) {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: cards }).map((_, index) => (
          <Skeleton key={index} className="h-28 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-3 xl:grid-cols-3">
        <Skeleton className="h-80 rounded-2xl xl:col-span-2" />
        <Skeleton className="h-80 rounded-2xl" />
      </div>
      <Skeleton className="h-72 rounded-2xl" />
      <div className="space-y-2">
        {Array.from({ length: rows }).map((_, index) => (
          <Skeleton key={index} className="h-10" />
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ forms */

export const inputClass =
  "h-10 w-full rounded-xl border border-slate-800 bg-slate-950/60 px-3.5 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-50";

export const selectClass =
  "h-10 w-full appearance-none rounded-xl border border-slate-800 bg-slate-950/60 px-3.5 pr-9 text-sm text-slate-200 outline-none transition focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/10";

export const textareaClass =
  "w-full rounded-xl border border-slate-800 bg-slate-950/60 px-3.5 py-2.5 text-sm text-slate-100 placeholder:text-slate-600 outline-none transition focus:border-emerald-500/50 focus:ring-2 focus:ring-emerald-500/10";

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
  className,
}: {
  label: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <label
        htmlFor={htmlFor}
        className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500"
      >
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-[11px] text-rose-300">{error}</p>
      ) : hint ? (
        <p className="text-[11px] leading-4 text-slate-500">{hint}</p>
      ) : null}
    </div>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cn(inputClass, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select {...props} className={cn(selectClass, props.className)} />
      <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-500">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-slate-800/70 bg-slate-950/30 px-3.5 py-3">
      <div className="min-w-0">
        <label htmlFor={id} className="text-sm font-medium text-slate-200">
          {label}
        </label>
        {description ? <p className="mt-0.5 text-[11px] leading-4 text-slate-500">{description}</p> : null}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full border transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-400 disabled:opacity-50",
          checked
            ? "border-emerald-400/50 bg-emerald-400/90"
            : "border-slate-700 bg-slate-800",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white shadow transition-all",
            checked ? "left-[calc(100%-1.25rem)]" : "left-0.5",
          )}
        />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ modal */

const modalSizes = {
  sm: "max-w-md",
  md: "max-w-lg",
  lg: "max-w-3xl",
};

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: keyof typeof modalSizes;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end justify-center p-3 sm:items-center sm:p-6">
      <button
        type="button"
        aria-label="Close dialog"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : undefined}
        className={cn(
          "relative z-10 w-full overflow-hidden rounded-2xl border border-slate-700/70 bg-[#0a1120] shadow-2xl shadow-black/60",
          "modal-enter",
          modalSizes[size],
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-800/70 px-5 py-4">
          <div>
            <h2 className="text-sm font-semibold text-white">{title}</h2>
            {description ? (
              <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-white/5 hover:text-slate-200"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {children ? <div className="max-h-[65vh] overflow-y-auto px-5 py-4">{children}</div> : null}
        {footer ? (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-800/70 bg-slate-950/30 px-5 py-3">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  loading = false,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: "danger" | "primary";
  loading?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            loading={loading}
            icon={tone === "danger" ? AlertTriangle : CheckCircle2}
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-6 text-slate-400">{message}</div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ misc */

export function KeyValue({
  label,
  value,
  mono = true,
  icon: Icon,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  icon?: IconComponent;
}) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-slate-800/50 py-2.5 last:border-0">
      <span className="flex items-center gap-2 text-xs text-slate-500">
        {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
        {label}
      </span>
      <span
        className={cn(
          "max-w-[60%] break-words text-right text-xs font-medium text-slate-200",
          mono && "num",
        )}
      >
        {value}
      </span>
    </div>
  );
}

export function Progress({ value, tone = "emerald" }: { value: number; tone?: Tone }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500",
          tone === "emerald" && "bg-emerald-400",
          tone === "rose" && "bg-rose-400",
          tone === "amber" && "bg-amber-400",
          tone === "sky" && "bg-sky-400",
          tone === "violet" && "bg-violet-400",
          tone === "blue" && "bg-blue-400",
          tone === "slate" && "bg-slate-400",
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

export function SyncLabel({
  updatedAt,
  loading = false,
  label = "Updated",
}: {
  updatedAt: Date | null;
  loading?: boolean;
  label?: string;
}) {
  return (
    <span className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-600">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          loading ? "animate-pulse bg-amber-400" : "bg-emerald-500/70",
        )}
      />
      {label}{" "}
      {updatedAt
        ? updatedAt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" })
        : "—"}
    </span>
  );
}

export function PercentChange({ value, digits = 2 }: { value: number; digits?: number }) {
  return (
    <span
      className={cn(
        "num inline-flex items-center gap-1 text-xs font-semibold",
        value > 0 ? "text-emerald-400" : value < 0 ? "text-rose-400" : "text-slate-400",
      )}
    >
      {value > 0 ? "▲" : value < 0 ? "▼" : "•"} {fmtPct(Math.abs(value), digits)}
    </span>
  );
}
