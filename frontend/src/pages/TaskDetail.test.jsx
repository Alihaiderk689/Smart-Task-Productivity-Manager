import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { toast } from 'sonner';
import { base44 } from '@/api/base44Client';
import { renderWithProviders } from '@/test/render';
import TaskDetail from './TaskDetail';

vi.mock('@/api/base44Client', () => ({
  base44: {
    entities: {
      Task: { get: vi.fn(), start: vi.fn(), pause: vi.fn(), resume: vi.fn(), stop: vi.fn(), delete: vi.fn(), reschedule: vi.fn() },
      Category: { list: vi.fn() },
    },
  },
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const pendingTask = {
  id: 42,
  title: 'Write report',
  description: '',
  status: 'Pending',
  priority: 'Medium',
  category: 1,
  start_time: new Date(Date.now() + 60_000).toISOString(),
  end_time: new Date(Date.now() + 120_000).toISOString(),
  created_at: new Date().toISOString(),
};

function renderTaskDetail() {
  return renderWithProviders(
    <Routes>
      <Route path="/tasks/:id" element={<TaskDetail />} />
    </Routes>,
    { initialEntries: ['/tasks/42'] }
  );
}

describe('TaskDetail page', () => {
  it('shows the not-found state for a genuine 404, distinct from a fetch error', async () => {
    base44.entities.Task.get.mockRejectedValue(
      Object.assign(new Error('Not Found'), { response: { status: 404 } })
    );
    base44.entities.Category.list.mockResolvedValue([]);

    renderTaskDetail();

    expect(await screen.findByText('Task not found.')).toBeInTheDocument();
  });

  it('shows a retryable error state for a non-404 failure', async () => {
    base44.entities.Task.get.mockRejectedValue(
      Object.assign(new Error('Server error'), { response: { status: 500 } })
    );
    base44.entities.Category.list.mockResolvedValue([]);

    renderTaskDetail();

    // useTaskQuery's own retry logic (retry on anything but a 404) applies
    // here regardless of the test QueryClient's retry:false default -- a
    // query-level option always overrides the client-level one -- so this
    // genuinely retries with real backoff delays before settling on error.
    expect(await screen.findByRole('button', { name: /retry/i }, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.queryByText('Task not found.')).not.toBeInTheDocument();
  }, 10000);

  it('calls the start action and shows a success toast', async () => {
    base44.entities.Task.get.mockResolvedValue(pendingTask);
    base44.entities.Category.list.mockResolvedValue([{ id: 1, name: 'Work' }]);
    base44.entities.Task.start.mockResolvedValue({ ...pendingTask, status: 'In Progress' });

    renderTaskDetail();

    const startButton = await screen.findByRole('button', { name: /start/i });
    await userEvent.click(startButton);

    await waitFor(() => expect(base44.entities.Task.start).toHaveBeenCalledWith(42));
    expect(toast.success).toHaveBeenCalled();
  });
});
