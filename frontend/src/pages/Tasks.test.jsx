import { describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { base44 } from '@/api/base44Client';
import { renderWithProviders } from '@/test/render';
import Tasks from './Tasks';

vi.mock('@/api/base44Client', () => ({
  base44: {
    entities: {
      Task: { list: vi.fn(), start: vi.fn(), pause: vi.fn(), resume: vi.fn(), stop: vi.fn(), delete: vi.fn() },
      Category: { list: vi.fn() },
    },
  },
}));

function pendingPromise() {
  return new Promise(() => {});
}

describe('Tasks page', () => {
  it('shows a loading state before data arrives', () => {
    base44.entities.Task.list.mockReturnValue(pendingPromise());
    base44.entities.Category.list.mockReturnValue(pendingPromise());

    const { container } = renderWithProviders(<Tasks />);

    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows the empty state once loaded with no tasks', async () => {
    base44.entities.Task.list.mockResolvedValue([]);
    base44.entities.Category.list.mockResolvedValue([]);

    renderWithProviders(<Tasks />);

    expect(await screen.findByText(/No tasks found/i)).toBeInTheDocument();
  });

  it('renders task cards once loaded with tasks', async () => {
    base44.entities.Task.list.mockResolvedValue([
      {
        id: 1,
        title: 'Write report',
        status: 'Pending',
        priority: 'Medium',
        category: 1,
        start_time: new Date().toISOString(),
        end_time: new Date().toISOString(),
      },
    ]);
    base44.entities.Category.list.mockResolvedValue([{ id: 1, name: 'Work' }]);

    renderWithProviders(<Tasks />);

    expect(await screen.findByText('Write report')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/No tasks found/i)).not.toBeInTheDocument());
  });
});
