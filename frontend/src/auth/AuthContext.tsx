import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { TOKEN_KEY } from "../api/client";
import {
  type AuthUser,
  changePasswordRequest,
  forgotPasswordRequest,
  loginRequest,
  logoutRequest,
  meRequest,
  resetPasswordRequest,
  updateProfileRequest,
} from "../api/auth";

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  forgotPassword: (email: string) => ReturnType<typeof forgotPasswordRequest>;
  resetPassword: (token: string, newPassword: string) => ReturnType<typeof resetPasswordRequest>;
  // Profile — updates `user` in place from the response so every screen
  // reading it (sidebar, topbar, profile card) reflects the change
  // immediately, with no full-page reload or extra /auth/me round-trip.
  updateProfile: (updates: { full_name?: string; email?: string }) => Promise<AuthUser>;
  changePassword: (currentPassword: string, newPassword: string) => ReturnType<typeof changePasswordRequest>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const restoreSession = useCallback(async () => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const me = await meRequest();
      setUser(me);
    } catch {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    restoreSession();
    const onUnauthorized = () => setUser(null);
    window.addEventListener("terraguard:unauthorized", onUnauthorized);
    return () => window.removeEventListener("terraguard:unauthorized", onUnauthorized);
  }, [restoreSession]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await loginRequest(email, password);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    setUser({ email: res.email || email, full_name: res.full_name, role: res.role });
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    localStorage.removeItem(TOKEN_KEY);
    setUser(null);
  }, []);

  const updateProfile = useCallback(async (updates: { full_name?: string; email?: string }) => {
    const res = await updateProfileRequest(updates);
    // An email change re-issues a JWT (the old one's `sub` no longer
    // resolves to any account) — swap it in immediately so the session
    // keeps working with no re-login and no reload.
    if (res.access_token) {
      localStorage.setItem(TOKEN_KEY, res.access_token);
    }
    const updated: AuthUser = {
      id: res.id,
      email: res.email,
      full_name: res.full_name,
      role: res.role,
      is_active: res.is_active,
      last_seen: res.last_seen,
      created_at: res.created_at,
    };
    setUser(updated);
    return updated;
  }, []);

  const changePassword = useCallback(
    (currentPassword: string, newPassword: string) => changePasswordRequest(currentPassword, newPassword),
    []
  );

  const refreshUser = useCallback(async () => {
    const me = await meRequest();
    setUser(me);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: !!user,
      isLoading,
      login,
      logout,
      forgotPassword: forgotPasswordRequest,
      resetPassword: resetPasswordRequest,
      updateProfile,
      changePassword,
      refreshUser,
    }),
    [user, isLoading, login, logout, updateProfile, changePassword, refreshUser]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
