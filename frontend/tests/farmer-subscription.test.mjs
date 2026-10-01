import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  FARMER_PLANS,
  getTierFromPlanCode,
  defaultSubscription,
  isListingAllowed,
  calculateTierCommission,
} from '../src/services/farmer-subscription-contracts.ts';

test('farmer plans define exactly 3 distinct tiers: starter, plus, and biashara', () => {
  const tiers = Object.keys(FARMER_PLANS);
  assert.deepEqual(tiers, ['starter', 'plus', 'biashara']);

  assert.equal(FARMER_PLANS.starter.monthlyPrice, 0);
  assert.equal(FARMER_PLANS.starter.maxListings, 3);
  assert.equal(FARMER_PLANS.starter.commissionRate, 0.10);
  assert.deepEqual(FARMER_PLANS.starter.features, []);

  assert.equal(FARMER_PLANS.plus.monthlyPrice, 499);
  assert.ok(FARMER_PLANS.plus.maxListings > 1000);
  assert.equal(FARMER_PLANS.plus.commissionRate, 0.06);
  assert.deepEqual(FARMER_PLANS.plus.features, ['insights']);

  assert.equal(FARMER_PLANS.biashara.monthlyPrice, 1499);
  assert.ok(FARMER_PLANS.biashara.maxListings > 1000);
  assert.equal(FARMER_PLANS.biashara.commissionRate, 0.03);
  assert.deepEqual(FARMER_PLANS.biashara.features, ['insights']);
});

test('annual billing offers 20% discount on paid tiers', () => {
  // Plus: 499 * 12 = 5,988. 20% off is approx 4,790.
  const plusMonthly12 = FARMER_PLANS.plus.monthlyPrice * 12;
  assert.ok(FARMER_PLANS.plus.annualPrice < plusMonthly12);
  const plusDiscount = (plusMonthly12 - FARMER_PLANS.plus.annualPrice) / plusMonthly12;
  assert.ok(plusDiscount >= 0.19 && plusDiscount <= 0.21);

  // Biashara: 1,499 * 12 = 17,988. 20% off is approx 14,390.
  const biasharaMonthly12 = FARMER_PLANS.biashara.monthlyPrice * 12;
  assert.ok(FARMER_PLANS.biashara.annualPrice < biasharaMonthly12);
  const biasharaDiscount = (biasharaMonthly12 - FARMER_PLANS.biashara.annualPrice) / biasharaMonthly12;
  assert.ok(biasharaDiscount >= 0.19 && biasharaDiscount <= 0.21);
});

test('getTierFromPlanCode maps plan codes accurately to tiers', () => {
  assert.equal(getTierFromPlanCode('mkulima-starter'), 'starter');
  assert.equal(getTierFromPlanCode('farmer-starter'), 'starter');
  assert.equal(getTierFromPlanCode('mkulima-plus'), 'plus');
  assert.equal(getTierFromPlanCode('farmer-plus-annual'), 'plus');
  assert.equal(getTierFromPlanCode('growth-tier'), 'plus');
  assert.equal(getTierFromPlanCode('mkulima-biashara'), 'biashara');
  assert.equal(getTierFromPlanCode('farmer-pro'), 'biashara');
  assert.equal(getTierFromPlanCode(undefined), 'starter');
});

test('defaultSubscription returns a valid active starter plan structure', () => {
  const sub = defaultSubscription('starter');
  assert.equal(sub.tier, 'starter');
  assert.equal(sub.status, 'active');
  assert.equal(sub.amount, 0);
  assert.equal(sub.currency, 'KES');
  assert.ok(sub.accountReference.startsWith('MVN-STARTER-'));
  assert.ok(new Date(sub.expiresAt).getTime() > Date.now());
});

test('isListingAllowed enforces 3-listing cap only on Starter tier', () => {
  assert.equal(isListingAllowed('starter', 0).allowed, true);
  assert.equal(isListingAllowed('starter', 2).allowed, true);
  assert.equal(isListingAllowed('starter', 3).allowed, false);
  assert.equal(isListingAllowed('starter', 5).allowed, false);

  assert.equal(isListingAllowed('plus', 3).allowed, true);
  assert.equal(isListingAllowed('plus', 50).allowed, true);
  assert.equal(isListingAllowed('biashara', 3).allowed, true);
  assert.equal(isListingAllowed('biashara', 100).allowed, true);
});

test('calculateTierCommission computes correct fee and savings vs Starter', () => {
  const orderAmount = 10000; // KES 10,000 order

  // Starter: 10% fee = 1000, net payout = 9000, 0 savings
  const starter = calculateTierCommission('starter', orderAmount);
  assert.equal(starter.feeAmount, 1000);
  assert.equal(starter.netPayout, 9000);
  assert.equal(starter.savingsVsStarter, 0);

  // Plus: 6% fee = 600, net payout = 9400, savings = 400 (4%)
  const plus = calculateTierCommission('plus', orderAmount);
  assert.equal(plus.feeAmount, 600);
  assert.equal(plus.netPayout, 9400);
  assert.equal(plus.savingsVsStarter, 400);

  // Biashara: 3% fee = 300, net payout = 9700, savings = 700 (7%)
  const biashara = calculateTierCommission('biashara', orderAmount);
  assert.equal(biashara.feeAmount, 300);
  assert.equal(biashara.netPayout, 9700);
  assert.equal(biashara.savingsVsStarter, 700);
});
