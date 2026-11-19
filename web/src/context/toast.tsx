import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "../lib/format";

export type ToastTone = "success" | "error" | "info" | "warning";

export interface ToastOptions {
  title: string;
  message?: string;
  tone?: ToastTone;
  durationMs?: number;
}

interface ToastItem extends ToastOptions {
  id: string;
  tone: ToastTone;
}

interface ToastContextValue {
  notify: (options: ToastOptions | string) => void;
  success: (title: string, message?: string) => void;
  error: (title: string, message?: string) => void;
  info: (title: string, message?: string) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const toneStyles: Record<ToastTone, { wrap: string; icon: string; Icon: typeof Info }> = {
  success: {
    wrap: "border-emerald-500/30 bg-emerald-500/[0.08]",
    icon: "text-emerald-400",
    Icon: CheckCircle2,
  },
  error: {
    wrap: "border-rose-500/30 bg-rose-500/[0.08]",
    icon: "text-rose-400",
    Icon: XCircle,
  },
  warning: {
    wrap: "border-amber-500/30 bg-amber-500/[0.08]",
    icon: "text-amber-400",
    Icon: AlertTriangle,
  },
  info: {
    wrap: "border-sky-500/30 bg-sky-500/[0.08]",
    icon: "text-sky-400",
    Icon: Info,
  },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<string, number>>(new Map());

  const dismiss = useCallback((id: string) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const notify = useCallback(
    (options: ToastOptions | string) => {
      const normalized = typeof options === "string" ? { title: options } : options;
      const id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const item: ToastItem = {
        id,
        tone: normalized.tone ?? "info",
        title: normalized.title,
        message: normalized.message,
        durationMs: normalized.durationMs ?? 4_500,
      };
      setItems((current) => [...current.slice(-4), item]);
      const timer = window.setTimeout(() => dismiss(id), item.durationMs ?? 4_500);
      timers.current.set(id, timer);
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      notify,
      success: (title, message) => notify({ title, message, tone: "success" }),
      error: (title, message) => notify({ title, message, tone: "error" }),
      info: (title, message) => notify({ title, message, tone: "info" }),
      dismiss,
    }),
    [notify, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-end gap-2 p-4 sm:inset-x-auto sm:right-0 sm:w-[380px]"
      >
        {items.map((item) => {
          const style = toneStyles[item.tone];
          const Icon = style.Icon;
          return (
            <div
              key={item.id}
              role="status"
              className={cn(
                "toast-enter pointer-events-auto flex w-full items-start gap-3 rounded-xl border px-4 py-3 shadow-2xl shadow-black/40 backdrop-blur-xl",
                style.wrap,
              )}
            >
              <Icon className={cn("mt-0.5 h-4.5 w-4.5 shrink-0", style.icon)} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-100">{item.title}</p>
                {item.message ? (
                  <p className="mt-0.5 text-xs leading-5 text-slate-400">{item.message}</p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                className="rounded-md p-1 text-slate-500 transition hover:bg-white/5 hover:text-slate-300"
                aria-label="Dismiss notification"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
