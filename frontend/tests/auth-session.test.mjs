import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AuthApiError } from '../src/services/auth-api.ts';
import { refreshSession } from '../src/services/auth-session.ts';

test('outages and rate limits preserve the stored session, which can renew after recovery', async () => {
  let stored = {accessToken:'expired-access',refreshToken:'valid-refresh'};
  let invalidations=0;
  const original={...stored};
  const invalidate=async()=>{invalidations++;stored=null;};
  for(const failure of [new TypeError('offline'),new AuthApiError(500,'unavailable'),new AuthApiError(429,'rate limited'),new Error('gateway starting')]) {
    await assert.rejects(refreshSession(async()=>{throw failure;},invalidate), error=>error===failure);
    assert.deepEqual(stored,original);
  }
  const result=await refreshSession(async()=>{stored={accessToken:'renewed-access',refreshToken:'rotated-refresh'};return stored.accessToken;},invalidate);
  assert.equal(result,'renewed-access');assert.equal(invalidations,0);assert.equal(stored.refreshToken,'rotated-refresh');
});
test('rejected refresh credentials remove the session and require a new sign-in', async () => {
 for(const status of [401,403]) {
  let stored='old-credentials';
  await assert.rejects(refreshSession(async()=>{throw new AuthApiError(status,'invalid refresh');},async()=>{stored=null;}),/session expired/);
  assert.equal(stored,null);
 }
});
