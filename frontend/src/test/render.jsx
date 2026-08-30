import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';

// A fresh, retry-free QueryClient per render -- retries would make an
// intentionally-failing mock query take the default backoff delays before
// settling into isError, slowing every failure-path test down for nothing.
export function renderWithProviders(ui, { initialEntries = ['/'] } = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}
