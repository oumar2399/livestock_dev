import type { Query } from '@tanstack/react-query';

import { ApiError } from './client';

const MAX_RETRIES = 2;

/** 4xx answers will not change on retry (deleted animal, no access, bad input). */
export function isClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500;
}

/** Retry network and server errors, never client errors. */
export function retryUnlessClientError(failureCount: number, error: unknown): boolean {
  return !isClientError(error) && failureCount < MAX_RETRIES;
}

/** True when the resource is gone or no longer readable: polling must stop. */
export function isGone(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 403 || error.status === 404);
}

/** refetchInterval that stops for good once the last answer was 403/404. */
export function pollUnlessGone(intervalMs: number) {
  return (query: Query<any, any, any, any>) => (isGone(query.state.error) ? false : intervalMs);
}
