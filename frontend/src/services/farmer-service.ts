import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiBaseUrl } from '@/components/customer-catalog-api';
import { liveRequest } from './live-api';
import {
  FarmerOrder,
  FarmerStats,
  OrderStatus,
  ProduceListing,
  ListingStatus,
} from '@/types/farmer';

const LISTINGS_STORAGE_KEY = '@mavuno_farmer_listings_clean';
const ORDERS_STORAGE_KEY = '@mavuno_farmer_orders_clean';

type ApiListing = {
  id: string; version: number; product_id: string; title: string; category_slug: string;
  price_amount: string; available_quantity: string; quantity_unit: ProduceListing['unit'];
  harvest_date: string | null; description: string | null; status: string; created_at: string;
  images?: Array<{ id: string; object_key: string; alt_text?: string; sort_order: number }>;
};

type ApiFarmerOrder = {
  id: string; order_number: string; customer_name: string; customer_phone: string | null;
  delivery_location: string | null; total_amount: string; status: string; created_at: string;
  items: Array<{ listing_id: string; listing_title: string; quantity: string;
    quantity_unit: ProduceListing['unit']; unit_price: string; line_total: string }>;
};

type ApiFulfilment = { status: string; version: number; method: 'pickup' | 'delivery' };

const categoryLabels: Record<string, ProduceListing['category']> = {
  vegetables: 'Vegetables', fruits: 'Fruits', 'grains-cereals': 'Grains & Cereals',
  'tubers-roots': 'Tubers & Roots', 'dairy-poultry': 'Dairy & Poultry',
};

function fromApi(item: ApiListing): ProduceListing {
  const firstImage = item.images && item.images.length > 0 ? item.images[0].object_key : undefined;
  return {
    id: item.id, version: item.version, productId: item.product_id, title: item.title,
    category: categoryLabels[item.category_slug] ?? 'Vegetables', price: Number(item.price_amount),
    quantity: Number(item.available_quantity), unit: item.quantity_unit,
    harvestDate: item.harvest_date ?? 'Fresh harvest', description: item.description ?? '',
    status: item.status === 'active' && Number(item.available_quantity) <= 10 ? 'low_stock'
      : item.status === 'sold_out' ? 'sold_out' : item.status === 'active' ? 'active' : 'paused',
    imageUrl: firstImage,
    createdAt: item.created_at,
  };
}

export const farmerService = {
  async getListings(): Promise<ProduceListing[]> {
    if (apiBaseUrl()) return (await liveRequest<ApiListing[]>('/farmers/me/listings')).map(fromApi);
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
    if (apiBaseUrl()) {
      if (!listingData.productId) throw new Error('Select a produce type before publishing.');
      const created = await liveRequest<ApiListing>('/listings', {
        method: 'POST', body: {
          product_id: listingData.productId, title: listingData.title,
          description: listingData.description, price_amount: listingData.price,
          available_quantity: listingData.quantity, quantity_unit: listingData.unit,
        },
      });

      if (listingData.imageUrl) {
        try {
          const key = listingData.imageUrl.startsWith('data:')
            ? `listings/${created.id}/photo_${Date.now()}.jpg`
            : listingData.imageUrl.startsWith('preset:')
            ? `listings/${listingData.imageUrl.replace('preset:', '')}.jpg`
            : listingData.imageUrl.replace(/^\/+/, '');
          await liveRequest(`/listings/${created.id}/images`, {
            method: 'POST',
            body: {
              object_key: key,
              alt_text: listingData.title,
              sort_order: 0,
            },
          });
        } catch {
          // Gracefully continue if backend object storage is optional
        }
      }

      const active = await liveRequest<ApiListing>(`/listings/${created.id}`, {
        method: 'PATCH', body: { expected_version: created.version, status: 'active' },
      });
      const result = fromApi(active);
      return {
        ...result,
        imageUrl: listingData.imageUrl || result.imageUrl,
      };
    }
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
    if (apiBaseUrl()) {
      const listing = (await liveRequest<ApiListing[]>('/farmers/me/listings')).find((item) => item.id === id);
      if (!listing) throw new Error('Listing no longer exists. Refresh your catalog.');
      await liveRequest(`/listings/${id}`, {
        method: 'PATCH', body: { expected_version: listing.version, status: status === 'low_stock' ? 'active' : status },
      });
      return;
    }
    const listings = await this.getListings();
    const updated = listings.map((item) => (item.id === id ? { ...item, status } : item));
    await AsyncStorage.setItem(LISTINGS_STORAGE_KEY, JSON.stringify(updated));
  },

  async deleteListing(id: string): Promise<void> {
    if (apiBaseUrl()) {
      const listing = (await liveRequest<ApiListing[]>('/farmers/me/listings')).find((item) => item.id === id);
      if (!listing) throw new Error('Listing no longer exists. Refresh your catalog.');
      await liveRequest(`/listings/${id}?expected_version=${listing.version}`, { method: 'DELETE' });
      return;
    }
    const listings = await this.getListings();
    const updated = listings.filter((item) => item.id !== id);
    await AsyncStorage.setItem(LISTINGS_STORAGE_KEY, JSON.stringify(updated));
  },

  async getOrders(): Promise<FarmerOrder[]> {
    if (apiBaseUrl()) {
      const orders = await liveRequest<ApiFarmerOrder[]>('/farmers/me/orders');
      return Promise.all(orders.map(async (order) => {
        const plan = ['fulfilment', 'completed'].includes(order.status)
          ? await liveRequest<ApiFulfilment>(`/fulfilments/${order.id}`) : null;
        const status: OrderStatus = order.status === 'completed' ? 'completed'
          : !plan || plan.status === 'pending' ? 'pending'
          : plan.status === 'scheduled' ? 'accepted'
          : plan.status === 'ready_for_handover' ? 'ready_for_pickup'
          : plan.status === 'in_transit' ? 'dispatched'
          : plan.status === 'completed' ? 'completed' : 'cancelled';
        return {
        id: order.id, orderNumber: order.order_number, customerName: order.customer_name,
        customerPhone: order.customer_phone ?? 'Not provided',
        deliveryLocation: order.delivery_location ?? 'Not provided',
        totalAmount: Number(order.total_amount),
        status,
        paymentMethod: 'M-Pesa', createdAt: order.created_at,
        fulfilmentStatus: plan?.status, fulfilmentVersion: plan?.version, fulfilmentMethod: plan?.method,
        items: order.items.map((item) => ({ listingId: item.listing_id, title: item.listing_title,
          quantity: Number(item.quantity), unit: item.quantity_unit,
          price: Number(item.unit_price), lineTotal: Number(item.line_total) })),
        };
      }));
    }
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
    if (apiBaseUrl()) throw new Error('Order coordination requires a confirmed fulfilment schedule.');
    const orders = await this.getOrders();
    const updated = orders.map((order) =>
      order.id === orderId ? { ...order, status } : order
    );
    await AsyncStorage.setItem(ORDERS_STORAGE_KEY, JSON.stringify(updated));
  },

  async advanceFulfilment(order: FarmerOrder): Promise<void> {
    if (!apiBaseUrl() || !order.fulfilmentStatus || !order.fulfilmentVersion) {
      throw new Error('The buyer must set a delivery plan first.');
    }
    const next = order.fulfilmentStatus === 'pending' ? 'scheduled'
      : order.fulfilmentStatus === 'scheduled' ? 'ready_for_handover'
      : order.fulfilmentStatus === 'ready_for_handover' && order.fulfilmentMethod === 'delivery'
        ? 'in_transit' : null;
    if (!next) throw new Error('No further farmer action is available for this order.');
    await liveRequest(`/fulfilments/${order.id}/status`, {
      method: 'POST', body: { status: next, expected_version: order.fulfilmentVersion },
    });
  },

  async getStats(): Promise<FarmerStats> {
    if (apiBaseUrl()) {
      const [listings, orders] = await Promise.all([this.getListings(), this.getOrders()]);
      return { activeListingsCount: listings.filter((item) => item.status === 'active' || item.status === 'low_stock').length,
        pendingOrdersCount: orders.filter((item) => item.status === 'pending').length,
        totalRevenue: orders.filter((item) => item.status === 'completed').reduce((sum, item) => sum + item.totalAmount, 0) };
    }
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
