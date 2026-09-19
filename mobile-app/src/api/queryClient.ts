import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
      staleTime: 10_000,
    },
    // A lost response does not mean a creation failed on the server.
    mutations: { retry: false },
  },
});
