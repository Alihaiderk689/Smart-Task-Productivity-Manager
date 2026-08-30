import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { base44 } from '@/api/base44Client';
import { actionSuccessMessages } from '@/lib/taskUtils';
import { toast } from 'sonner';

export const taskKeys = {
  all: ['tasks'],
  detail: (id) => ['tasks', id],
};

export const categoryKeys = {
  all: ['categories'],
};

export function useTasksQuery() {
  return useQuery({ queryKey: taskKeys.all, queryFn: () => base44.entities.Task.list() });
}

export function useTaskQuery(id) {
  return useQuery({
    queryKey: taskKeys.detail(id),
    queryFn: () => base44.entities.Task.get(id),
    enabled: Boolean(id),
    // Matches the app-wide default (queryClientInstance's retry: 1, see
    // src/lib/query-client.jsx) -- at most one retry, same as every other
    // page -- but skips it for errors a retry can never fix: a 404 (task
    // genuinely doesn't exist / isn't this user's) and a 401 (apiClient's
    // response interceptor in services/api.js already attempts one token
    // refresh + replay per request before this ever sees the error, so a
    // query-level retry here would just trigger a second, redundant
    // refresh attempt and delay the error state for no benefit). Only
    // retries other transient failures (network blip, 500).
    // Cast to `any`: the real error is an axios error (has `.response`),
    // not TanStack Query's default `Error`-typed generic.
    retry: /** @type {any} */ ((failureCount, error) => {
      const statusCode = error?.response?.status;
      return statusCode !== 404 && statusCode !== 401 && failureCount < 1;
    }),
  });
}

export function useCategoriesQuery() {
  return useQuery({ queryKey: categoryKeys.all, queryFn: () => base44.entities.Category.list() });
}

// Shared by Tasks.jsx and TaskDetail.jsx for the dynamic start/pause/resume/
// stop buttons -- same API call shape, same toast/invalidate behavior.
export function useTaskActionMutation() {
  const queryClient = useQueryClient();
  // Cast to `any` (both the options in and the mutation result out):
  // TVariables/TError can't be inferred from a plain destructured JS
  // parameter under checkJs, and the real error is an axios error (has
  // `.response`), not the default `Error` generic.
  return /** @type {any} */ (useMutation(/** @type {any} */ ({
    mutationFn: ({ action, taskId }) => base44.entities.Task[action](taskId),
    onSuccess: (_data, { action }) => {
      toast.success(actionSuccessMessages[action] || 'Task updated');
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
    },
    onError: (err) => {
      toast.error(err.response?.data?.message || err.response?.data?.error || 'Failed to update task');
    },
  })));
}

export function useDeleteTaskMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (taskId) => base44.entities.Task.delete(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}
