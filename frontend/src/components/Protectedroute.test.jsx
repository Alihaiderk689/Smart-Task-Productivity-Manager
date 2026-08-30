import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import ProtectedRoute from './Protectedroute';

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }));

function renderProtected() {
  return render(
    <MemoryRouter initialEntries={['/tasks']}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/tasks" element={<div>Protected content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('ProtectedRoute', () => {
  it('redirects to /login when not authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: false,
      isLoadingAuth: false,
      authChecked: true,
      authError: null,
      checkUserAuth: vi.fn(),
    });

    renderProtected();

    expect(screen.getByText('Login page')).toBeInTheDocument();
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
  });

  it('renders the protected route when authenticated', () => {
    useAuth.mockReturnValue({
      isAuthenticated: true,
      isLoadingAuth: false,
      authChecked: true,
      authError: null,
      checkUserAuth: vi.fn(),
    });

    renderProtected();

    expect(screen.getByText('Protected content')).toBeInTheDocument();
  });
});
