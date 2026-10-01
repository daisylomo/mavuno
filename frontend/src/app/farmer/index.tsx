import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  Platform,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Href, useFocusEffect, useRouter } from 'expo-router';
import { Colors } from '../../constants/theme';
import { farmerService } from '../../services/farmer-service';
import { AppUser, userService } from '../../services/user-service';
import { FarmerStats, ListingStatus, ProduceListing } from '../../types/farmer';
import MarketplaceLinks from '@/components/marketplace-links';
import {
  ActiveFarmerSubscription,
  farmerSubscriptionService,
} from '@/services/farmer-subscription-service';

const PRODUCE_IMAGES: Record<string, any> = {
  tomatoes: require('@/assets/products/tomatoes.jpg'),
  spinach: require('@/assets/products/spinach.jpg'),
  mangoes: require('@/assets/products/mangoes.jpg'),
  bananas: require('@/assets/products/bananas.jpg'),
  carrots: require('@/assets/products/carrots.jpg'),
  avocados: require('@/assets/products/avocados.jpg'),
  potatoes: require('@/assets/products/potatoes.jpg'),
  honey: require('@/assets/products/honey.jpg'),
};

const getProduceImageSource = (imageUrl?: string) => {
  if (!imageUrl) return undefined;
  if (imageUrl.startsWith('preset:')) {
    const key = imageUrl.replace('preset:', '');
    return PRODUCE_IMAGES[key] || PRODUCE_IMAGES.tomatoes;
  }
  return { uri: imageUrl };
};

export default function FarmerDashboard() {
  const router = useRouter();

  const [currentUser, setCurrentUser] = useState<AppUser | null>(null);
  const [subscription, setSubscription] = useState<ActiveFarmerSubscription | null>(null);
  const [listings, setListings] = useState<ProduceListing[]>([]);
  const [stats, setStats] = useState<FarmerStats>({
    activeListingsCount: 0,
    pendingOrdersCount: 0,
    totalRevenue: 0,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadData = async () => {
    try {
      setError('');
      const [allListings, currentStats, user, currentSub] = await Promise.all([
        farmerService.getListings(),
        farmerService.getStats(),
        userService.getCurrentUser(),
        farmerSubscriptionService.getCurrentSubscription(),
      ]);
      setListings(allListings);
      setStats(currentStats);
      setCurrentUser(user);
      setSubscription(currentSub);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load your listings.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  React.useEffect(() => {
    loadData();
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadData();
    }, [])
  );

  const getDisplayName = () => {
    if (!currentUser?.name) return 'Farmer';
    const clean = currentUser.name.trim().replace(/\s/g, '');
    if (/^\+?\d+$/.test(clean)) return 'Farmer';
    return currentUser.name.trim();
  };

  const onRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  const handleToggleStatus = async (item: ProduceListing) => {
    try {
      const nextStatus: ListingStatus = item.status === 'active' || item.status === 'low_stock' ? 'paused' : 'active';
      await farmerService.updateListingStatus(item.id, nextStatus);
      await loadData();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not change listing status.');
    }
  };

  const handleDeleteListing = async (id: string, title: string) => {
    if (Platform.OS === 'web') {
      if (window.confirm(`Are you sure you want to remove "${title}"?`)) {
        try { await farmerService.deleteListing(id); await loadData(); }
        catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not remove listing.'); }
      }
    } else {
      Alert.alert(
        'Delete Produce',
        `Are you sure you want to remove "${title}" from the marketplace?`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Delete',
            style: 'destructive',
            onPress: async () => {
              try { await farmerService.deleteListing(id); await loadData(); }
              catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not remove listing.'); }
            },
          },
        ]
      );
    }
  };

  const getStatusStyle = (status: ListingStatus) => {
    switch (status) {
      case 'active':
        return { bg: '#DCFCE7', text: '#15803D', label: 'Active' };
      case 'low_stock':
        return { bg: '#FEF3C7', text: '#B45309', label: 'Low Stock' };
      case 'paused':
        return { bg: '#F1F5F9', text: '#475569', label: 'Paused' };
      case 'sold_out':
        return { bg: '#FEE2E2', text: '#B91C1C', label: 'Sold Out' };
    }
  };

  const renderHeader = () => (
    <View>
      <View style={{ padding: 16 }}><MarketplaceLinks /></View>
      {/* Farm Banner */}
      <View style={styles.welcomeBanner}>
        <View style={styles.bannerTop}>
          <View style={styles.avatarCircle}>
            <Text style={styles.avatarEmoji}>🌾</Text>
          </View>
          <View style={styles.bannerInfo}>
            <Text style={styles.farmTitle}>
              Jambo, {getDisplayName()}! 👋
            </Text>
            <Text style={styles.farmSubtitle}>Manage your fresh harvest & buyer orders</Text>
            <TouchableOpacity
              onPress={() => router.push('/farmer/subscription' as Href)}
              style={[
                styles.tierChip,
                subscription?.tier === 'biashara'
                  ? styles.tierChipBiashara
                  : subscription?.tier === 'plus'
                  ? styles.tierChipPlus
                  : styles.tierChipStarter,
              ]}>
              <Text style={styles.tierChipText}>
                {subscription?.tier === 'biashara'
                  ? '👑 Biashara Pro (3% Fee)'
                  : subscription?.tier === 'plus'
                  ? '⭐ Mkulima Plus (Verified ✅)'
                  : '🌱 Free Starter Plan'} • Manage ➔
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* Live Metrics */}
        <View style={styles.statsRow}>
          <View style={styles.statBox}>
            <Text style={styles.statNumber}>{stats.activeListingsCount}</Text>
            <Text style={styles.statLabel}>Active Produce</Text>
          </View>

          <TouchableOpacity
            style={[styles.statBox, styles.statBoxClickable]}
            onPress={() => router.push('/farmer/orders' as Href)}>
            <View style={styles.statBadgeRow}>
              <Text style={[styles.statNumber, { color: '#EAB308' }]}>
                {stats.pendingOrdersCount}
              </Text>
              {stats.pendingOrdersCount > 0 && <View style={styles.alertDot} />}
            </View>
            <Text style={styles.statLabel}>Pending Orders ➔</Text>
          </TouchableOpacity>

          <View style={styles.statBox}>
            <Text style={[styles.statNumber, { color: '#16A34A' }]}>
              KES {stats.totalRevenue > 1000 ? `${(stats.totalRevenue / 1000).toFixed(1)}k` : stats.totalRevenue}
            </Text>
            <Text style={styles.statLabel}>Revenue</Text>
          </View>
        </View>
      </View>

      {/* Subscription Promo / Status Banner */}
      {subscription?.tier === 'starter' || !subscription ? (
        <TouchableOpacity
          style={styles.upgradePromoBanner}
          onPress={() => router.push('/farmer/subscription' as Href)}
          activeOpacity={0.88}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
              <View style={styles.upgradePromoTag}>
                <Text style={styles.upgradePromoTagText}>BOOST HARVEST SALES</Text>
              </View>
              <Text style={styles.upgradePromoSub}>Save 20% Annual</Text>
            </View>
            <Text style={styles.upgradePromoTitle}>Upgrade to Mkulima Plus or Biashara</Text>
            <Text style={styles.upgradePromoDesc}>
              Unlock unlimited produce listings, Verified Farmer badge ✅ & buyer harvest pre-bookings.
            </Text>
          </View>
          <View style={styles.upgradePromoArrowCircle}>
            <Text style={styles.upgradePromoArrowText}>➔</Text>
          </View>
        </TouchableOpacity>
      ) : (
        <TouchableOpacity
          style={styles.proActiveBanner}
          onPress={() => router.push('/farmer/subscription' as Href)}
          activeOpacity={0.88}>
          <Text style={{ fontSize: 24, marginRight: 10 }}>
            {subscription.tier === 'biashara' ? '👑' : '⭐'}
          </Text>
          <View style={{ flex: 1 }}>
            <Text style={styles.proActiveTitle}>
              {subscription.tier === 'biashara'
                ? 'Mkulima Biashara Pro Active'
                : 'Mkulima Plus Active'}
            </Text>
            <Text style={styles.proActiveDesc}>
              {subscription.tier === 'biashara'
                ? '3% lowest commission rate • Market intelligence & instant payouts'
                : 'Unlimited listings enabled • Verified Farmer badge ✅ • 6% fee rate'}
            </Text>
          </View>
          <Text style={styles.proActiveManageText}>Plans ➔</Text>
        </TouchableOpacity>
      )}

      {/* Action Buttons Hub */}
      <View style={styles.actionGrid}>
        <TouchableOpacity
          style={[styles.actionBtn, styles.actionPrimary]}
          onPress={() => router.push('/farmer/new-listing' as Href)}
          activeOpacity={0.85}>
          <Text style={styles.actionBtnIcon}>➕</Text>
          <View>
            <Text style={styles.actionBtnTitleWhite}>Add Produce Listing</Text>
            <Text style={styles.actionBtnSubWhite}>Post fresh harvest for customers</Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.actionBtn, styles.actionSecondary]}
          onPress={() => router.push('/farmer/orders' as Href)}
          activeOpacity={0.85}>
          <Text style={styles.actionBtnIcon}>📦</Text>
          <View>
            <Text style={styles.actionBtnTitle}>Manage Customer Orders</Text>
            <Text style={styles.actionBtnSub}>
              {stats.pendingOrdersCount > 0
                ? `${stats.pendingOrdersCount} paid orders awaiting the next step`
                : 'View order history and status'}
            </Text>
          </View>
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.actionBtn, styles.actionTierBtn]}
          onPress={() => router.push('/farmer/subscription' as Href)}
          activeOpacity={0.85}>
          <Text style={styles.actionBtnIcon}>⭐</Text>
          <View>
            <Text style={styles.actionBtnTitle}>Farmer Subscriptions & Tiers</Text>
            <Text style={styles.actionBtnSub}>
              Active: {subscription?.tier === 'biashara' ? 'Biashara Pro (3% Fee)' : subscription?.tier === 'plus' ? 'Mkulima Plus (6% Fee)' : 'Free Starter (10% Fee)'}
            </Text>
          </View>
        </TouchableOpacity>
      </View>

      {/* Section Title */}
      {!!error && <Text style={{ color: '#B91C1C', marginBottom: 12 }}>{error}</Text>}
      <View style={styles.sectionHeaderRow}>
        <Text style={styles.sectionTitle}>My Produce Catalog</Text>
        <Text style={styles.listingsCountText}>{listings.length} items listed</Text>
      </View>
    </View>
  );

  const renderProduceCard = ({ item }: { item: ProduceListing }) => {
    const status = getStatusStyle(item.status);
    const isProOrPlus = subscription && (subscription.tier === 'plus' || subscription.tier === 'biashara');

    return (
      <View style={styles.produceCard}>
        {isProOrPlus && (
          <View style={styles.verifiedProduceBadge}>
            <Text style={styles.verifiedProduceBadgeText}>
              {subscription?.tier === 'biashara' ? '👑 Biashara Verified • Priority Placement' : '✅ Verified Farmer Produce'}
            </Text>
          </View>
        )}
        {/* Top Info */}
        <View style={styles.cardHeader}>
          {item.imageUrl ? (
            <Image
              source={getProduceImageSource(item.imageUrl)!}
              style={styles.cardThumbnail}
            />
          ) : null}
          <View style={styles.titleContainer}>
            <Text style={styles.produceTitle}>{item.title}</Text>
            <Text style={styles.produceMeta}>
              {item.category} • {item.harvestDate}
            </Text>
          </View>
          <View style={[styles.statusChip, { backgroundColor: status.bg }]}>
            <Text style={[styles.statusChipText, { color: status.text }]}>
              {status.label}
            </Text>
          </View>
        </View>

        {/* Pricing & Stock Details */}
        <View style={styles.cardDetailsRow}>
          <View style={styles.priceContainer}>
            <Text style={styles.priceLabel}>Selling Price</Text>
            <Text style={styles.priceValue}>
              KSh {item.price}{' '}
              <Text style={styles.priceUnit}>/ {item.unit}</Text>
            </Text>
          </View>

          <View style={styles.stockContainer}>
            <Text style={styles.stockLabel}>Stock Available</Text>
            <Text style={styles.stockValue}>
              {item.quantity} {item.unit}
            </Text>
          </View>
        </View>

        {item.description ? (
          <Text style={styles.descriptionText} numberOfLines={2}>
            {item.description}
          </Text>
        ) : null}

        {/* Card Actions */}
        <View style={styles.cardActionsRow}>
          <TouchableOpacity
            style={[
              styles.actionPill,
              item.status === 'active' || item.status === 'low_stock' ? styles.pausePill : styles.resumePill,
            ]}
            onPress={() => handleToggleStatus(item)}>
            <Text
              style={[
                styles.actionPillText,
                item.status === 'active' || item.status === 'low_stock' ? styles.pauseText : styles.resumeText,
              ]}>
              {item.status === 'active' || item.status === 'low_stock' ? '⏸️ Pause Listing' : '▶️ Activate'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionPill, styles.deletePill]}
            onPress={() => handleDeleteListing(item.id, item.title)}>
            <Text style={styles.deleteText}>🗑️ Remove</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      {loading ? (
        <View style={styles.centerLoading}>
          <ActivityIndicator size="large" color={Colors.brandGreen} />
        </View>
      ) : (
        <FlatList
          data={listings}
          keyExtractor={(item) => item.id}
          renderItem={renderProduceCard}
          ListHeaderComponent={renderHeader}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              colors={[Colors.brandGreen]}
            />
          }
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={styles.emptyEmoji}>🧺</Text>
              <Text style={styles.emptyTitle}>No produce listed yet</Text>
              <Text style={styles.emptySub}>
                Start selling by adding your first fresh harvest listing!
              </Text>
            </View>
          }
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  listContent: {
    padding: 16,
    paddingBottom: 40,
  },
  centerLoading: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  welcomeBanner: {
    backgroundColor: Colors.surface,
    borderRadius: 16,
    padding: 18,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.05,
    shadowRadius: 6,
    elevation: 2,
  },
  bannerTop: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
  },
  avatarCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#E8F5E9',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  avatarEmoji: {
    fontSize: 24,
  },
  bannerInfo: {
    flex: 1,
  },
  farmTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: Colors.brandGreen,
  },
  farmSubtitle: {
    fontSize: 13,
    color: Colors.textMuted,
    marginTop: 2,
  },
  statsRow: {
    flexDirection: 'row',
    gap: 10,
  },
  statBox: {
    flex: 1,
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingVertical: 12,
    paddingHorizontal: 8,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  statBoxClickable: {
    backgroundColor: '#FFFBEB',
    borderColor: '#FDE68A',
  },
  statBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  alertDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#EF4444',
  },
  statNumber: {
    fontSize: 18,
    fontWeight: '800',
    color: Colors.text,
  },
  statLabel: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 4,
    fontWeight: '600',
    textAlign: 'center',
  },
  actionGrid: {
    gap: 12,
    marginBottom: 24,
  },
  actionBtn: {
    borderRadius: 14,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 2,
  },
  actionPrimary: {
    backgroundColor: Colors.brandGreen,
    borderColor: '#1B4332',
  },
  actionSecondary: {
    backgroundColor: Colors.surface,
    borderColor: '#E2E8F0',
  },
  actionBtnIcon: {
    fontSize: 26,
    marginRight: 14,
  },
  actionBtnTitleWhite: {
    fontSize: 16,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  actionBtnSubWhite: {
    fontSize: 12,
    color: '#D8F3DC',
    marginTop: 2,
  },
  actionBtnTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.text,
  },
  actionBtnSub: {
    fontSize: 12,
    color: Colors.textMuted,
    marginTop: 2,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: Colors.text,
  },
  listingsCountText: {
    fontSize: 13,
    color: Colors.textMuted,
    fontWeight: '600',
  },
  produceCard: {
    backgroundColor: Colors.surface,
    borderRadius: 14,
    padding: 16,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  cardThumbnail: {
    width: 48,
    height: 48,
    borderRadius: 8,
    marginRight: 10,
    backgroundColor: '#F1F5F9',
  },
  titleContainer: {
    flex: 1,
    paddingRight: 8,
  },
  produceTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: Colors.text,
  },
  produceMeta: {
    fontSize: 12,
    color: '#64748B',
    marginTop: 2,
  },
  statusChip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusChipText: {
    fontSize: 11,
    fontWeight: '700',
  },
  cardDetailsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
  },
  priceContainer: {},
  priceLabel: {
    fontSize: 11,
    color: '#64748B',
    textTransform: 'uppercase',
    fontWeight: '600',
  },
  priceValue: {
    fontSize: 16,
    fontWeight: '800',
    color: Colors.brandGreen,
    marginTop: 2,
  },
  priceUnit: {
    fontSize: 12,
    fontWeight: '500',
    color: '#64748B',
  },
  stockContainer: {
    alignItems: 'flex-end',
  },
  stockLabel: {
    fontSize: 11,
    color: '#64748B',
    textTransform: 'uppercase',
    fontWeight: '600',
  },
  stockValue: {
    fontSize: 15,
    fontWeight: '700',
    color: Colors.text,
    marginTop: 2,
  },
  descriptionText: {
    fontSize: 13,
    color: '#4B5563',
    lineHeight: 18,
    marginBottom: 12,
  },
  cardActionsRow: {
    flexDirection: 'row',
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
    paddingTop: 10,
  },
  actionPill: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 8,
  },
  pausePill: {
    backgroundColor: '#F1F5F9',
  },
  resumePill: {
    backgroundColor: '#DCFCE7',
  },
  deletePill: {
    backgroundColor: '#FEE2E2',
  },
  actionPillText: {
    fontSize: 12,
    fontWeight: '600',
  },
  pauseText: {
    color: '#475569',
  },
  resumeText: {
    color: '#166534',
  },
  deleteText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#DC2626',
  },
  emptyState: {
    padding: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: Colors.text,
  },
  emptySub: {
    fontSize: 13,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: 4,
  },
  tierChip: {
    alignSelf: 'flex-start',
    marginTop: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
  },
  tierChipStarter: {
    backgroundColor: '#F1F5F9',
  },
  tierChipPlus: {
    backgroundColor: '#DCFCE7',
  },
  tierChipBiashara: {
    backgroundColor: '#FEF3C7',
  },
  tierChipText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#0F172A',
  },
  upgradePromoBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 14,
    marginBottom: 14,
    borderWidth: 1.5,
    borderColor: '#86EFAC',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  upgradePromoTag: {
    backgroundColor: Colors.brandGreen,
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  upgradePromoTagText: {
    color: '#FFFFFF',
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  upgradePromoSub: {
    fontSize: 11,
    fontWeight: '700',
    color: '#D97706',
  },
  upgradePromoTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
    marginBottom: 2,
  },
  upgradePromoDesc: {
    fontSize: 11,
    color: '#64748B',
    lineHeight: 15,
  },
  upgradePromoArrowCircle: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#DCFCE7',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 10,
  },
  upgradePromoArrowText: {
    fontSize: 15,
    fontWeight: '800',
    color: Colors.brandGreen,
  },
  proActiveBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFCF7',
    borderRadius: 14,
    padding: 14,
    marginBottom: 14,
    borderWidth: 1.5,
    borderColor: '#FCD34D',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  proActiveTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: '#0F172A',
  },
  proActiveDesc: {
    fontSize: 11,
    color: '#64748B',
    marginTop: 2,
  },
  proActiveManageText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#D97706',
    marginLeft: 8,
  },
  actionTierBtn: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#CBD5E1',
  },
  verifiedProduceBadge: {
    backgroundColor: '#DCFCE7',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    alignSelf: 'flex-start',
    marginBottom: 8,
  },
  verifiedProduceBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#15803D',
  },
});
