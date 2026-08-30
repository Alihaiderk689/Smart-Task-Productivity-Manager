import { beforeEach, describe, expect, it, vi } from 'vitest';
import { categoriesApi, fetchPage, tasksApi } from '@/services/api';
import { base44 } from './base44Client';

vi.mock('@/services/api', () => ({
  categoriesApi: { list: vi.fn() },
  tasksApi: { list: vi.fn() },
  fetchPage: vi.fn(),
  logoutRequest: vi.fn(),
  profileRequest: vi.fn(),
  signInRequest: vi.fn(),
  signUpRequest: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

function page(results, next) {
  return { data: { count: 142, next, previous: null, results } };
}

function makeTasks(ids) {
  return ids.map((id) => ({ id, title: `Task ${id}` }));
}

describe('base44.entities.Task.list()', () => {
  it('returns every task across multiple pages, not just the first 100', async () => {
    const page1Ids = Array.from({ length: 100 }, (_, i) => i + 1);
    const page2Ids = Array.from({ length: 42 }, (_, i) => i + 101);

    tasksApi.list.mockResolvedValueOnce(page(makeTasks(page1Ids), 'https://api.example.com/api/tasks/?page=2'));
    fetchPage.mockResolvedValueOnce(page(makeTasks(page2Ids), null));

    const result = await base44.entities.Task.list();

    expect(result).toHaveLength(142);
    expect(result.map((t) => t.id)).toEqual([...page1Ids, ...page2Ids]);
    expect(fetchPage).toHaveBeenCalledWith('https://api.example.com/api/tasks/?page=2');
  });

  it('returns a single page as-is when there is no next link', async () => {
    tasksApi.list.mockResolvedValueOnce(page(makeTasks([1, 2, 3]), null));

    const result = await base44.entities.Task.list();

    expect(result).toHaveLength(3);
    expect(fetchPage).not.toHaveBeenCalled();
  });

  it('follows more than two pages until next is exhausted', async () => {
    tasksApi.list.mockResolvedValueOnce(page(makeTasks([1]), 'https://api.example.com/api/tasks/?page=2'));
    fetchPage
      .mockResolvedValueOnce(page(makeTasks([2]), 'https://api.example.com/api/tasks/?page=3'))
      .mockResolvedValueOnce(page(makeTasks([3]), null));

    const result = await base44.entities.Task.list();

    expect(result.map((t) => t.id)).toEqual([1, 2, 3]);
    expect(fetchPage).toHaveBeenCalledTimes(2);
  });
});

describe('base44.entities.Category.list()', () => {
  it('returns every category across multiple pages', async () => {
    categoriesApi.list.mockResolvedValueOnce(
      page([{ id: 1, name: 'A' }], 'https://api.example.com/api/categories/?page=2')
    );
    fetchPage.mockResolvedValueOnce(page([{ id: 2, name: 'B' }], null));

    const result = await base44.entities.Category.list();

    expect(result).toEqual([{ id: 1, name: 'A' }, { id: 2, name: 'B' }]);
  });
});
