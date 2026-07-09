// Minimal frontend auth helpers using fetch and localStorage

const API_ROOT = 'http://127.0.0.1:8000/api';

export async function signup(firstName, email, password) {
  const res = await fetch(`${API_ROOT}/signup/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ first_name: firstName, email, password }),
  });
  return res.json();
}

export async function login(email, password) {
  const res = await fetch(`${API_ROOT}/login/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (data.access && data.refresh) {
    localStorage.setItem('access', data.access);
    localStorage.setItem('refresh', data.refresh);
  }
  return data;
}

export function getAccess() {
  return localStorage.getItem('access');
}

export function getRefresh() {
  return localStorage.getItem('refresh');
}

export async function refreshToken() {
  const refresh = getRefresh();
  if (!refresh) throw new Error('No refresh token');
  const res = await fetch(`${API_ROOT}/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  const data = await res.json();
  if (data.access) {
    localStorage.setItem('access', data.access);
  }
  // when rotation is enabled the refresh endpoint may return a new refresh token
  if (data.refresh) localStorage.setItem('refresh', data.refresh);
  return data;
}

export async function logout() {
  const refresh = getRefresh();
  if (!refresh) return;
  await fetch(`${API_ROOT}/logout/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  localStorage.removeItem('access');
  localStorage.removeItem('refresh');
}

export async function profile() {
  const access = getAccess();
  const res = await fetch(`${API_ROOT}/profile/`, {
    headers: { Authorization: `Bearer ${access}` },
  });
  if (res.status === 401) {
    // try refreshing once
    await refreshToken();
    const newAccess = getAccess();
    return fetch(`${API_ROOT}/profile/`, { headers: { Authorization: `Bearer ${newAccess}` } }).then(r => r.json());
  }
  return res.json();
}
