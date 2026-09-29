import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  authApi,
  isBackendConfigured,
  PASSWORD_MIN_LENGTH,
  toAppRole,
  toBackendRole,
} from '../src/services/auth-api.ts';

const API = 'http://localhost:9000/api/v1';

function withApi(fn) {
  const previous = process.env.EXPO_PUBLIC_MAVUNO_API_URL;
  process.env.EXPO_PUBLIC_MAVUNO_API_URL = API;
  const originalFetch = globalThis.fetch;
  return Promise.resolve(fn())
    .finally(() => {
      globalThis.fetch = originalFetch;
      if (previous === undefined) delete process.env.EXPO_PUBLIC_MAVUNO_API_URL;
      else process.env.EXPO_PUBLIC_MAVUNO_API_URL = previous;
    });
}

function stubFetch(status, body) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init, body: init?.body ? JSON.parse(init.body) : undefined });
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  return calls;
}

const tokenResponse = {
  access_token: 'access-token-value',
  refresh_token: 'refresh-token-value',
  token_type: 'bearer',
  expires_in: 900,
  user: {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'jane@example.com',
    phone_e164: '+254712345678',
    roles: ['buyer'],
  },
};

test('the app role "customer" is sent to the backend as "buyer"', () => {
  assert.equal(toBackendRole('customer'), 'buyer');
  assert.equal(toBackendRole('farmer'), 'farmer');
  assert.equal(toBackendRole('admin'), 'buyer');
});

test('the backend roles list maps back to a single app role', () => {
  assert.equal(toAppRole(['buyer']), 'customer');
  assert.equal(toAppRole(['farmer']), 'farmer');
  assert.equal(toAppRole(['admin', 'buyer']), 'admin');
  assert.equal(toAppRole([]), 'customer');
});

test('the password minimum matches the backend RegisterRequest rule', () => {
  assert.equal(PASSWORD_MIN_LENGTH, 10);
});

test('auth is only enabled when the API URL is configured', () => {
  const previous = process.env.EXPO_PUBLIC_MAVUNO_API_URL;
  delete process.env.EXPO_PUBLIC_MAVUNO_API_URL;
  assert.equal(isBackendConfigured(), false);

  process.env.EXPO_PUBLIC_MAVUNO_API_URL = 'not-a-url';
  assert.equal(isBackendConfigured(), false, 'a malformed URL must not enable live auth');

  process.env.EXPO_PUBLIC_MAVUNO_API_URL = API;
  assert.equal(isBackendConfigured(), true);

  if (previous === undefined) delete process.env.EXPO_PUBLIC_MAVUNO_API_URL;
  else process.env.EXPO_PUBLIC_MAVUNO_API_URL = previous;
});

test('register sends the mapped role and omits blank identifiers', async () => {
  await withApi(async () => {
    const calls = stubFetch(201, tokenResponse);
    const result = await authApi.register({
      email: '  Jane@Example.com ',
      phone: '',
      password: 'a-long-password',
      role: 'customer',
    });

    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, `${API}/auth/register`);
    assert.deepEqual(calls[0].body, {
      password: 'a-long-password',
      role: 'buyer',
      email: 'jane@example.com',
    });
    assert.ok(!('phone' in calls[0].body), 'a blank phone must not be sent');
    assert.equal(result.access_token, 'access-token-value');
    assert.deepEqual(result.user.roles, ['buyer']);
  });
});

test('login posts the identifier and password the backend expects', async () => {
  await withApi(async () => {
    const calls = stubFetch(200, tokenResponse);
    await authApi.login('  jane@example.com  ', 'a-long-password');

    assert.equal(calls[0].url, `${API}/auth/login`);
    assert.deepEqual(calls[0].body, {
      identifier: 'jane@example.com',
      password: 'a-long-password',
    });
  });
});

test('backend error envelopes surface their message to the screen', async () => {
  await withApi(async () => {
    stubFetch(409, {
      error: { code: 'account_exists', message: 'That account already exists', request_id: 'r1' },
    });
    await assert.rejects(
      authApi.register({ email: 'a@b.com', phone: '', password: 'a-long-password', role: 'farmer' }),
      /That account already exists/
    );
  });
});

test('a rate limited response explains the wait instead of leaking HTTP detail', async () => {
  await withApi(async () => {
    stubFetch(429, null);
    await assert.rejects(authApi.login('jane@example.com', 'a-long-password'), /Too many attempts/);
  });
});

test('an unreachable backend produces a readable message', async () => {
  await withApi(async () => {
    globalThis.fetch = async () => {
      throw new TypeError('fetch failed');
    };
    await assert.rejects(
      authApi.login('jane@example.com', 'a-long-password'),
      /Could not reach the Mavuno server/
    );
  });
});

test('a malformed success payload is rejected rather than trusted', async () => {
  await withApi(async () => {
    stubFetch(200, { access_token: 'only-this' });
    await assert.rejects(
      authApi.login('jane@example.com', 'a-long-password'),
      /unexpected sign-in payload/
    );
  });
});

test('logout revokes the refresh token with the bearer header', async () => {
  await withApi(async () => {
    const calls = stubFetch(200, { revoked: true });
    await authApi.logout('access-token-value', 'refresh-token-value');

    assert.equal(calls[0].url, `${API}/auth/logout`);
    assert.deepEqual(calls[0].body, { refresh_token: 'refresh-token-value' });
    assert.equal(calls[0].init.headers.Authorization, 'Bearer access-token-value');
  });
});

test('a sleeping host gateway error is retried once, then explained', async () => {
  await withApi(async () => {
    const statuses = [503, 200];
    let calls = 0;
    globalThis.fetch = async () => {
      const status = statuses[calls++];
      return new Response(JSON.stringify(status === 200 ? tokenResponse : null), {
        status, headers: { 'Content-Type': 'application/json' },
      });
    };
    const signedIn = await authApi.login('jane@example.com', 'a-long-password');
    assert.equal(signedIn.user.email, 'jane@example.com');
    assert.equal(calls, 2);

    calls = 0;
    statuses.splice(0, 2, 502, 504);
    await assert.rejects(
      authApi.login('jane@example.com', 'a-long-password'),
      /starting up after being idle/
    );
    assert.equal(calls, 2);
  });
});
