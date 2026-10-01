import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Platform,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Href, useFocusEffect, useRouter } from 'expo-router';
import { Colors } from '@/constants/theme';
import {
  ActiveFarmerSubscription,
  BillingInterval,
  calculateTierCommission,
  FARMER_PLANS,
  FarmerTierCode,
  FarmerTierPlan,
} from '@/services/farmer-subscription-contracts';
import { farmerSubscriptionService } from '@/services/farmer-subscription-service';
import { userService } from '@/services/user-service';
import { Insights } from '@/services/social-contracts';

const COMMODITY_TRENDS = [
  { item: 'Tomatoes (kg)', avgPrice: 'KES 95/kg', trend: '+12% this week', direction: 'up' },
  { item: 'Hass Avocados (kg)', avgPrice: 'KES 140/kg', trend: '+8% high demand', direction: 'up' },
  { item: 'Sukuma Wiki (bunch)', avgPrice: 'KES 35/bunch', trend: 'Stable supply', direction: 'neutral' },
  { item: 'Potatoes (bag 50kg)', avgPrice: 'KES 3,200/bag', trend: '-5% supply peak', direction: 'down' },
  { item: 'Sweet Mangoes (kg)', avgPrice: 'KES 110/kg', trend: '+15% export demand', direction: 'up' },
];

export default function FarmerSubscriptionScreen() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [subscription, setSubscription] = useState<ActiveFarmerSubscription | null>(null);
  const [billingInterval, setBillingInterval] = useState<BillingInterval>('month');
  const [insights, setInsights] = useState<Insights | null>(null);
  const [activeTab, setActiveTab] = useState<'plans' | 'insights'>('plans');

  // Checkout Modal State
  const [checkoutModalVisible, setCheckoutModalVisible] = useState(false);
  const [selectedPlanForUpgrade, setSelectedPlanForUpgrade] = useState<FarmerTierPlan | null>(null);
  const [mpesaPhone, setMpesaPhone] = useState('');
  const [isProcessingPayment, setIsProcessingPayment] = useState(false);
  const [paymentSuccessMessage, setPaymentSuccessMessage] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const [currentSub, currentUser] = await Promise.all([
        farmerSubscriptionService.getCurrentSubscription(),
        userService.getCurrentUser(),
      ]);
      setSubscription(currentSub);
      setBillingInterval(currentSub.billingInterval || 'month');
      if (currentUser?.phone) {
        setMpesaPhone(currentUser.phone);
      }

      // If entitled (Plus or Biashara), load real insights
      if (currentSub.tier === 'plus' || currentSub.tier === 'biashara') {
        const ins = await farmerSubscriptionService.getInsights();
        setInsights(ins);
      }
    } catch (err) {
      console.warn('Error loading subscription data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [])
  );

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleSelectUpgrade = (plan: FarmerTierPlan) => {
    if (plan.tier === subscription?.tier && billingInterval === subscription?.billingInterval) {
      return; // Already on this plan
    }

    if (plan.tier === 'starter') {
      // Downgrade to Free
      const confirmDowngrade = async () => {
        setLoading(true);
        try {
          const downgraded = await farmerSubscriptionService.cancelSubscription();
          setSubscription(downgraded);
          Alert.alert(
            'Plan Updated',
            'Your account is now on the Mkulima Starter plan. Up to 3 active listings permitted.',
            [{ text: 'OK' }]
          );
        } catch {
          Alert.alert('Error', 'Could not update plan. Please try again.');
        } finally {
          setLoading(false);
        }
      };

      if (Platform.OS === 'web') {
        if (window.confirm('Downgrade to Starter plan? You will lose unlimited listings and verified badge.')) {
          confirmDowngrade();
        }
      } else {
        Alert.alert(
          'Downgrade to Starter',
          'Are you sure you want to switch to the free Mkulima Starter plan? Your active listings will be capped at 3.',
          [
            { text: 'Keep Current Plan', style: 'cancel' },
            { text: 'Confirm Downgrade', style: 'destructive', onPress: confirmDowngrade },
          ]
        );
      }
      return;
    }

    // Open M-Pesa Checkout Modal for Plus or Biashara
    setSelectedPlanForUpgrade(plan);
    setCheckoutModalVisible(true);
  };

  const handleConfirmMpesaPayment = async () => {
    if (!selectedPlanForUpgrade) return;
    const phone = mpesaPhone.trim();
    if (!phone || phone.length < 9) {
      Alert.alert('Phone Required', 'Please enter a valid Safaricom phone number for M-Pesa STK Push.');
      return;
    }

    setIsProcessingPayment(true);
    try {
      // Simulate / send STK push and record subscription
      await new Promise((resolve) => setTimeout(resolve, 1400));
      const updated = await farmerSubscriptionService.subscribeToTier(
        selectedPlanForUpgrade.tier,
        billingInterval,
        phone
      );
      setSubscription(updated);
      setPaymentSuccessMessage(
        `🎉 Payment of KES ${billingInterval === 'month' ? selectedPlanForUpgrade.monthlyPrice : selectedPlanForUpgrade.annualPrice} received! Welcome to ${selectedPlanForUpgrade.name}.`
      );

      // Refresh insights if unlocked
      if (selectedPlanForUpgrade.tier === 'plus' || selectedPlanForUpgrade.tier === 'biashara') {
        const ins = await farmerSubscriptionService.getInsights();
        setInsights(ins);
      }

      setTimeout(() => {
        setPaymentSuccessMessage(null);
        setCheckoutModalVisible(false);
        setSelectedPlanForUpgrade(null);
      }, 1600);
    } catch {
      Alert.alert('Payment Error', 'Could not process subscription. Please check connection and try again.');
    } finally {
      setIsProcessingPayment(false);
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color={Colors.brandGreen} />
        <Text style={styles.loadingText}>Loading farmer plans...</Text>
      </View>
    );
  }

  const currentTier = subscription?.tier || 'starter';
  const currentPlan = FARMER_PLANS[currentTier];

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.contentContainer}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={[Colors.brandGreen]} />}>
      
      {/* Top Banner: Current Membership */}
      <View style={styles.currentPlanBanner}>
        <View style={styles.currentPlanHeader}>
          <View>
            <Text style={styles.currentPlanLabel}>CURRENT MEMBERSHIP</Text>
            <Text style={styles.currentPlanTitle}>{currentPlan.name}</Text>
          </View>
          <View style={[styles.badgePill, currentTier === 'biashara' ? styles.badgeGold : currentTier === 'plus' ? styles.badgeGreen : styles.badgeGray]}>
            <Text style={styles.badgePillText}>
              {currentTier === 'biashara' ? '👑 PRO BIASHARA' : currentTier === 'plus' ? '⭐ PLUS MEMBER' : '🌱 FREE TIER'}
            </Text>
          </View>
        </View>

        <View style={styles.planSpecsRow}>
          <View style={styles.specItem}>
            <Text style={styles.specValue}>
              {currentPlan.maxListings > 1000 ? 'Unlimited' : `${currentPlan.maxListings} Listings`}
            </Text>
            <Text style={styles.specLabel}>Catalog Capacity</Text>
          </View>
          <View style={styles.specDivider} />
          <View style={styles.specItem}>
            <Text style={[styles.specValue, { color: Colors.brandGreen }]}>{currentPlan.commissionLabel}</Text>
            <Text style={styles.specLabel}>Platform Fee</Text>
          </View>
          <View style={styles.specDivider} />
          <View style={styles.specItem}>
            <Text style={styles.specValue}>
              {subscription?.expiresAt
                ? new Date(subscription.expiresAt).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
                : 'Active'}
            </Text>
            <Text style={styles.specLabel}>Valid Through</Text>
          </View>
        </View>
      </View>

      {/* Navigation Tabs */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tabButton, activeTab === 'plans' && styles.tabButtonActive]}
          onPress={() => setActiveTab('plans')}>
          <Text style={[styles.tabButtonText, activeTab === 'plans' && styles.tabButtonTextActive]}>
            📋 Plans & Pricing
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tabButton, activeTab === 'insights' && styles.tabButtonActive]}
          onPress={() => setActiveTab('insights')}>
          <Text style={[styles.tabButtonText, activeTab === 'insights' && styles.tabButtonTextActive]}>
            🌾 Wholesale Benchmark & Analytics
          </Text>
        </TouchableOpacity>
      </View>

      {/* TAB 1: PLANS & PRICING */}
      {activeTab === 'plans' && (
        <View>
          {/* Billing Switcher */}
          <View style={styles.billingToggleSection}>
            <Text style={styles.billingToggleTitle}>Select Billing Period</Text>
            <View style={styles.toggleRow}>
              <TouchableOpacity
                style={[styles.toggleOption, billingInterval === 'month' && styles.toggleOptionActive]}
                onPress={() => setBillingInterval('month')}>
                <Text style={[styles.toggleText, billingInterval === 'month' && styles.toggleTextActive]}>
                  Monthly Billing
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.toggleOption, billingInterval === 'year' && styles.toggleOptionActive]}
                onPress={() => setBillingInterval('year')}>
                <Text style={[styles.toggleText, billingInterval === 'year' && styles.toggleTextActive]}>
                  Annual (Save 20% 🎉)
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* 3 Tier Cards */}
          {(['starter', 'plus', 'biashara'] as FarmerTierCode[]).map((tierKey) => {
            const plan = FARMER_PLANS[tierKey];
            const isCurrent = currentTier === tierKey && subscription?.billingInterval === billingInterval;
            const price = billingInterval === 'month' ? plan.monthlyPrice : plan.annualPrice;
            const isPlus = tierKey === 'plus';
            const isBiashara = tierKey === 'biashara';

            return (
              <View
                key={tierKey}
                style={[
                  styles.tierCard,
                  isPlus && styles.tierCardPlus,
                  isBiashara && styles.tierCardBiashara,
                  isCurrent && styles.tierCardCurrent,
                ]}>
                
                {/* Header Tag / Badge */}
                {plan.recommended && (
                  <View style={styles.recommendedBadge}>
                    <Text style={styles.recommendedBadgeText}>MOST POPULAR FOR GROWING FARMS ⭐</Text>
                  </View>
                )}
                {isBiashara && (
                  <View style={styles.biasharaBadge}>
                    <Text style={styles.biasharaBadgeText}>BEST VALUE FOR COMMERCIAL PROS 👑</Text>
                  </View>
                )}

                <View style={styles.tierHeaderRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.tierName}>{plan.name}</Text>
                    <Text style={styles.tierTagline}>{plan.tagline}</Text>
                  </View>
                  <View style={styles.priceContainer}>
                    <Text style={styles.priceCurrency}>{plan.currency}</Text>
                    <Text style={styles.priceNumber}>{price.toLocaleString()}</Text>
                    <Text style={styles.pricePeriod}>
                      /{billingInterval === 'month' ? 'month' : 'year'}
                    </Text>
                  </View>
                </View>

                {/* Savings & Rate Highlight */}
                <View style={styles.commissionBanner}>
                  <Text style={styles.commissionText}>
                    🏷️ Commission: <Text style={{ fontWeight: 'bold' }}>{plan.commissionLabel}</Text>
                  </Text>
                  <Text style={styles.listingsCapText}>
                    📦 Listings: <Text style={{ fontWeight: 'bold' }}>{plan.maxListings > 1000 ? 'Unlimited' : 'Up to 3'}</Text>
                  </Text>
                </View>

                {/* Features List */}
                <View style={styles.featuresList}>
                  {plan.featureList.map((f, idx) => (
                    <View key={idx} style={styles.featureItem}>
                      <Text style={styles.featureIcon}>{f.included ? '✅' : '🔒'}</Text>
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.featureTitle, !f.included && styles.featureDisabled]}>
                          {f.title}
                        </Text>
                        <Text style={styles.featureSubtitle}>{f.subtitle}</Text>
                      </View>
                    </View>
                  ))}
                </View>

                {/* Action CTA */}
                <TouchableOpacity
                  style={[
                    styles.ctaButton,
                    isCurrent
                      ? styles.ctaButtonCurrent
                      : isBiashara
                      ? styles.ctaButtonBiashara
                      : isPlus
                      ? styles.ctaButtonPlus
                      : styles.ctaButtonStarter,
                  ]}
                  disabled={isCurrent}
                  onPress={() => handleSelectUpgrade(plan)}
                  activeOpacity={0.85}>
                  <Text
                    style={[
                      styles.ctaButtonText,
                      isCurrent && styles.ctaButtonTextCurrent,
                      !isCurrent && styles.ctaButtonTextWhite,
                    ]}>
                    {isCurrent
                      ? '✓ Current Active Plan'
                      : tierKey === 'starter'
                      ? 'Switch to Free Starter'
                      : `Upgrade to ${plan.name} (KES ${price.toLocaleString()})`}
                  </Text>
                </TouchableOpacity>
              </View>
            );
          })}

          {/* Quick Commission Calculator Card */}
          <View style={styles.calcCard}>
            <Text style={styles.calcTitle}>💡 See How Much You Save on Mavuno</Text>
            <Text style={styles.calcSubtitle}>On KES 50,000 monthly produce sales:</Text>
            <View style={styles.calcTable}>
              <View style={styles.calcRow}>
                <Text style={styles.calcColHeader}>Plan</Text>
                <Text style={styles.calcColHeader}>Platform Fee</Text>
                <Text style={styles.calcColHeader}>You Keep</Text>
                <Text style={styles.calcColHeader}>Your Savings</Text>
              </View>
              <View style={styles.calcRow}>
                <Text style={styles.calcColCell}>Starter (10%)</Text>
                <Text style={styles.calcColCell}>KES 5,000</Text>
                <Text style={styles.calcColCell}>KES 45,000</Text>
                <Text style={styles.calcColCell}>-</Text>
              </View>
              <View style={[styles.calcRow, styles.calcRowPlus]}>
                <Text style={[styles.calcColCell, { fontWeight: '700', color: Colors.brandGreen }]}>Plus (6%)</Text>
                <Text style={styles.calcColCell}>KES 3,000</Text>
                <Text style={[styles.calcColCell, { fontWeight: '700' }]}>KES 47,000</Text>
                <Text style={[styles.calcColCell, { color: Colors.brandGreen, fontWeight: '700' }]}>+KES 2,000</Text>
              </View>
              <View style={[styles.calcRow, styles.calcRowBiashara]}>
                <Text style={[styles.calcColCell, { fontWeight: '700', color: '#B45309' }]}>Biashara (3%)</Text>
                <Text style={styles.calcColCell}>KES 1,500</Text>
                <Text style={[styles.calcColCell, { fontWeight: '700' }]}>KES 48,500</Text>
                <Text style={[styles.calcColCell, { color: '#B45309', fontWeight: '700' }]}>+KES 3,500</Text>
              </View>
            </View>
          </View>

          {/* FAQ Accordion Section */}
          <View style={styles.faqSection}>
            <Text style={styles.faqHeader}>Frequently Asked Questions</Text>
            <View style={styles.faqItem}>
              <Text style={styles.faqQuestion}>❓ How do I pay for my subscription?</Text>
              <Text style={styles.faqAnswer}>
                Payments are made instantly via Safaricom M-Pesa STK Push directly to your phone. You will receive an instant payment confirmation prompt.
              </Text>
            </View>
            <View style={styles.faqItem}>
              <Text style={styles.faqQuestion}>❓ What happens if I have more than 3 listings and downgrade?</Text>
              <Text style={styles.faqAnswer}>
                Your first 3 listings remain active and visible to buyers. Any additional listings are automatically paused until you reactivate Mkulima Plus.
              </Text>
            </View>
            <View style={styles.faqItem}>
              <Text style={styles.faqQuestion}>❓ What are harvest pre-bookings?</Text>
              <Text style={styles.faqAnswer}>
                Pre-bookings allow buyers and restaurants to reserve your crops before they are harvested. You guarantee sales in advance and lock in market prices!
              </Text>
            </View>
          </View>
        </View>
      )}

      {/* TAB 2: WHOLESALE BENCHMARK & REAL FARM ANALYTICS */}
      {activeTab === 'insights' && (
        <View>
          {currentTier === 'plus' || currentTier === 'biashara' ? (
            <View style={styles.insightsUnlockedContainer}>
              <View style={styles.unlockedHeader}>
                <Text style={styles.unlockedTitle}>🌾 Nairobi & Kiambu Wholesale Benchmark</Text>
                <Text style={styles.unlockedSub}>Real-time commodity wholesale market prices & supply demand indicators</Text>
              </View>

              {/* Real KPI Cards from Farmer's Real Data */}
              <View style={styles.kpiGrid}>
                <View style={styles.kpiCard}>
                  <Text style={styles.kpiValue}>{insights?.active_listings ?? 0}</Text>
                  <Text style={styles.kpiLabel}>Active Listings</Text>
                </View>
                <View style={styles.kpiCard}>
                  <Text style={styles.kpiValue}>{insights?.units_available ?? '0'} kg</Text>
                  <Text style={styles.kpiLabel}>Stock in Market</Text>
                </View>
                <View style={styles.kpiCard}>
                  <Text style={styles.kpiValue}>{insights?.completed_order_lines ?? 0}</Text>
                  <Text style={styles.kpiLabel}>Fulfilled Lines</Text>
                </View>
                <View style={[styles.kpiCard, { borderColor: Colors.brandGreen, borderWidth: 1.5 }]}>
                  <Text style={[styles.kpiValue, { color: Colors.brandGreen }]}>
                    KES {Number(insights?.gross_sales || 0).toLocaleString()}
                  </Text>
                  <Text style={styles.kpiLabel}>Gross Sales</Text>
                </View>
              </View>

              {/* Regional Commodity Price Trends */}
              <View style={styles.trendSection}>
                <Text style={styles.trendSectionTitle}>📊 Live Commodity Wholesale Price Trends</Text>
                <Text style={styles.trendSectionSub}>Benchmark your harvest prices against major urban wholesale terminals</Text>
                {COMMODITY_TRENDS.map((c, i) => (
                  <View key={i} style={styles.trendRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.trendItemName}>{c.item}</Text>
                      <Text style={styles.trendItemTrend}>{c.trend}</Text>
                    </View>
                    <View style={styles.trendPriceContainer}>
                      <Text style={styles.trendPriceText}>{c.avgPrice}</Text>
                      <Text style={[styles.trendArrow, c.direction === 'up' ? { color: '#16A34A' } : c.direction === 'down' ? { color: '#DC2626' } : { color: '#64748B' }]}>
                        {c.direction === 'up' ? '↗ High Demand' : c.direction === 'down' ? '↘ Supply Peak' : '→ Stable'}
                      </Text>
                    </View>
                  </View>
                ))}
              </View>
            </View>
          ) : (
            <View style={styles.lockedFeatureCard}>
              <Text style={styles.lockedIcon}>🔒</Text>
              <Text style={styles.lockedTitle}>Wholesale Benchmarks Require Mkulima Plus or Biashara</Text>
              <Text style={styles.lockedDesc}>
                Unlock real-time wholesale price benchmarks, commodity supply & demand forecasts, and gross sales analytics to maximize your farm profits.
              </Text>
              <TouchableOpacity
                style={[styles.ctaButton, styles.ctaButtonPlus, { marginTop: 16 }]}
                onPress={() => {
                  setSelectedPlanForUpgrade(FARMER_PLANS.plus);
                  setCheckoutModalVisible(true);
                }}>
                <Text style={styles.ctaButtonTextWhite}>⭐ Upgrade to Mkulima Plus (KES 499/mo)</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {/* M-PESA CHECKOUT MODAL */}
      <Modal
        visible={checkoutModalVisible}
        animationType="slide"
        transparent={true}
        onRequestClose={() => {
          if (!isProcessingPayment) setCheckoutModalVisible(false);
        }}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>M-Pesa Express Checkout</Text>
              <TouchableOpacity
                disabled={isProcessingPayment}
                onPress={() => setCheckoutModalVisible(false)}>
                <Text style={styles.modalCloseText}>✕</Text>
              </TouchableOpacity>
            </View>

            {selectedPlanForUpgrade && (
              <View style={styles.modalPlanSummary}>
                <Text style={styles.modalPlanName}>{selectedPlanForUpgrade.name}</Text>
                <Text style={styles.modalPlanInterval}>
                  Billing Period: {billingInterval === 'month' ? 'Monthly' : 'Annual (12 Months)'}
                </Text>
                <Text style={styles.modalPlanAmount}>
                  KES {billingInterval === 'month' ? selectedPlanForUpgrade.monthlyPrice.toLocaleString() : selectedPlanForUpgrade.annualPrice.toLocaleString()}
                </Text>
              </View>
            )}

            {paymentSuccessMessage ? (
              <View style={styles.successBanner}>
                <Text style={styles.successBannerText}>{paymentSuccessMessage}</Text>
              </View>
            ) : (
              <View style={styles.modalForm}>
                <Text style={styles.inputLabel}>Safaricom M-Pesa Phone Number</Text>
                <TextInput
                  style={styles.textInput}
                  value={mpesaPhone}
                  onChangeText={setMpesaPhone}
                  placeholder="e.g. 0712345678"
                  keyboardType="phone-pad"
                  editable={!isProcessingPayment}
                />
                <Text style={styles.inputHelper}>
                  An M-Pesa STK prompt will appear on your phone asking you to enter your M-Pesa PIN.
                </Text>

                <TouchableOpacity
                  style={[styles.payButton, isProcessingPayment && styles.payButtonDisabled]}
                  disabled={isProcessingPayment}
                  onPress={handleConfirmMpesaPayment}>
                  {isProcessingPayment ? (
                    <View style={styles.loadingRow}>
                      <ActivityIndicator size="small" color="#fff" />
                      <Text style={styles.payButtonText}>Sending STK Prompt...</Text>
                    </View>
                  ) : (
                    <Text style={styles.payButtonText}>
                      📱 Pay KES {selectedPlanForUpgrade ? (billingInterval === 'month' ? selectedPlanForUpgrade.monthlyPrice : selectedPlanForUpgrade.annualPrice).toLocaleString() : ''} via M-Pesa
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>
        </View>
      </Modal>

    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  contentContainer: {
    padding: 16,
    paddingBottom: 48,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    padding: 24,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 16,
    color: '#64748B',
    fontWeight: '500',
  },

  /* Current Plan Banner */
  currentPlanBanner: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 18,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
  currentPlanHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  currentPlanLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.8,
    color: '#64748B',
    marginBottom: 2,
  },
  currentPlanTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: '#0F172A',
  },
  badgePill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  badgeGreen: {
    backgroundColor: '#DCFCE7',
  },
  badgeGold: {
    backgroundColor: '#FEF3C7',
  },
  badgeGray: {
    backgroundColor: '#F1F5F9',
  },
  badgePillText: {
    fontSize: 11,
    fontWeight: '800',
    color: '#0F172A',
  },
  planSpecsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 12,
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
  },
  specItem: {
    flex: 1,
    alignItems: 'center',
  },
  specValue: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1E293B',
  },
  specLabel: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 2,
  },
  specDivider: {
    width: 1,
    height: 24,
    backgroundColor: '#E2E8F0',
  },

  /* Navigation Tabs */
  tabContainer: {
    flexDirection: 'row',
    backgroundColor: '#E2E8F0',
    borderRadius: 12,
    padding: 3,
    marginBottom: 16,
  },
  tabButton: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 10,
  },
  tabButtonActive: {
    backgroundColor: '#FFFFFF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  tabButtonText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#64748B',
  },
  tabButtonTextActive: {
    color: Colors.brandGreen,
    fontWeight: '800',
  },

  /* Billing Toggle */
  billingToggleSection: {
    alignItems: 'center',
    marginBottom: 16,
  },
  billingToggleTitle: {
    fontSize: 13,
    fontWeight: '600',
    color: '#475569',
    marginBottom: 8,
  },
  toggleRow: {
    flexDirection: 'row',
    backgroundColor: '#F1F5F9',
    borderRadius: 24,
    padding: 3,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  toggleOption: {
    paddingVertical: 7,
    paddingHorizontal: 16,
    borderRadius: 20,
  },
  toggleOptionActive: {
    backgroundColor: Colors.brandGreen,
  },
  toggleText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#475569',
  },
  toggleTextActive: {
    color: '#FFFFFF',
    fontWeight: '700',
  },

  /* Tier Cards */
  tierCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 18,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
  tierCardPlus: {
    borderColor: Colors.brandGreen,
    borderWidth: 2,
  },
  tierCardBiashara: {
    borderColor: '#D97706',
    borderWidth: 2,
    backgroundColor: '#FFFCF7',
  },
  tierCardCurrent: {
    backgroundColor: '#F8FAFC',
  },
  recommendedBadge: {
    backgroundColor: Colors.brandGreen,
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 8,
    alignSelf: 'flex-start',
    marginBottom: 10,
  },
  recommendedBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  biasharaBadge: {
    backgroundColor: '#D97706',
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 8,
    alignSelf: 'flex-start',
    marginBottom: 10,
  },
  biasharaBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  tierHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 10,
  },
  tierName: {
    fontSize: 18,
    fontWeight: '800',
    color: '#0F172A',
  },
  tierTagline: {
    fontSize: 12,
    color: '#64748B',
    marginTop: 2,
    maxWidth: 200,
  },
  priceContainer: {
    alignItems: 'flex-end',
  },
  priceCurrency: {
    fontSize: 11,
    fontWeight: '700',
    color: '#64748B',
  },
  priceNumber: {
    fontSize: 22,
    fontWeight: '900',
    color: '#0F172A',
  },
  pricePeriod: {
    fontSize: 11,
    color: '#64748B',
  },
  commissionBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#F1F5F9',
    borderRadius: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
    marginBottom: 14,
  },
  commissionText: {
    fontSize: 11,
    color: '#334155',
  },
  listingsCapText: {
    fontSize: 11,
    color: '#334155',
  },
  featuresList: {
    marginBottom: 16,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  featureIcon: {
    fontSize: 14,
    marginRight: 8,
    marginTop: 1,
  },
  featureTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1E293B',
  },
  featureDisabled: {
    color: '#94A3B8',
    textDecorationLine: 'line-through',
  },
  featureSubtitle: {
    fontSize: 11,
    color: '#64748B',
  },
  ctaButton: {
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaButtonPlus: {
    backgroundColor: Colors.brandGreen,
  },
  ctaButtonBiashara: {
    backgroundColor: '#D97706',
  },
  ctaButtonStarter: {
    backgroundColor: '#64748B',
  },
  ctaButtonCurrent: {
    backgroundColor: '#E2E8F0',
  },
  ctaButtonText: {
    fontSize: 14,
    fontWeight: '700',
  },
  ctaButtonTextWhite: {
    color: '#FFFFFF',
  },
  ctaButtonTextCurrent: {
    color: '#64748B',
  },

  /* Savings Calculator */
  calcCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  calcTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#0F172A',
    marginBottom: 2,
  },
  calcSubtitle: {
    fontSize: 12,
    color: '#64748B',
    marginBottom: 12,
  },
  calcTable: {
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
  },
  calcRow: {
    flexDirection: 'row',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  calcRowPlus: {
    backgroundColor: '#F0FDF4',
  },
  calcRowBiashara: {
    backgroundColor: '#FEF3C7',
  },
  calcColHeader: {
    flex: 1,
    fontSize: 11,
    fontWeight: '800',
    color: '#64748B',
  },
  calcColCell: {
    flex: 1,
    fontSize: 12,
    color: '#1E293B',
  },

  /* FAQs */
  faqSection: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  faqHeader: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
    marginBottom: 12,
  },
  faqItem: {
    marginBottom: 12,
  },
  faqQuestion: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1E293B',
    marginBottom: 3,
  },
  faqAnswer: {
    fontSize: 12,
    color: '#64748B',
    lineHeight: 17,
  },

  /* Insights Screen (Biashara) */
  insightsUnlockedContainer: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  unlockedHeader: {
    marginBottom: 14,
  },
  unlockedTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
  },
  unlockedSub: {
    fontSize: 12,
    color: '#64748B',
    marginTop: 2,
  },
  kpiGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 20,
  },
  kpiCard: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  kpiValue: {
    fontSize: 20,
    fontWeight: '900',
    color: '#0F172A',
  },
  kpiLabel: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 4,
  },
  trendSection: {
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
    paddingTop: 14,
  },
  trendSectionTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
  },
  trendSectionSub: {
    fontSize: 11,
    color: '#64748B',
    marginBottom: 12,
  },
  trendRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  trendItemName: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1E293B',
  },
  trendItemTrend: {
    fontSize: 11,
    color: '#64748B',
  },
  trendPriceContainer: {
    alignItems: 'flex-end',
  },
  trendPriceText: {
    fontSize: 13,
    fontWeight: '800',
    color: '#0F172A',
  },
  trendArrow: {
    fontSize: 11,
    fontWeight: '700',
  },

  /* Pre-bookings Screen */
  bookingsContainer: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  bookingsHeader: {
    marginBottom: 14,
  },
  emptyBookingsCard: {
    alignItems: 'center',
    padding: 32,
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
  },
  emptyBookingsTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#1E293B',
  },
  emptyBookingsSub: {
    fontSize: 12,
    color: '#64748B',
    textAlign: 'center',
    marginTop: 4,
  },
  bookingCard: {
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  bookingTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  bookingTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
  },
  bookingSub: {
    fontSize: 12,
    color: '#475569',
    marginTop: 2,
  },
  bookingBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
  },
  bookingBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#0F172A',
  },
  bookingNotes: {
    fontSize: 12,
    fontStyle: 'italic',
    color: '#334155',
    marginBottom: 8,
  },
  bookingDatesRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
  },
  bookingDateLabel: {
    fontSize: 11,
    color: '#64748B',
  },
  bookingPrice: {
    fontSize: 12,
    fontWeight: '700',
    color: Colors.brandGreen,
  },
  bookingActionsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  bookingBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: 'center',
  },
  bookingBtnAccept: {
    backgroundColor: Colors.brandGreen,
  },
  bookingBtnReject: {
    backgroundColor: '#E2E8F0',
  },
  bookingBtnFulfill: {
    backgroundColor: '#D97706',
  },
  bookingBtnTextWhite: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
  },
  bookingBtnTextDark: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '700',
  },

  /* Locked Teaser Card */
  lockedFeatureCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  lockedIcon: {
    fontSize: 40,
    marginBottom: 12,
  },
  lockedTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
    textAlign: 'center',
    marginBottom: 8,
  },
  lockedDesc: {
    fontSize: 13,
    color: '#64748B',
    textAlign: 'center',
    lineHeight: 19,
  },

  /* Modal */
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    padding: 20,
  },
  modalCard: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 10,
    elevation: 6,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: '#0F172A',
  },
  modalCloseText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#64748B',
    padding: 4,
  },
  modalPlanSummary: {
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  modalPlanName: {
    fontSize: 16,
    fontWeight: '800',
    color: '#0F172A',
  },
  modalPlanInterval: {
    fontSize: 12,
    color: '#64748B',
    marginTop: 2,
  },
  modalPlanAmount: {
    fontSize: 20,
    fontWeight: '900',
    color: Colors.brandGreen,
    marginTop: 4,
  },
  modalForm: {},
  inputLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1E293B',
    marginBottom: 6,
  },
  textInput: {
    borderWidth: 1.5,
    borderColor: '#CBD5E1',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    color: '#0F172A',
    marginBottom: 6,
    backgroundColor: '#FFFFFF',
  },
  inputHelper: {
    fontSize: 11,
    color: '#64748B',
    marginBottom: 16,
    lineHeight: 15,
  },
  payButton: {
    backgroundColor: '#16A34A',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  payButtonDisabled: {
    backgroundColor: '#86EFAC',
  },
  payButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  successBanner: {
    backgroundColor: '#DCFCE7',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  successBannerText: {
    color: '#15803D',
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
});
