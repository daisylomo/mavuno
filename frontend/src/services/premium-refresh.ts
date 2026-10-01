import type { Entitlements } from './social-contracts';

/** Verify a possible renewal before sending a subscriber back to the paywall. */
export async function refreshPremiumEntitlements(api: {
  entitlements: () => Promise<Entitlements>;
  syncStorePurchases: () => Promise<Entitlements>;
}): Promise<Entitlements> {
  const current = await api.entitlements();
  if (current.premium || !current.purchases_available) return current;
  // A delayed webhook can leave an expired period in the database. Only the
  // backend's fresh RevenueCat verification may unlock the next period.
  return api.syncStorePurchases();
}
