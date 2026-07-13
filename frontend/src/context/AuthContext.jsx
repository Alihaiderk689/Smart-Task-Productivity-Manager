/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  clearAuthSession,
  logoutRequest,
  profileRequest,
  readAuthSession,
  setAuthSession,
  signInRequest,
  signUpRequest,
} from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const session = readAuthSession();
  const [user, setUser] = useState(session.user);
  const [accessToken, setAccessToken] = useState(session.accessToken);
  const [refreshToken, setRefreshToken] = useState(session.refreshToken);
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [isLoadingPublicSettings] = useState(false);
  const [authError, setAuthError] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  const checkUserAuth = useCallback(async () => {
    setIsLoadingAuth(true);
    setAuthError(null);

    const currentSession = readAuthSession();

    if (!currentSession.accessToken) {
      setUser(null);
      setAccessToken(null);
      setRefreshToken(null);
      setIsLoadingAuth(false);
      setAuthChecked(true);
      return null;
    }

    try {
      const profile = await profileRequest();
      setUser(profile);
      setAccessToken(currentSession.accessToken);
      setRefreshToken(currentSession.refreshToken);
      setAuthChecked(true);
      return profile;
    } catch (error) {
      clearAuthSession();
      setUser(null);
      setAccessToken(null);
      setRefreshToken(null);
      setAuthError({
        type: error.response?.status === 401 || error.response?.status === 403 ? "auth_required" : "unknown",
        message: error.response?.data?.detail || error.message || "Authentication check failed",
      });
      setAuthChecked(true);
      return null;
    } finally {
      setIsLoadingAuth(false);
    }
  }, []);

  useEffect(() => {
    void checkUserAuth();
  }, [checkUserAuth]);

  const syncProfile = useCallback(async () => {
    const profile = await profileRequest();
    setUser(profile);
    setAuthSession({ user: profile });
    return profile;
  }, []);

  const signIn = useCallback(async (credentials) => {
    const data = await signInRequest(credentials);
    setUser(data.user);
    setAccessToken(data.access);
    setRefreshToken(data.refresh);
    setAuthSession(data);
    setAuthError(null);
    setAuthChecked(true);
    return data;
  }, []);

  const signUp = useCallback(async (credentials) => {
    const data = await signUpRequest(credentials);
    setUser(data.user);
    setAccessToken(data.access);
    setRefreshToken(data.refresh);
    setAuthSession(data);
    setAuthError(null);
    setAuthChecked(true);
    return data;
  }, []);

  const signOut = useCallback(async () => {
    try {
      if (refreshToken) {
        await logoutRequest(refreshToken);
      }
    } finally {
      clearAuthSession();
      setUser(null);
      setAccessToken(null);
      setRefreshToken(null);
    }
  }, [refreshToken]);

  const logout = useCallback(async (shouldRedirect = true) => {
    await signOut();

    if (shouldRedirect) {
      window.location.href = "/login";
    }
  }, [signOut]);

  const navigateToLogin = useCallback(() => {
    const from = `${window.location.pathname}${window.location.search}`;
    window.location.href = from && from !== "/" ? `/login?from=${encodeURIComponent(from)}` : "/login";
  }, []);

  const value = useMemo(
    () => ({
      user,
      accessToken,
      refreshToken,
      isAuthenticated: Boolean(accessToken),
      authReady: !isLoadingAuth,
      isLoadingAuth,
      isLoadingPublicSettings,
      authError,
      authChecked,
      signIn,
      signUp,
      signOut,
      syncProfile,
      checkUserAuth,
      logout,
      navigateToLogin,
    }),
    [
      user,
      accessToken,
      refreshToken,
      isLoadingAuth,
      isLoadingPublicSettings,
      authError,
      authChecked,
      signIn,
      signUp,
      signOut,
      syncProfile,
      checkUserAuth,
      logout,
      navigateToLogin,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  return context;
}