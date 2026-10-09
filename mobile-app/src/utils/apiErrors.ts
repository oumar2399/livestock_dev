import { ApiError, NetworkError } from '../api/client';
import { showDialog } from '../components/dialog';

/**
 * Error dialogs: a title saying what kind of failure it is, and the server's reason
 * as the message. Never a bare "Error".
 */
export function apiErrorTitle(error: unknown, fallbackTitle = 'Something went wrong'): string {
  if (error instanceof NetworkError) return 'No connection';
  if (error instanceof ApiError) {
    if (error.status === 403) return 'Not allowed';
    if (error.status === 404) return 'Not found';
    if (error.status === 409) return 'Conflict';
    if (error.status === 400 || error.status === 422) return 'Could not save';
    if (error.status === 401) return 'Not signed in';
    if (error.status >= 500) return 'Server error';
  }
  return fallbackTitle;
}

export function apiErrorMessage(error: unknown, fallbackMessage: string): string {
  if (error instanceof Error && error.message) return error.message;
  return fallbackMessage;
}

export function showApiError(error: unknown, fallbackTitle: string, fallbackMessage: string): void {
  showDialog(apiErrorTitle(error, fallbackTitle), apiErrorMessage(error, fallbackMessage));
}
