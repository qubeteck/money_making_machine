import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ChartCandlestick,
  KeyRound,
  Loader2,
  Lock,
  Mail,
  Send,
  ShieldCheck,
  User,
} from "lucide-react";
import { ApiError, apiPost, errorMessage } from "../lib/api";
import { cn } from "../lib/format";
import { useAuth } from "../context/auth";
import { AlertBanner, Button, Field, inputClass } from "../components/ui";

type Mode = "password" | "telegram";
type Screen = "login" | "register";

interface LoginResponse {
  ok: boolean;
  message?: string;
  user?: { id: number; username: string; email: string | null };
}

interface TelegramWidgetUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

export function LoginPage() {
  const { loading, authenticated, required, providers, refresh, error } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from || "/";

  const [screen, setScreen] = useState<Screen>("login");
  const [mode, setMode] = useState<Mode>("password");
  const [username, setUsername] = useState("admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [chatId, setChatId] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const [searchParams] = useSearchParams();
  const telegramWidgetRef = useRef<HTMLDivElement | null>(null);
  const telegramAvailable = Boolean(providers?.telegram);
  const googleAvailable = Boolean(providers?.google);
  const telegramBotUsername = (providers?.telegram_bot_username || "").replace(/^@/, "");
  const telegramWidgetAvailable = Boolean(
    providers?.telegram_widget && telegramBotUsername,
  );
  const nextPath = from.startsWith("/ui")
    ? from
    : `/ui${from === "/" ? "/" : from.startsWith("/") ? from : `/${from}`}`;
  const googleHref = `/auth/google?next=${encodeURIComponent(nextPath)}`;
  const headline = useMemo(
    () => (screen === "login" ? "Welcome back" : "Create your access"),
    [screen],
  );

  useEffect(() => {
    const authError = searchParams.get("auth_error");
    if (authError) setFormError(authError);
  }, [searchParams]);

  useEffect(() => {
    if (loading || authenticated || !telegramWidgetAvailable) return;
    const container = telegramWidgetRef.current;
    if (!container) return;

    const telegramWindow = window as Window & {
      mmTelegramAuth?: (user: TelegramWidgetUser) => void;
    };
    telegramWindow.mmTelegramAuth = async (user) => {
      setBusy(true);
      setFormError(null);
      setMessage(null);
      try {
        await apiPost<LoginResponse>(
          "/auth/telegram/widget",
          { ...user, next: nextPath },
          { skipAuthEvent: true },
        );
        await refresh();
        navigate(from, { replace: true });
      } catch (cause) {
        setFormError(errorMessage(cause));
      } finally {
        setBusy(false);
      }
    };

    container.replaceChildren();
    const script = document.createElement("script");
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.async = true;
    script.setAttribute("data-telegram-login", telegramBotUsername);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "10");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-lang", "en");
    script.setAttribute("data-onauth", "mmTelegramAuth(user)");
    container.appendChild(script);

    return () => {
      delete telegramWindow.mmTelegramAuth;
      container.replaceChildren();
    };
  }, [
    authenticated,
    from,
    loading,
    navigate,
    nextPath,
    refresh,
    telegramBotUsername,
    telegramWidgetAvailable,
  ]);

  if (loading) {
    return (
      <div className="app-background grid min-h-screen place-items-center">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-emerald-400/30 bg-emerald-400/10">
            <Loader2 className="h-5 w-5 animate-spin text-emerald-400" />
          </div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
            Checking your session
          </p>
        </div>
      </div>
    );
  }

  if (authenticated && !required) {
    return <Navigate to={from} replace />;
  }
  if (authenticated) {
    return <Navigate to={from} replace />;
  }

  const finish = async () => {
    await refresh();
    navigate(from, { replace: true });
  };

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    setMessage(null);
    try {
      if (screen === "register") {
        if (password !== confirmPassword) {
          throw new ApiError(400, "Passwords do not match.");
        }
        await apiPost<LoginResponse>(
          "/auth/register",
          { username, email: email || null, password, confirm_password: confirmPassword },
          { skipAuthEvent: true },
        );
        await finish();
      } else {
        await apiPost<LoginResponse>(
          "/auth/login",
          { username, password },
          { skipAuthEvent: true },
        );
        await finish();
      }
    } catch (cause) {
      setFormError(
        cause instanceof ApiError && cause.status === 401
          ? "Incorrect username or password."
          : errorMessage(cause),
      );
    } finally {
      setBusy(false);
    }
  };

  const requestCode = async () => {
    setBusy(true);
    setFormError(null);
    setMessage(null);
    try {
      const response = await apiPost<{ ok: boolean; message: string }>(
        "/auth/telegram/request-code",
        { chat_id: chatId, action: "login" },
        { skipAuthEvent: true },
      );
      setCodeSent(true);
      setMessage(response.message || "Verification code sent.");
    } catch (cause) {
      setFormError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const verifyCode = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFormError(null);
    try {
      await apiPost<LoginResponse>(
        "/auth/telegram/verify-code",
        { chat_id: chatId, code },
        { skipAuthEvent: true },
      );
      await finish();
    } catch (cause) {
      setFormError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  };

  const switchScreen = (next: Screen) => {
    setScreen(next);
    setFormError(null);
    setMessage(null);
    setCodeSent(false);
    setMode("password");
  };

  return (
    <div className="app-background min-h-screen">
      <div className="mx-auto grid min-h-screen max-w-[1220px] items-center gap-10 px-4 py-10 sm:px-6 lg:grid-cols-[1.05fr_.95fr] lg:gap-16 lg:px-8">
        {/* Brand / story panel */}
        <div className="hidden lg:block">
          <div className="mb-10 flex items-center gap-3">
            <img
              src="/ui/logo-192.png"
              alt="Money Machine logo"
              className="h-12 w-12 rounded-xl border border-emerald-400/25 object-cover shadow-lg shadow-emerald-950/40"
            />
            <div>
              <p className="text-sm font-bold tracking-[0.1em] text-white">MONEY MACHINE</p>
              <p className="text-[9px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                Trading control plane
              </p>
            </div>
          </div>

          <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-emerald-400/80">
            Multi-timeframe SMC engine
          </p>
          <h1 className="mt-4 max-w-xl text-4xl font-bold leading-[1.15] tracking-tight text-white">
            See the structure.
            <br />
            Let the engine execute.
          </h1>
          <p className="mt-5 max-w-md text-sm leading-7 text-slate-400">
            A self-hosted futures dashboard with a 4H trend filter, 1H structure map and
            15M execution trigger. Paper trading is the default; live mode needs two
            deliberate switches.
          </p>

          <div className="mt-10 grid max-w-lg gap-3">
            {[
              {
                icon: ShieldCheck,
                title: "Risk-first execution",
                body: "Structural stops, daily loss guardrails and a kill switch on every surface.",
              },
              {
                icon: ChartCandlestick,
                title: "One source of truth",
                body: "The dashboard, Telegram bot and trading engine share the same journal.",
              },
              {
                icon: KeyRound,
                title: "Deliberate live arming",
                body: "Live orders stay blocked until the env switch and dashboard arm are both set.",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.title}
                  className="flex items-start gap-3 rounded-xl border border-slate-800/60 bg-slate-900/30 px-4 py-3"
                >
                  <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-400/10 text-emerald-400">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div>
                    <p className="text-xs font-semibold text-slate-200">{item.title}</p>
                    <p className="mt-0.5 text-[11px] leading-5 text-slate-500">{item.body}</p>
                  </div>
                </div>
              );
            })}
          </div>

          <p className="mt-10 max-w-md text-[10px] leading-5 text-slate-600">
            Trading derivatives involves substantial risk of loss. Backtests and paper
            results are approximations, not promises. Only trade capital you can afford
            to lose.
          </p>
        </div>

        {/* Auth card */}
        <div className="mx-auto w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <img
              src="/ui/logo-192.png"
              alt="Money Machine logo"
              className="h-11 w-11 rounded-xl border border-emerald-400/25 object-cover shadow-lg shadow-emerald-950/40"
            />
            <div>
              <p className="text-sm font-bold tracking-[0.1em] text-white">MONEY MACHINE</p>
              <p className="text-[9px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                Trading control plane
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-800/70 bg-[#0a1120]/90 p-6 shadow-2xl shadow-black/40 backdrop-blur-xl sm:p-8">
            <div className="mb-6">
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-emerald-400/80">
                {screen === "login" ? "Secure access" : "New dashboard account"}
              </p>
              <h2 className="mt-1.5 text-2xl font-bold tracking-tight text-white">{headline}</h2>
              <p className="mt-1 text-sm text-slate-500">
                {screen === "login"
                  ? "Sign in to the trading command center."
                  : "Create credentials stored in the local database."}
              </p>
            </div>

            {error ? (
              <div className="mb-4">
                <AlertBanner
                  tone="rose"
                  title="Engine unreachable"
                  action={
                    <Button size="sm" variant="ghost" onClick={() => void refresh()}>
                      Retry
                    </Button>
                  }
                >
                  {error}
                </AlertBanner>
              </div>
            ) : null}

            {formError ? (
              <div className="mb-4 rounded-xl border border-rose-500/25 bg-rose-500/[0.07] px-3.5 py-2.5 text-xs leading-5 text-rose-200">
                {formError}
              </div>
            ) : null}
            {message ? (
              <div className="mb-4 rounded-xl border border-emerald-500/25 bg-emerald-500/[0.07] px-3.5 py-2.5 text-xs leading-5 text-emerald-200">
                {message}
              </div>
            ) : null}

            {googleAvailable || telegramWidgetAvailable ? (
              <div className="mb-5 space-y-3">
                {googleAvailable ? (
                  <div>
                    <a
                      href={googleHref}
                      title="Use your Gmail / Google account"
                      className={cn(
                        "flex h-11 w-full items-center justify-center gap-2.5 rounded-xl border border-slate-700 bg-white px-4 text-sm font-semibold text-slate-900 transition hover:bg-slate-100",
                        busy && "pointer-events-none opacity-60",
                      )}
                    >
                      <GoogleIcon />
                      Continue with Gmail
                    </a>
                    <p className="mt-1.5 text-center text-[10px] text-slate-600">
                      Google creates the dashboard account on first use.
                    </p>
                  </div>
                ) : null}

                {telegramWidgetAvailable ? (
                  <div>
                    <div
                      ref={telegramWidgetRef}
                      className="flex min-h-10 items-center justify-center"
                    />
                    <p className="mt-1.5 text-center text-[10px] text-slate-600">
                      Telegram creates the dashboard account on first use.
                    </p>
                  </div>
                ) : null}

                <div className="relative py-1">
                  <span className="absolute inset-x-0 top-1/2 h-px bg-slate-800" />
                  <span className="relative mx-auto block w-fit bg-[#0a1120] px-3 text-[10px] uppercase tracking-[0.16em] text-slate-600">
                    or {screen === "login" ? "use dashboard credentials" : "create a local account"}
                  </span>
                </div>
              </div>
            ) : null}

            {screen === "login" && telegramAvailable ? (
              <div className="mb-5 grid grid-cols-2 gap-1 rounded-xl border border-slate-800 bg-slate-950/50 p-1">
                {(
                  [
                    { key: "password", label: "Password", icon: Lock },
                    { key: "telegram", label: "Telegram code", icon: Send },
                  ] as const
                ).map((tab) => {
                  const Icon = tab.icon;
                  return (
                    <button
                      key={tab.key}
                      type="button"
                      onClick={() => {
                        setMode(tab.key);
                        setFormError(null);
                        setMessage(null);
                      }}
                      className={cn(
                        "flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition",
                        mode === tab.key
                          ? "bg-slate-800 text-white shadow"
                          : "text-slate-500 hover:text-slate-300",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" /> {tab.label}
                    </button>
                  );
                })}
              </div>
            ) : null}

            {mode === "password" || screen === "register" ? (
              <form onSubmit={submitPassword} className="space-y-4">
                <Field label="Username" htmlFor="username">
                  <div className="relative">
                    <User className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
                    <input
                      id="username"
                      className={cn(inputClass, "pl-10")}
                      value={username}
                      onChange={(event) => setUsername(event.target.value)}
                      autoComplete="username"
                      placeholder="admin"
                      required
                    />
                  </div>
                </Field>

                {screen === "register" ? (
                  <Field label="Email (optional)" htmlFor="email">
                    <div className="relative">
                      <Mail className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
                      <input
                        id="email"
                        type="email"
                        className={cn(inputClass, "pl-10")}
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        autoComplete="email"
                        placeholder="you@example.com"
                      />
                    </div>
                  </Field>
                ) : null}

                <Field
                  label="Password"
                  htmlFor="password"
                  hint={screen === "register" ? "At least 6 characters." : undefined}
                >
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
                    <input
                      id="password"
                      type="password"
                      className={cn(inputClass, "pl-10")}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      autoComplete={screen === "register" ? "new-password" : "current-password"}
                      placeholder="••••••••"
                      required
                      minLength={screen === "register" ? 6 : undefined}
                    />
                  </div>
                </Field>

                {screen === "register" ? (
                  <Field label="Confirm password" htmlFor="confirm-password">
                    <div className="relative">
                      <Lock className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-600" />
                      <input
                        id="confirm-password"
                        type="password"
                        className={cn(inputClass, "pl-10")}
                        value={confirmPassword}
                        onChange={(event) => setConfirmPassword(event.target.value)}
                        autoComplete="new-password"
                        placeholder="••••••••"
                        required
                      />
                    </div>
                  </Field>
                ) : null}

                <Button
                  type="submit"
                  variant="primary"
                  loading={busy}
                  className="mt-1 w-full"
                  icon={screen === "login" ? ArrowRight : ShieldCheck}
                >
                  {screen === "login" ? "Sign in" : "Create account"}
                </Button>
              </form>
            ) : (
              <form onSubmit={verifyCode} className="space-y-4">
                <Field
                  label="Telegram chat ID"
                  htmlFor="chat-id"
                  hint="Send /id to the bot to discover your numeric chat ID."
                >
                  <input
                    id="chat-id"
                    className={cn(inputClass, "num")}
                    value={chatId}
                    onChange={(event) => setChatId(event.target.value)}
                    inputMode="numeric"
                    placeholder="123456789"
                    required
                  />
                </Field>

                {codeSent ? (
                  <Field label="Verification code" htmlFor="telegram-code">
                    <input
                      id="telegram-code"
                      className={cn(inputClass, "num tracking-[0.3em]")}
                      value={code}
                      onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                      inputMode="numeric"
                      placeholder="000000"
                      maxLength={6}
                      required
                    />
                  </Field>
                ) : null}

                {codeSent ? (
                  <div className="flex gap-2">
                    <Button
                      type="submit"
                      variant="primary"
                      className="flex-1"
                      loading={busy}
                      icon={ShieldCheck}
                    >
                      Verify & sign in
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => void requestCode()}
                      disabled={busy}
                    >
                      Resend
                    </Button>
                  </div>
                ) : (
                  <Button
                    type="button"
                    variant="primary"
                    className="w-full"
                    loading={busy}
                    onClick={() => void requestCode()}
                    disabled={!chatId}
                    icon={Send}
                  >
                    Send verification code
                  </Button>
                )}
              </form>
            )}

            <div className="mt-6 border-t border-slate-800/70 pt-5">
              {screen === "login" ? (
                <p className="text-center text-xs text-slate-500">
                  No dashboard account?{" "}
                  <button
                    type="button"
                    onClick={() => switchScreen("register")}
                    className="font-semibold text-emerald-400 transition hover:text-emerald-300"
                  >
                    Create one
                  </button>
                </p>
              ) : (
                <button
                  type="button"
                  onClick={() => switchScreen("login")}
                  className="mx-auto flex items-center gap-1.5 text-xs font-semibold text-slate-400 transition hover:text-white"
                >
                  <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
                </button>
              )}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-[10px] text-slate-600">
            <span className="inline-flex items-center gap-1">
              <ShieldCheck className="h-3 w-3" /> HttpOnly session cookie
            </span>
            <a href="/auth/login" className="transition hover:text-slate-400">
              Classic sign in
            </a>
            <a href="/" className="transition hover:text-slate-400">
              Legacy dashboard
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
