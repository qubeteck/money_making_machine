import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, apiGet, apiPost } from "../lib/api";
import type { AuthMe, AuthProviders, MeInfo } from "../lib/types";

export interface AuthUser {
  username: string;
  email?: string | null;
  telegramLinked?: boolean;
  method?: string;
}

interface AuthContextValue {
  loading: boolean;
  authenticated: boolean;
  required: boolean;
  user: AuthUser | null;
  providers: AuthProviders | null;
  me: MeInfo | null;
  error: string | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const [required, setRequired] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [providers, setProviders] = useState<AuthProviders | null>(null);
  const [me, setMe] = useState<MeInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requiredRef = useRef(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const providerInfo = await apiGet<AuthProviders>("/auth/providers", {
        skipAuthEvent: true,
      });
      setProviders(providerInfo);
      setRequired(providerInfo.auth_required);
      requiredRef.current = providerInfo.auth_required;

      if (!providerInfo.auth_required) {
        setAuthenticated(true);
        setMe(null);
        setUser({ username: "Local operator", method: "anonymous" });
        return;
      }

      let info: MeInfo | null = null;
      try {
        info = await apiGet<MeInfo>("/api/v1/me", { skipAuthEvent: true });
        setMe(info);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 401) {
          setAuthenticated(false);
          setUser(null);
          setMe(null);
          return;
        }
        throw cause;
      }

      if (!info.authenticated) {
        setAuthenticated(false);
        setUser(null);
        return;
      }

      setAuthenticated(true);
      let profile: AuthMe | null = null;
      try {
        profile = await apiGet<AuthMe>("/auth/me", { skipAuthEvent: true });
      } catch {
        // /auth/me is only reachable for cookie sessions; bearer/API identities
        // still get a usable shell below.
      }
      if (profile?.user) {
        setUser({
          username: profile.user.username,
          email: profile.user.email,
          telegramLinked: Boolean(profile.user.telegram_verified),
          method: info.method,
        });
      } else {
        setUser({
          username: info.username || info.subject || "Operator",
          method: info.method,
        });
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Authentication check failed");
      setAuthenticated(false);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const handleUnauthorized = () => {
      if (!requiredRef.current) return;
      setAuthenticated(false);
      setUser(null);
      setMe(null);
    };
    window.addEventListener("mm:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("mm:unauthorized", handleUnauthorized);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiPost("/auth/logout", undefined, { skipAuthEvent: true });
    } catch {
      // Always clear the local state even if the network call fails.
    }
    setAuthenticated(false);
    setUser(null);
    setMe(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      loading,
      authenticated,
      required,
      user,
      providers,
      me,
      error,
      refresh,
      logout,
    }),
    [loading, authenticated, required, user, providers, me, error, refresh, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
