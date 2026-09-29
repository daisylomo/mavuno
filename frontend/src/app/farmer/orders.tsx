import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Colors } from '@/constants/theme';
import { farmerService } from '@/services/farmer-service';
import { FarmerOrder, OrderStatus } from '@/types/farmer';
import { isBackendConfigured } from '@/services/auth-api';

export default function FarmerOrdersScreen() {
  const [orders, setOrders] = useState<FarmerOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'pending' | 'accepted' | 'completed'>('all');

  const loadOrders = async () => {
    setLoading(true);
    try {
      const data = await farmerService.getOrders();
      setOrders(data);
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load orders.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
  }, []);

  const handleUpdateStatus = async (orderId: string, nextStatus: OrderStatus) => {
    await farmerService.updateOrderStatus(orderId, nextStatus);
    await loadOrders();
  };

  const handleAdvance = async (order: FarmerOrder) => {
    try {
      await farmerService.advanceFulfilment(order);
      await loadOrders();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not update delivery.');
    }
  };

  const filteredOrders = orders.filter((o) => {
    if (selectedFilter === 'all') return true;
    if (selectedFilter === 'accepted' && isBackendConfigured()) {
      return ['accepted', 'ready_for_pickup', 'dispatched'].includes(o.status);
    }
    return o.status === selectedFilter;
  });

  const getStatusBadge = (order: FarmerOrder) => {
    const status = order.status;
    switch (status) {
      case 'pending':
        return { bg: '#FEF3C7', text: '#92400E', label: isBackendConfigured()
          ? order.fulfilmentStatus === 'pending' ? 'Delivery plan received' : 'Paid — awaiting delivery plan'
          : 'Pending Approval' };
      case 'accepted':
        return { bg: '#DBEAFE', text: '#1E40AF', label: isBackendConfigured() ? 'Delivery scheduled' : 'Order Accepted' };
      case 'ready_for_pickup':
        return { bg: '#E0E7FF', text: '#3730A3', label: 'Ready for handover' };
      case 'dispatched':
        return { bg: '#E0E7FF', text: '#3730A3', label: isBackendConfigured() ? 'In transit' : 'Dispatched' };
      case 'completed':
        return { bg: '#DCFCE7', text: '#166534', label: 'Completed' };
      case 'cancelled':
        return { bg: '#FEE2E2', text: '#991B1B', label: 'Cancelled' };
    }
  };

  const renderOrderItem = ({ item }: { item: FarmerOrder }) => {
    const badge = getStatusBadge(item);

    return (
      <View style={styles.orderCard}>
        {/* Header */}
        <View style={styles.cardHeader}>
          <View>
            <Text style={styles.orderNumber}>{item.orderNumber}</Text>
            <Text style={styles.orderTime}>{item.createdAt}</Text>
          </View>
          <View style={[styles.statusBadge, { backgroundColor: badge.bg }]}>
            <Text style={[styles.statusText, { color: badge.text }]}>
              {badge.label}
            </Text>
          </View>
        </View>

        {/* Customer Details */}
        <View style={styles.customerBox}>
          <Text style={styles.customerName}>👤 {item.customerName}</Text>
          <Text style={styles.customerDetail}>📞 {item.customerPhone}</Text>
          <Text style={styles.customerDetail}>📍 {item.deliveryLocation}</Text>
        </View>

        {/* Items List */}
        <View style={styles.itemsSection}>
          <Text style={styles.itemsSectionTitle}>Ordered Produce</Text>
          {item.items.map((prod, index) => (
            <View key={index} style={styles.itemRow}>
              <Text style={styles.itemTitle}>
                {prod.title} ({prod.quantity} {prod.unit})
              </Text>
              <Text style={styles.itemPrice}>KSh {prod.lineTotal}</Text>
            </View>
          ))}
        </View>

        {/* Total & Payment */}
        <View style={styles.totalRow}>
          <View>
            <Text style={styles.paymentMethod}>Payment: {item.paymentMethod}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={styles.totalLabel}>{isBackendConfigured() ? 'Your items subtotal' : 'Total Payout'}</Text>
            <Text style={styles.totalAmount}>KSh {item.totalAmount.toLocaleString()}</Text>
          </View>
        </View>

        {/* Actions */}
        {!isBackendConfigured() && <View style={styles.actionRow}>
          {item.status === 'pending' && (
            <>
              <TouchableOpacity
                style={[styles.actionBtn, styles.acceptBtn]}
                onPress={() => handleUpdateStatus(item.id, 'accepted')}>
                <Text style={styles.acceptBtnText}>Accept Order</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionBtn, styles.declineBtn]}
                onPress={() => handleUpdateStatus(item.id, 'cancelled')}>
                <Text style={styles.declineBtnText}>Decline</Text>
              </TouchableOpacity>
            </>
          )}

          {item.status === 'accepted' && (
            <TouchableOpacity
              style={[styles.actionBtn, styles.dispatchBtn]}
              onPress={() => handleUpdateStatus(item.id, 'dispatched')}>
              <Text style={styles.dispatchBtnText}>Mark Dispatched / In Transit</Text>
            </TouchableOpacity>
          )}

          {item.status === 'dispatched' && (
            <TouchableOpacity
              style={[styles.actionBtn, styles.completeBtn]}
              onPress={() => handleUpdateStatus(item.id, 'completed')}>
              <Text style={styles.completeBtnText}>Confirm Delivery & Settlement</Text>
            </TouchableOpacity>
          )}
        </View>}
        {isBackendConfigured() && (['pending', 'scheduled'].includes(item.fulfilmentStatus ?? '') ||
          (item.fulfilmentStatus === 'ready_for_handover' && item.fulfilmentMethod === 'delivery')) && (
          <View style={styles.actionRow}>
            <TouchableOpacity style={[styles.actionBtn, styles.acceptBtn]} onPress={() => handleAdvance(item)}>
              <Text style={styles.acceptBtnText}>
                {item.fulfilmentStatus === 'pending' ? 'Confirm delivery schedule'
                  : item.fulfilmentStatus === 'scheduled' ? 'Ready for handover' : 'Mark in transit'}
              </Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    );
  };

  return (
    <View style={styles.container}>
      {/* Filter Tabs */}
      {error && <Text style={{ color: '#B91C1C', padding: 12 }}>{error}</Text>}
      <View style={styles.filterRow}>
        {(['all', 'pending', 'accepted', 'completed'] as const).map((filter) => {
          const isSelected = selectedFilter === filter;
          return (
            <TouchableOpacity
              key={filter}
              style={[styles.filterChip, isSelected && styles.filterChipActive]}
              onPress={() => setSelectedFilter(filter)}>
              <Text
                style={[
                  styles.filterChipText,
                  isSelected && styles.filterChipTextActive,
                ]}>
                {filter === 'accepted' && isBackendConfigured()
                  ? 'In progress' : filter.charAt(0).toUpperCase() + filter.slice(1)}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={Colors.brandGreen} />
        </View>
      ) : filteredOrders.length === 0 ? (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyEmoji}>📦</Text>
          <Text style={styles.emptyTitle}>No orders found</Text>
          <Text style={styles.emptySubtitle}>
            New customer purchase orders will appear here automatically
          </Text>
        </View>
      ) : (
        <FlatList
          data={filteredOrders}
          keyExtractor={(item) => item.id}
          renderItem={renderOrderItem}
          contentContainerStyle={styles.listContent}
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
  filterRow: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: Colors.surface,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  filterChip: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 16,
    backgroundColor: '#F1F5F9',
  },
  filterChipActive: {
    backgroundColor: Colors.brandGreen,
  },
  filterChipText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748B',
  },
  filterChipTextActive: {
    color: '#FFFFFF',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  emptyEmoji: {
    fontSize: 48,
    marginBottom: 12,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: Colors.text,
  },
  emptySubtitle: {
    fontSize: 14,
    color: Colors.textMuted,
    textAlign: 'center',
    marginTop: 4,
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  orderCard: {
    backgroundColor: Colors.surface,
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  orderNumber: {
    fontSize: 16,
    fontWeight: '800',
    color: Colors.text,
  },
  orderTime: {
    fontSize: 12,
    color: Colors.textMuted,
    marginTop: 2,
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  statusText: {
    fontSize: 12,
    fontWeight: '700',
  },
  customerBox: {
    backgroundColor: '#F8FAFC',
    borderRadius: 8,
    padding: 10,
    marginBottom: 12,
  },
  customerName: {
    fontSize: 14,
    fontWeight: '700',
    color: Colors.text,
  },
  customerDetail: {
    fontSize: 13,
    color: '#4B5563',
    marginTop: 2,
  },
  itemsSection: {
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: '#F1F5F9',
    paddingVertical: 10,
    marginBottom: 12,
  },
  itemsSectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: '#94A3B8',
    textTransform: 'uppercase',
    marginBottom: 6,
  },
  itemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginVertical: 2,
  },
  itemTitle: {
    fontSize: 14,
    color: Colors.text,
  },
  itemPrice: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.text,
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  paymentMethod: {
    fontSize: 13,
    fontWeight: '600',
    color: Colors.brandGreen,
  },
  totalLabel: {
    fontSize: 11,
    color: Colors.textMuted,
  },
  totalAmount: {
    fontSize: 18,
    fontWeight: '800',
    color: Colors.text,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  acceptBtn: {
    backgroundColor: Colors.brandGreen,
  },
  acceptBtnText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 14,
  },
  declineBtn: {
    backgroundColor: '#FEE2E2',
  },
  declineBtnText: {
    color: '#DC2626',
    fontWeight: '600',
    fontSize: 14,
  },
  dispatchBtn: {
    backgroundColor: '#2563EB',
  },
  dispatchBtnText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 14,
  },
  completeBtn: {
    backgroundColor: '#16A34A',
  },
  completeBtnText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 14,
  },
});
