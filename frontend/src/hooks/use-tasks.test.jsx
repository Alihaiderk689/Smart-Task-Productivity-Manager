import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import { useTasksQuery, useTaskQuery } from './use-tasks';

vi.mock('@/api/base44Client', () => ({
  base44: { entities: { Task: { list: vi.fn(), get: vi.fn() }, Category: { list: vi.fn() } } },
}));

function apiError(statusCode) {
  return Object.assign(new Error(`HTTP ${statusCode}`), { response: { status: statusCode } });
}

beforeEach(() => {
  // Without this, a mock's call count (and any queued mockResolvedValueOnce/
  // mockRejectedValueOnce values) leaks across `it()` blocks, since these
  // mock functions are created once at module scope by vi.mock() above, not
  // per-test. `cleanup()` also unmounts the previous test's renderHook tree
  // so its query observer can't keep firing (e.g. a lingering retry timer)
  // into the next test's assertions.
  vi.clearAllMocks();
  cleanup();
});

function wrapper({ children }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useTasksQuery', () => {
  it('surfaces isError and the underlying error when the API call rejects', async () => {
    const apiError = Object.assign(new Error('Network Error'), {
      response: { status: 500, data: { detail: 'Internal server error' } },
    });
    base44.entities.Task.list.mockRejectedValueOnce(apiError);

    const { result } = renderHook(() => useTasksQuery(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBe(apiError);
    expect(result.current.data).toBeUndefined();
  });

  it('returns the task list on success', async () => {
    base44.entities.Task.list.mockResolvedValueOnce([{ id: 1, title: 'Task 1' }]);

    const { result } = renderHook(() => useTasksQuery(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual([{ id: 1, title: 'Task 1' }]);
  });
});

// useTaskQuery's own retry option overrides the QueryClient's retry:false
// default (a query-level option always wins over the client default), so
// these exercise the real retry function, not a suppressed one.
describe('useTaskQuery retry policy', () => {
  it('does not retry a 404 -- task.get is called exactly once', async () => {
    base44.entities.Task.get.mockRejectedValue(apiError(404));

    const { result } = renderHook(() => useTaskQuery(42), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(base44.entities.Task.get).toHaveBeenCalledTimes(1);
  });

  it('does not retry a 401 -- apiClient already handled the refresh/replay, a query-level retry is redundant', async () => {
    base44.entities.Task.get.mockRejectedValue(apiError(401));

    const { result } = renderHook(() => useTaskQuery(42), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(base44.entities.Task.get).toHaveBeenCalledTimes(1);
  });

  it('retries exactly once (matching the app-wide default) on a transient 500', async () => {
    base44.entities.Task.get.mockRejectedValueOnce(apiError(500));
    base44.entities.Task.get.mockResolvedValueOnce({ id: 42, title: 'Recovered' });

    const { result } = renderHook(() => useTaskQuery(42), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 3000 });

    expect(base44.entities.Task.get).toHaveBeenCalledTimes(2);
    expect(result.current.data).toEqual({ id: 42, title: 'Recovered' });
  });
});
