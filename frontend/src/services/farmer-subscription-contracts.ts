export type FarmerTierCode = 'starter' | 'plus' | 'biashara';
export type BillingInterval = 'month' | 'year';

export interface TierFeature {
  title: string;
  subtitle: string;
  included: boolean;
  icon: string;
}

export interface FarmerTierPlan {
  tier: FarmerTierCode;
  code: string;
  name: string;
  tagline: string;
  monthlyPrice: number;
  annualPrice: number;
  currency: 'KES';
  maxListings: number;
  commissionRate: number; // e.g. 0.10 for 10%
  commissionLabel: string;
  badge: string;
  features: string[]; // backend features: 'prebooking', 'insights'
  featureList: TierFeature[];
  recommended?: boolean;
}

export interface ActiveFarmerSubscription {
  tier: FarmerTierCode;
  planId: string;
  planCode: string;
  planName: string;
  billingInterval: BillingInterval;
  amount: number;
  currency: 'KES';
  accountReference: string;
  status: 'active' | 'pending' | 'canceled' | 'expired';
  startedAt: string;
  expiresAt: string;
  isVerified: boolean;
  provider: 'mpesa' | 'revenuecat' | 'backend' | 'offline_demo';
}

export const FARMER_PLANS: Record<FarmerTierCode, FarmerTierPlan> = {
  starter: {
    tier: 'starter',
    code: 'mkulima-starter',
    name: 'Mkulima Starter',
    tagline: 'Ideal for smallholders beginning direct farm-to-table sales',
    monthlyPrice: 0,
    annualPrice: 0,
    currency: 'KES',
    maxListings: 3,
    commissionRate: 0.10,
    commissionLabel: '10% Platform Fee',
    badge: 'Free Tier',
    features: [],
    featureList: [
      {
        title: 'Up to 3 Active Listings',
        subtitle: 'Publish up to 3 fresh harvest items in the catalog',
        included: true,
        icon: '🌱',
      },
      {
        title: 'Standard Marketplace Visibility',
        subtitle: 'Listed in regional produce searches',
        included: true,
        icon: '🔍',
      },
      {
        title: 'Customer Order Management',
        subtitle: 'Process customer pickup and delivery orders',
        included: true,
        icon: '📦',
      },
      {
        title: 'Standard 10% Platform Commission',
        subtitle: 'Standard transaction fee on fulfilled orders',
        included: true,
        icon: '💳',
      },
      {
        title: 'Unlimited Produce Listings',
        subtitle: 'Cap of 3 active listings per farm',
        included: false,
        icon: '♾️',
      },
      {
        title: 'Verified Farmer Badge ✅',
        subtitle: 'Build instant customer trust with verified profile',
        included: false,
        icon: '✅',
      },
      {
        title: 'Wholesale Price Benchmarks',
        subtitle: 'Access real-time commodity prices and demand data',
        included: false,
        icon: '🌾',
      },
      {
        title: 'Market Intelligence & Price Analytics',
        subtitle: 'Real-time sales and regional demand analytics',
        included: false,
        icon: '📊',
      },
      {
        title: 'Instant M-Pesa Settlement',
        subtitle: 'Standard weekly payout schedule',
        included: false,
        icon: '⚡',
      },
    ],
  },
  plus: {
    tier: 'plus',
    code: 'mkulima-plus',
    name: 'Mkulima Plus',
    tagline: 'Scale your farm with unlimited listings & wholesale price benchmarks',
    monthlyPrice: 499,
    annualPrice: 4790, // Save 20%
    currency: 'KES',
    maxListings: 999999,
    commissionRate: 0.06,
    commissionLabel: '6% Platform Fee (Save 4%)',
    badge: 'Popular ⭐',
    recommended: true,
    features: ['insights'],
    featureList: [
      {
        title: 'Unlimited Produce Listings',
        subtitle: 'Post as many seasonal harvests as you produce',
        included: true,
        icon: '♾️',
      },
      {
        title: 'Verified Farmer Badge ✅',
        subtitle: 'Distinguished green checkmark on all produce cards',
        included: true,
        icon: '✅',
      },
      {
        title: 'Wholesale Price Benchmarks 🌾',
        subtitle: 'Nairobi & regional commodity price trends and demand alerts',
        included: true,
        icon: '🌾',
      },
      {
        title: 'Priority Marketplace Ranking ⭐',
        subtitle: 'Appear higher in customer search results',
        included: true,
        icon: '⭐',
      },
      {
        title: 'Discounted 6% Platform Fee',
        subtitle: 'Keep 94% of your total revenue (save 4% per order)',
        included: true,
        icon: '💰',
      },
      {
        title: 'SMS & WhatsApp Order Alerts',
        subtitle: 'Instant alerts when customer places an order',
        included: true,
        icon: '📲',
      },
      {
        title: 'Lowest 3% Platform Fee',
        subtitle: 'Available on Mkulima Biashara tier',
        included: false,
        icon: '🏆',
      },
      {
        title: 'Instant M-Pesa Settlement',
        subtitle: '24-hour settlement schedule',
        included: false,
        icon: '⚡',
      },
    ],
  },
  biashara: {
    tier: 'biashara',
    code: 'mkulima-biashara',
    name: 'Mkulima Biashara',
    tagline: 'Commercial powerhouse with wholesale benchmarks & lowest 3% fee',
    monthlyPrice: 1499,
    annualPrice: 14390, // Save 20%
    currency: 'KES',
    maxListings: 999999,
    commissionRate: 0.03,
    commissionLabel: '3% Platform Fee (Save 7%)',
    badge: 'Commercial Pro 👑',
    features: ['insights'],
    featureList: [
      {
        title: 'All Mkulima Plus Features Included',
        subtitle: 'Unlimited listings, verified badge, wholesale benchmarks',
        included: true,
        icon: '🌟',
      },
      {
        title: 'Wholesale Price Benchmarks 🌾',
        subtitle: 'Real-time urban market benchmarks and commodity forecasts',
        included: true,
        icon: '🌾',
      },
      {
        title: 'Live Farm Analytics & Sales Insights 📊',
        subtitle: 'Real-time gross sales, volume, and order line tracking',
        included: true,
        icon: '📊',
      },
      {
        title: 'Lowest 3% Platform Commission 🏆',
        subtitle: 'Maximum profit retention: keep 97% of your revenue',
        included: true,
        icon: '💰',
      },
      {
        title: 'Instant M-Pesa Settlement ⚡',
        subtitle: 'Automated instant mobile payout immediately on handover',
        included: true,
        icon: '⚡',
      },
      {
        title: 'Featured Homepage Banner 👑',
        subtitle: 'Prominent carousel showcase across the customer marketplace',
        included: true,
        icon: '👑',
      },
      {
        title: 'Dedicated Farm Account Manager',
        subtitle: 'Direct WhatsApp/phone support & bulk commercial buyer matching',
        included: true,
        icon: '🤝',
      },
    ],
  },
};

export function getTierFromPlanCode(code?: string): FarmerTierCode {
  if (!code) return 'starter';
  const clean = code.toLowerCase();
  if (clean.includes('biashara') || clean.includes('pro') || clean.includes('commercial')) {
    return 'biashara';
  }
  if (clean.includes('plus') || clean.includes('growth')) {
    return 'plus';
  }
  return 'starter';
}

export function defaultSubscription(tier: FarmerTierCode = 'starter'): ActiveFarmerSubscription {
  const plan = FARMER_PLANS[tier];
  const now = new Date();
  const nextMonth = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
  return {
    tier,
    planId: `local-plan-${tier}`,
    planCode: plan.code,
    planName: plan.name,
    billingInterval: 'month',
    amount: plan.monthlyPrice,
    currency: 'KES',
    accountReference: `MVN-${tier.toUpperCase()}-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
    status: 'active',
    startedAt: now.toISOString(),
    expiresAt: nextMonth.toISOString(),
    isVerified: true,
    provider: 'offline_demo',
  };
}

export function isListingAllowed(
  tier: FarmerTierCode,
  currentListingCount: number
): { allowed: boolean; max: number; current: number; reason?: string } {
  const plan = FARMER_PLANS[tier];
  if (currentListingCount >= plan.maxListings) {
    return {
      allowed: false,
      max: plan.maxListings,
      current: currentListingCount,
      reason: `Your current ${plan.name} allows up to ${plan.maxListings} active listings. Upgrade to Mkulima Plus or Biashara for unlimited produce listings!`,
    };
  }
  return {
    allowed: true,
    max: plan.maxListings,
    current: currentListingCount,
  };
}

export function calculateTierCommission(tier: FarmerTierCode, orderAmount: number): {
  rate: number;
  feeAmount: number;
  netPayout: number;
  savingsVsStarter: number;
} {
  const plan = FARMER_PLANS[tier];
  const rate = plan.commissionRate;
  const starterRate = FARMER_PLANS.starter.commissionRate;
  const feeAmount = Math.round(orderAmount * rate * 100) / 100;
  const starterFee = Math.round(orderAmount * starterRate * 100) / 100;
  const netPayout = Math.round((orderAmount - feeAmount) * 100) / 100;
  const savingsVsStarter = Math.max(0, Math.round((starterFee - feeAmount) * 100) / 100);

  return {
    rate,
    feeAmount,
    netPayout,
    savingsVsStarter,
  };
}
