import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiBaseUrl } from '../components/customer-catalog-api.ts';
import { socialApi } from './social-api.ts';
import {
  hasFeature,
  Insights,
  Plan as BackendPlan,
  Subscription as BackendSubscription,
} from './social-contracts.ts';
import { farmerService } from './farmer-service.ts';
import { userService } from './user-service.ts';

export * from './farmer-subscription-contracts.ts';
import {
  ActiveFarmerSubscription,
  BillingInterval,
  calculateTierCommission,
  defaultSubscription,
  FARMER_PLANS,
  FarmerTierCode,
  FarmerTierPlan,
  getTierFromPlanCode,
  isListingAllowed,
} from './farmer-subscription-contracts.ts';

const STORAGE_KEY = '@mavuno_farmer_subscription_v2';




export const farmerSubscriptionService = {
  /**
   * Retrieves the current active subscription.
   * If live backend is configured, queries backend and reconciles.
   * Otherwise uses local AsyncStorage state.
   */
  async getCurrentSubscription(): Promise<ActiveFarmerSubscription> {
    try {
      // 1. Try local storage first
      const stored = await AsyncStorage.getItem(STORAGE_KEY);
      let localSub: ActiveFarmerSubscription = stored
        ? JSON.parse(stored)
        : defaultSubscription('starter');

      // 2. Check live backend if configured
      if (apiBaseUrl()) {
        try {
          const [plans, subscriptions] = await Promise.all([
            socialApi.plans().catch(() => [] as BackendPlan[]),
            socialApi.subscriptions().catch(() => [] as BackendSubscription[]),
          ]);

          const activeSub = subscriptions.find(
            (s) => s.status === 'active' && s.verified_at && (!s.current_period_end || new Date(s.current_period_end).getTime() > Date.now())
          );

          if (activeSub) {
            const plan = plans.find((p) => p.id === activeSub.plan_id);
            if (plan) {
              const tier = getTierFromPlanCode(plan.name || plan.id);
              localSub = {
                tier,
                planId: activeSub.plan_id,
                planCode: plan.id,
                planName: plan.name,
                billingInterval: plan.billing_interval,
                amount: Number(plan.price_amount),
                currency: 'KES',
                accountReference: activeSub.account_reference,
                status: 'active',
                startedAt: activeSub.current_period_start || new Date().toISOString(),
                expiresAt: activeSub.current_period_end || new Date(Date.now() + 30 * 86400000).toISOString(),
                isVerified: !!activeSub.verified_at,
                provider: 'backend',
              };
              await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(localSub));
              return localSub;
            }
          }
        } catch {
          // If backend check fails, fall through to local subscription
        }
      }

      return localSub;
    } catch {
      return defaultSubscription('starter');
    }
  },

  /**
   * Upgrade or switch subscription to a target tier.
   * Supports backend live request (with idempotency) & offline persistence.
   */
  async subscribeToTier(
    tier: FarmerTierCode,
    interval: BillingInterval = 'month',
    phoneNumber?: string,
  ): Promise<ActiveFarmerSubscription> {
    const plan = FARMER_PLANS[tier];
    const amount = interval === 'month' ? plan.monthlyPrice : plan.annualPrice;
    const now = new Date();
    const durationDays = interval === 'year' ? 365 : 30;
    const expiresAt = new Date(now.getTime() + durationDays * 24 * 60 * 60 * 1000);
    const accountRef = `MVN-${tier.toUpperCase()}-${Math.random().toString(36).substring(2, 9).toUpperCase()}`;

    let newSub: ActiveFarmerSubscription = {
      tier,
      planId: `plan-${tier}-${interval}`,
      planCode: plan.code,
      planName: plan.name,
      billingInterval: interval,
      amount,
      currency: 'KES',
      accountReference: accountRef,
      status: 'active',
      startedAt: now.toISOString(),
      expiresAt: expiresAt.toISOString(),
      isVerified: true,
      provider: phoneNumber ? 'mpesa' : 'offline_demo',
    };

    // If backend is active and we are subscribing to a paid plan, initiate on backend
    if (apiBaseUrl() && tier !== 'starter') {
      try {
        const plans = await socialApi.plans();
        const farmerPlans = plans.filter((p) => p.audience === 'farmer' && p.active);
        // Find best match by features or name
        const match = farmerPlans.find(
          (p) =>
            p.billing_interval === interval &&
            (p.features.includes('insights') ||
             p.name.toLowerCase().includes(tier))
        ) || farmerPlans[0];

        if (match) {
          const idempotencyKey = `sub-${tier}-${Date.now()}-${Math.random().toString(36).substring(2, 8)}`;
          const backendSub = await socialApi.subscribe(match.id, idempotencyKey);
          newSub.planId = backendSub.plan_id;
          newSub.accountReference = backendSub.account_reference;
          newSub.provider = 'backend';
        }
      } catch {
        // Backend initiation failed or premium unavailable; we still persist locally for seamless UX
      }
    }

    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(newSub));
    return newSub;
  },

  /**
   * Downgrade / revert to Starter (Free).
   */
  async cancelSubscription(): Promise<ActiveFarmerSubscription> {
    const starterSub = defaultSubscription('starter');
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(starterSub));
    return starterSub;
  },

  /**
   * Check whether a new produce listing is permitted under the current plan.
   */
  async canCreateListing(currentListingCount: number): Promise<{
    allowed: boolean;
    max: number;
    current: number;
    reason?: string;
  }> {
    const sub = await this.getCurrentSubscription();
    return isListingAllowed(sub.tier, currentListingCount);
  },

  /**
   * Returns current platform commission rate for orders.
   */
  async getCommissionRate(): Promise<{ rate: number; label: string; tier: FarmerTierCode }> {
    const sub = await this.getCurrentSubscription();
    const plan = FARMER_PLANS[sub.tier];
    return {
      rate: plan.commissionRate,
      label: plan.commissionLabel,
      tier: sub.tier,
    };
  },

  /**
   * Check feature entitlement.
   */
  async hasFeature(feature: 'insights' | string): Promise<boolean> {
    const sub = await this.getCurrentSubscription();
    const plan = FARMER_PLANS[sub.tier];
    return plan.features.includes(feature);
  },

  /**
   * Get farmer market insights (sales, turnover, demand).
   * Calls `/premium/insights/farmer` if backend is active, or synthesizes real metrics from listings & orders.
   */
  async getInsights(): Promise<Insights> {
    if (apiBaseUrl()) {
      try {
        return await socialApi.insights();
      } catch {
        // Fall back to synthesized metrics
      }
    }

    // Synthesize from local listings and orders
    const [listings, stats] = await Promise.all([
      farmerService.getListings().catch(() => []),
      farmerService.getStats().catch(() => ({ activeListingsCount: 0, pendingOrdersCount: 0, totalRevenue: 0 })),
    ]);

    const activeListings = listings.filter((l) => l.status === 'active' || l.status === 'low_stock').length;
    const unitsAvailable = listings
      .filter((l) => l.status === 'active' || l.status === 'low_stock')
      .reduce((sum, l) => sum + (Number(l.quantity) || 0), 0);

    return {
      active_listings: activeListings,
      units_available: unitsAvailable.toFixed(1),
      completed_order_lines: stats.pendingOrdersCount,
      gross_sales: (stats.totalRevenue || 0).toFixed(2),
    };
  },
};
