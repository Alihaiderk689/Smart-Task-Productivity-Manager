import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import RoleRoute from './RoleRoute';

vi.mock('@/context/AuthContext', () => ({ useAuth: vi.fn() }));

function renderWithRole(allow, initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<div>User home</div>} />
        <Route path="/admin" element={<div>Admin home</div>} />
        <Route element={<RoleRoute allow={allow} />}>
          <Route path="/tasks" element={<div>User page</div>} />
          <Route path="/admin/tasks" element={<div>Admin page</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('RoleRoute', () => {
  it('redirects a staff user away from a user-only route to /admin', () => {
    useAuth.mockReturnValue({ user: { is_staff: true } });

    renderWithRole('user', '/tasks');

    expect(screen.getByText('Admin home')).toBeInTheDocument();
    expect(screen.queryByText('User page')).not.toBeInTheDocument();
  });

  it('redirects a non-staff user away from a staff-only route to /', () => {
    useAuth.mockReturnValue({ user: { is_staff: false } });

    renderWithRole('staff', '/admin/tasks');

    expect(screen.getByText('User home')).toBeInTheDocument();
    expect(screen.queryByText('Admin page')).not.toBeInTheDocument();
  });

  it('lets a staff user reach a staff-only route', () => {
    useAuth.mockReturnValue({ user: { is_staff: true } });

    renderWithRole('staff', '/admin/tasks');

    expect(screen.getByText('Admin page')).toBeInTheDocument();
  });

  it('lets a non-staff user reach a user-only route', () => {
    useAuth.mockReturnValue({ user: { is_staff: false } });

    renderWithRole('user', '/tasks');

    expect(screen.getByText('User page')).toBeInTheDocument();
  });
});
