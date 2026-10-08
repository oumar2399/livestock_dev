import { QueryClient } from '@tanstack/react-query';

import { retryUnlessClientError } from './queryPolicy';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: retryUnlessClientError,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      staleTime: 10_000,
    },
    // A lost response does not mean a creation failed on the server.
    mutations: { retry: false },
  },
});
