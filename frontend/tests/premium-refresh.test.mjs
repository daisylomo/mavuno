import assert from 'node:assert/strict';
import { test } from 'node:test';
import { refreshPremiumEntitlements } from '../src/services/premium-refresh.ts';

const standard = { premium: false, features: [], provider: null, expires_at: null, purchases_available: true };
const renewed = { ...standard, premium: true, features: ['prebooking'], provider: 'revenuecat' };

test('a delayed renewal webhook is reconciled before showing the upgrade screen', async () => {
  const result = await refreshPremiumEntitlements({
    entitlements: async () => standard,
    syncStorePurchases: async () => renewed,
  });
  assert.deepEqual(result, renewed);
});

test('an expired or absent store purchase does not unlock Premium', async () => {
  assert.deepEqual(await refreshPremiumEntitlements({
    entitlements: async () => standard,
    syncStorePurchases: async () => standard,
  }), standard);
});

test('active Premium and disabled store purchases do not trigger verification', async () => {
  for (const current of [renewed, { ...standard, purchases_available: false }]) {
    assert.deepEqual(await refreshPremiumEntitlements({
      entitlements: async () => current,
      syncStorePurchases: async () => assert.fail('Unexpected store verification'),
    }), current);
  }
});

test('verification failures surface for retry instead of silently downgrading', async () => {
  await assert.rejects(refreshPremiumEntitlements({
    entitlements: async () => standard,
    syncStorePurchases: async () => { throw new Error('Store temporarily unavailable'); },
  }), /Store temporarily unavailable/);
});
