import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ChartCandlestick, Loader2 } from "lucide-react";
import { AuthProvider, useAuth } from "./context/auth";
import { ToastProvider } from "./context/toast";
import { AppShell } from "./components/shell";
import { BacktestPage } from "./pages/BacktestPage";
import { CommandCenterPage } from "./pages/CommandCenterPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
import { LivePricesPage } from "./pages/LivePricesPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SignalsPage } from "./pages/SignalsPage";
import { TradesPage } from "./pages/TradesPage";

function BootScreen() {
  return (
    <div className="app-background grid min-h-screen place-items-center">
      <div className="flex flex-col items-center gap-3">
        <div className="relative flex h-12 w-12 items-center justify-center rounded-2xl border border-emerald-400/30 bg-emerald-400/10">
          <ChartCandlestick className="h-5 w-5 text-emerald-400" />
          <Loader2 className="absolute -bottom-1 -right-1 h-4 w-4 animate-spin rounded-full bg-[#05070d] text-slate-500" />
        </div>
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
          Starting command center
        </p>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { loading, authenticated } = useAuth();
  const location = useLocation();

  if (loading) return <BootScreen />;
  if (!authenticated) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="/command-center" element={<CommandCenterPage />} />
        <Route path="/trades" element={<TradesPage />} />
        <Route path="/signals" element={<SignalsPage />} />
        <Route path="/live" element={<LivePricesPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/diagnostics" element={<DiagnosticsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter basename="/ui">
      <ToastProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
