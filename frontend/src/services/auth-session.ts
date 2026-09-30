import { AuthApiError } from './auth-api.ts';

/** A provider or network outage must not discard credentials that can recover later. */
export async function refreshSession<T>(renew: () => Promise<T>, invalidate: () => Promise<void>): Promise<T> {
  try {
    return await renew();
  } catch (error) {
    if (error instanceof AuthApiError && [401, 403].includes(error.status)) {
      await invalidate();
      throw new Error('Your session expired. Please sign in again.');
    }
    throw error;
  }
}
