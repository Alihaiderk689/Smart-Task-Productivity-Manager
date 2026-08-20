/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  bootstrapSession,
  getAccessToken,
  googleLoginRequest,
  logoutRequest,
  profileRequest,
  setAccessToken,
  signInRequest,
  signUpRequest,
} from "../services/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessTokenState] = useState(getAccessToken());
  const [isLoadingAuth, setIsLoadingAuth] = useState(true);
  const [isLoadingPublicSettings] = useState(false);
  const [authError, setAuthError] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);

  // There's nothing left in persistent client storage to read synchronously
  // on load (see services/api.js) -- resuming a session now means asking
  // the backend to trade the HttpOnly refresh cookie, if any, for a fresh
  // access token, then fetching the profile with it. A user with no
  // existing session just gets a quick "not authenticated" from this same
  // round trip.
  const checkUserAuth = useCallback(async () => {
    setIsLoadingAuth(true);
    setAuthError(null);

    const token = await bootstrapSession();

    if (!token) {
      setUser(null);
      setAccessTokenState(null);
      setIsLoadingAuth(false);
      setAuthChecked(true);
      return null;
    }

    try {
      const profile = await profileRequest();
      setUser(profile);
      setAccessTokenState(token);
      setAuthChecked(true);
      return profile;
    } catch (error) {
      setAccessToken(null);
      setUser(null);
      setAccessTokenState(null);
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
    return profile;
  }, []);

  const signIn = useCallback(async (credentials) => {
    const data = await signInRequest(credentials);
    setUser(data.user);
    setAccessTokenState(data.access);
    setAuthError(null);
    setAuthChecked(true);
    return data;
  }, []);

  const signUp = useCallback(async (credentials) => {
    // signup doesn't log the account in -- it requires OTP verification
    // first (see users/views.py::signup) -- so there's no access token to
    // store here yet.
    const data = await signUpRequest(credentials);
    setUser(data.user);
    setAuthError(null);
    setAuthChecked(true);
    return data;
  }, []);

  // `credential` is the ID token handed back by Google's Sign In With Google
  // button (see GoogleLoginButton) -- the backend verifies it and returns the
  // same { user, access } shape as signIn (the refresh token never appears
  // in this response body -- see services/api.js).
  const signInWithGoogle = useCallback(async (credential) => {
    const data = await googleLoginRequest(credential);
    setUser(data.user);
    setAccessTokenState(data.access);
    setAuthError(null);
    setAuthChecked(true);
    return data;
  }, []);

  // Hydrates the session from an { user, access } payload returned by an
  // endpoint other than /login/ (e.g. email verification, password reset)
  // -- the access token itself was already stored in memory by the api.js
  // call that produced `data`; this just syncs React state to match.
  const applySession = useCallback((data) => {
    setUser(data.user);
    setAccessTokenState(data.access);
    setAuthError(null);
    setAuthChecked(true);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      setUser(null);
      setAccessTokenState(null);
    }
  }, []);

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
      isAuthenticated: Boolean(accessToken),
      authReady: !isLoadingAuth,
      isLoadingAuth,
      isLoadingPublicSettings,
      authError,
      authChecked,
      signIn,
      signUp,
      signInWithGoogle,
      signOut,
      syncProfile,
      checkUserAuth,
      logout,
      navigateToLogin,
      applySession,
    }),
    [
      user,
      accessToken,
      isLoadingAuth,
      isLoadingPublicSettings,
      authError,
      authChecked,
      signIn,
      signUp,
      signInWithGoogle,
      signOut,
      syncProfile,
      checkUserAuth,
      logout,
      navigateToLogin,
      applySession,
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
