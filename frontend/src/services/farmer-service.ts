import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  FarmerOrder,
  FarmerStats,
  OrderStatus,
  ProduceListing,
  ListingStatus,
} from '@/types/farmer';

const LISTINGS_STORAGE_KEY = '@mavuno_farmer_listings_clean';
const ORDERS_STORAGE_KEY = '@mavuno_farmer_orders_clean';

export const farmerService = {
  async getListings(): Promise<ProduceListing[]> {
    try {
      const stored = await AsyncStorage.getItem(LISTINGS_STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
      return [];
    } catch {
      return [];
    }
  },

  async createListing(
    listingData: Omit<ProduceListing, 'id' | 'createdAt'>
  ): Promise<ProduceListing> {
    const listings = await this.getListings();
    const newListing: ProduceListing = {
      ...listingData,
      id: 'prod_' + Date.now(),
      createdAt: new Date().toISOString(),
    };
    const updated = [newListing, ...listings];
    await AsyncStorage.setItem(LISTINGS_STORAGE_KEY, JSON.stringify(updated));
    return newListing;
  },

  async updateListingStatus(id: string, status: ListingStatus): Promise<void> {
    const listings = await this.getListings();
    const updated = listings.map((item) => (item.id === id ? { ...item, status } : item));
    await AsyncStorage.setItem(LISTINGS_STORAGE_KEY, JSON.stringify(updated));
  },

  async deleteListing(id: string): Promise<void> {
    const listings = await this.getListings();
    const updated = listings.filter((item) => item.id !== id);
    await AsyncStorage.setItem(LISTINGS_STORAGE_KEY, JSON.stringify(updated));
  },

  async getOrders(): Promise<FarmerOrder[]> {
    try {
      const stored = await AsyncStorage.getItem(ORDERS_STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored);
      }
      return [];
    } catch {
      return [];
    }
  },

  async updateOrderStatus(orderId: string, status: OrderStatus): Promise<void> {
    const orders = await this.getOrders();
    const updated = orders.map((order) =>
      order.id === orderId ? { ...order, status } : order
    );
    await AsyncStorage.setItem(ORDERS_STORAGE_KEY, JSON.stringify(updated));
  },

  async getStats(): Promise<FarmerStats> {
    const listings = await this.getListings();
    const orders = await this.getOrders();

    const activeListingsCount = listings.filter((l) => l.status === 'active' || l.status === 'low_stock').length;
    const pendingOrdersCount = orders.filter((o) => o.status === 'pending').length;
    const totalRevenue = orders
      .filter((o) => o.status === 'completed' || o.status === 'dispatched' || o.status === 'accepted')
      .reduce((acc, curr) => acc + curr.totalAmount, 0);

    return {
      activeListingsCount,
      pendingOrdersCount,
      totalRevenue,
    };
  },
};
