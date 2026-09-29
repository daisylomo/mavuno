import {
  apiBaseUrl,
  SERVER_TIMEOUT_MS,
  SERVER_WAKING_MESSAGE,
} from '../components/customer-catalog-api.ts';

/** The backend rejects anything shorter (see RegisterRequest in backend/src/mavuno/auth/schemas.py). */
export const PASSWORD_MIN_LENGTH = 10;

/** Gateway answers while a sleeping host starts; the request never reached the API. */
const WAKING_STATUSES = new Set([502, 503, 504]);
const WAKE_RETRY_DELAY_MS = 4_000;

/** Roles used by the Expo screens. */
export type AppRole = 'farmer' | 'customer' | 'admin';

/** Roles the backend accepts when registering. */
export type BackendRole = 'buyer' | 'farmer';

export interface BackendUser {
  id: string;
  email: string | null;
  phone_e164: string | null;
  roles: string[];
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: BackendUser;
}

export interface BackendProfile { display_name: string }

/** The app calls buyers "customer"; the backend calls them "buyer". */
export function toBackendRole(role: AppRole): BackendRole {
  return role === 'farmer' ? 'farmer' : 'buyer';
}

/** The backend returns a list of roles; the screens expect a single one. */
export function toAppRole(roles: readonly string[]): AppRole {
  if (roles.includes('administrator') || roles.includes('admin')) return 'admin';
  if (roles.includes('farmer')) return 'farmer';
  return 'customer';
}

/** True when EXPO_PUBLIC_MAVUNO_API_URL points at a running backend. */
export function isBackendConfigured(): boolean {
  try {
    return apiBaseUrl() !== null;
  } catch {
    return false;
  }
}

function requireBaseUrl(): string {
  const base = apiBaseUrl();
  if (!base) {
    throw new Error('The Mavuno API is not configured. Set EXPO_PUBLIC_MAVUNO_API_URL.');
  }
  return base;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Pulls the message out of the backend's {"error": {...}} envelope. */
function errorMessage(status: number, body: unknown): string {
  if (isRecord(body) && isRecord(body.error) && typeof body.error.message === 'string') {
    return body.error.message;
  }
  if (status === 401) return 'Incorrect credentials. Please try again.';
  if (status === 429) return 'Too many attempts. Please wait a moment and try again.';
  return `The server returned an unexpected response (HTTP ${status}).`;
}

function parseUser(value: unknown): BackendUser {
  if (!isRecord(value) || typeof value.id !== 'string' || !Array.isArray(value.roles)) {
    throw new Error('The server returned an unexpected user payload.');
  }
  const roles = value.roles.filter((role): role is string => typeof role === 'string');
  return {
    id: value.id,
    email: typeof value.email === 'string' ? value.email : null,
    phone_e164: typeof value.phone_e164 === 'string' ? value.phone_e164 : null,
    roles,
  };
}

function parseTokenResponse(value: unknown): TokenResponse {
  if (
    !isRecord(value) ||
    typeof value.access_token !== 'string' ||
    typeof value.refresh_token !== 'string' ||
    typeof value.expires_in !== 'number'
  ) {
    throw new Error('The server returned an unexpected sign-in payload.');
  }
  return {
    access_token: value.access_token,
    refresh_token: value.refresh_token,
    expires_in: value.expires_in,
    user: parseUser(value.user),
  };
}

async function request(
  path: string,
  init: { method: string; body?: unknown; accessToken?: string }
): Promise<unknown> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body !== undefined) headers['Content-Type'] = 'application/json';
  if (init.accessToken) headers.Authorization = `Bearer ${init.accessToken}`;

  async function send(): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), SERVER_TIMEOUT_MS);
    try {
      return await fetch(`${requireBaseUrl()}${path}`, {
        method: init.method,
        headers,
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
        signal: controller.signal,
      });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error(SERVER_WAKING_MESSAGE);
      }
      throw new Error('Could not reach the Mavuno server. Check your internet connection and try again.');
    } finally {
      clearTimeout(timer);
    }
  }

  let response = await send();
  if (WAKING_STATUSES.has(response.status)) {
    // The free host answers from its gateway while the API boots. The request was not
    // processed, so trying once more is safe even for registration.
    await new Promise((resolve) => setTimeout(resolve, WAKE_RETRY_DELAY_MS));
    response = await send();
    if (WAKING_STATUSES.has(response.status)) throw new Error(SERVER_WAKING_MESSAGE);
  }

  let body: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) throw new Error(errorMessage(response.status, body));
  return body;
}

export const authApi = {
  async register(params: {
    email: string;
    phone: string;
    password: string;
    role: AppRole;
  }): Promise<TokenResponse> {
    const payload: Record<string, unknown> = {
      password: params.password,
      role: toBackendRole(params.role),
    };
    // The backend needs at least one of these, and rejects empty strings.
    if (params.email.trim()) payload.email = params.email.trim().toLowerCase();
    if (params.phone.trim()) payload.phone = params.phone.trim();

    return parseTokenResponse(await request('/auth/register', { method: 'POST', body: payload }));
  },

  async login(identifier: string, password: string): Promise<TokenResponse> {
    const body = { identifier: identifier.trim(), password };
    return parseTokenResponse(await request('/auth/login', { method: 'POST', body }));
  },

  async refresh(refreshToken: string): Promise<TokenResponse> {
    return parseTokenResponse(await request('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    }));
  },

  async me(accessToken: string): Promise<BackendUser> {
    return parseUser(await request('/auth/me', { method: 'GET', accessToken }));
  },

  async profile(accessToken: string): Promise<BackendProfile> {
    const value = await request('/users/me', { method: 'GET', accessToken });
    if (!isRecord(value) || typeof value.display_name !== 'string') {
      throw new Error('The server returned an unexpected profile payload.');
    }
    return { display_name: value.display_name };
  },

  async updateDisplayName(accessToken: string, displayName: string): Promise<void> {
    await request('/users/me', {
      method: 'PATCH', body: { display_name: displayName }, accessToken,
    });
  },

  async logout(accessToken: string, refreshToken: string): Promise<void> {
    await request('/auth/logout', {
      method: 'POST',
      body: { refresh_token: refreshToken },
      accessToken,
    });
  },
};
