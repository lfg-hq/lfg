'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { buildApiUrl } from '@/app/lib/config';

interface AuthTokens {
  access: string;
  refresh: string;
}

interface UserProfile {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
}

interface ProfileData {
  email_verified?: boolean;
  subscription_plan_name?: string;
  total_tokens_used?: number;
  org_mode_enabled?: boolean;
}

interface AuthContextValue {
  user: UserProfile | null;
  profile: ProfileData | null;
  accessToken: string | null;
  loading: boolean;
  login: (credentials: { email: string; password: string }) => Promise<void>;
  register: (payload: { username: string; email: string; password: string; password2: string }) => Promise<void>;
  completeOAuth: (payload: AuthResponsePayload) => Promise<void>;
  logout: () => Promise<void>;
  fetchWithAuth: (input: RequestInfo, init?: RequestInit, retryOnAuthError?: boolean) => Promise<Response>;
}

interface AuthResponsePayload {
  user: UserProfile;
  profile?: ProfileData | null;
  tokens: AuthTokens;
}

interface StoredSession {
  tokens: AuthTokens;
  user: UserProfile;
  profile: ProfileData | null;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const SESSION_STORAGE_KEY = 'lfg-auth-session';

function readStoredSession(): StoredSession | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredSession;
  } catch (error) {
    console.warn('Failed to parse auth session from storage', error);
    return null;
  }
}

function writeStoredSession(session: StoredSession | null) {
  if (typeof window === 'undefined') {
    return;
  }
  if (!session) {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [tokens, setTokens] = useState<AuthTokens | null>(null);
  const [loading, setLoading] = useState(true);

  const storeSession = useCallback((payload: AuthResponsePayload | null) => {
    if (!payload) {
      setTokens(null);
      setUser(null);
      setProfile(null);
      writeStoredSession(null);
      return;
    }

    setTokens(payload.tokens);
    setUser(payload.user);
    setProfile(payload.profile ?? null);
    writeStoredSession({ tokens: payload.tokens, user: payload.user, profile: payload.profile ?? null });
  }, []);

  const refreshAccessToken = useCallback(async () => {
    if (!tokens?.refresh) {
      throw new Error('Missing refresh token');
    }

    const response = await fetch(buildApiUrl('auth/refresh/'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh: tokens.refresh }),
    });

    if (!response.ok) {
      throw new Error('Failed to refresh token');
    }

    const data = (await response.json()) as { access: string };
    const nextTokens: AuthTokens = { access: data.access, refresh: tokens.refresh };
    setTokens(nextTokens);
    if (user || profile) {
      writeStoredSession({ tokens: nextTokens, user: user as UserProfile, profile: profile ?? null });
    }
    return nextTokens.access;
  }, [tokens, user, profile]);

  const fetchWithAuth = useCallback<AuthContextValue['fetchWithAuth']>(
    async (input, init = {}, retryOnAuthError = true) => {
      if (!tokens?.access) {
        throw new Error('Not authenticated');
      }

      const headers = new Headers(init.headers ?? {});
      if (!headers.has('Authorization')) {
        headers.set('Authorization', `Bearer ${tokens.access}`);
      }

      if (init.body && !(init.body instanceof FormData)) {
        headers.set('Content-Type', headers.get('Content-Type') ?? 'application/json');
      }

      const response = await fetch(input, { ...init, headers });

      if (response.status !== 401 || !retryOnAuthError) {
        return response;
      }

      try {
        const newAccess = await refreshAccessToken();
        const retryHeaders = new Headers(init.headers ?? {});
        retryHeaders.set('Authorization', `Bearer ${newAccess}`);
        if (init.body && !(init.body instanceof FormData)) {
          retryHeaders.set('Content-Type', retryHeaders.get('Content-Type') ?? 'application/json');
        }
        return await fetch(input, { ...init, headers: retryHeaders });
      } catch (error) {
        storeSession(null);
        throw error;
      }
    },
    [tokens?.access, refreshAccessToken, storeSession]
  );

  const loadSessionFromStorage = useCallback(() => {
    const stored = readStoredSession();
    if (stored) {
      setTokens(stored.tokens);
      setUser(stored.user);
      setProfile(stored.profile);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadSessionFromStorage();
  }, [loadSessionFromStorage]);

  const login = useCallback<AuthContextValue['login']>(
    async ({ email, password }) => {
      const response = await fetch(buildApiUrl('auth/login/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.error || 'Unable to login');
      }

      const payload: AuthResponsePayload = {
        user: data.user,
        profile: data.profile,
        tokens: data.tokens,
      };

      storeSession(payload);
    },
    [storeSession]
  );

  const register = useCallback<AuthContextValue['register']>(
    async ({ username, email, password, password2 }) => {
      const response = await fetch(buildApiUrl('auth/register/'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password, password2 }),
      });

      const data = await response.json();
      if (!response.ok) {
        const errorMessage = typeof data === 'object' ? JSON.stringify(data) : 'Registration failed';
        throw new Error(errorMessage);
      }

      const payload: AuthResponsePayload = {
        user: data.user,
        profile: data.profile ?? null,
        tokens: data.tokens,
      };

      storeSession(payload);
    },
    [storeSession]
  );

  const completeOAuth = useCallback<AuthContextValue['completeOAuth']>(
    async (payload) => {
      storeSession(payload);
    },
    [storeSession]
  );

  const logout = useCallback(async () => {
    if (tokens?.refresh) {
      try {
        await fetch(buildApiUrl('auth/logout/'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tokens.access}` },
          body: JSON.stringify({ refresh_token: tokens.refresh }),
        });
      } catch (error) {
        console.warn('Failed to logout cleanly', error);
      }
    }
    storeSession(null);
  }, [tokens, storeSession]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      profile,
      accessToken: tokens?.access ?? null,
      loading,
      login,
      register,
      completeOAuth,
      logout,
      fetchWithAuth,
    }),
    [user, profile, tokens?.access, loading, login, register, completeOAuth, logout, fetchWithAuth]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
