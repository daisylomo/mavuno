import { apiBaseUrl, SERVER_TIMEOUT_MS, SERVER_WAKING_MESSAGE } from '@/components/customer-catalog-api';
import { userService } from './user-service';

let refreshing: Promise<string> | null = null;

export async function liveRequest<T>(path: string, options: {
  method?: string;
  body?: unknown;
  idempotencyKey?: string;
} = {}): Promise<T> {
  const base = apiBaseUrl();
  if (!base) throw new Error('The live Mavuno API is not configured.');
  const tokens = await userService.getTokens();
  if (!tokens) throw new Error('Please sign in to continue.');

  async function send(accessToken: string): Promise<Response> {
    const headers: Record<string, string> = {
      Accept: 'application/json',
      Authorization: `Bearer ${accessToken}`,
    };
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SERVER_TIMEOUT_MS);
    try {
      return await fetch(`${base}${path}`, {
        method: options.method ?? 'GET',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw new Error(SERVER_WAKING_MESSAGE);
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  let response: Response;
  try {
    response = await send(tokens.accessToken);
    if (response.status === 401) {
      const current = await userService.getTokens();
      if (current?.accessToken && current.accessToken !== tokens.accessToken) {
        response = await send(current.accessToken);
      } else {
        refreshing ??= userService.refreshAccessToken().finally(() => { refreshing = null; });
        response = await send(await refreshing);
      }
    }
  } catch (error) {
    if (error instanceof TypeError) throw new Error('Could not reach the Mavuno API. Check your connection.');
    throw error;
  }

  if ([502, 503, 504].includes(response.status)) throw new Error(SERVER_WAKING_MESSAGE);
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = body as { error?: { message?: string } } | null;
    throw new Error(envelope?.error?.message ?? `Mavuno API returned HTTP ${response.status}.`);
  }
  return body as T;
}
