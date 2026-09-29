import AsyncStorage from '@react-native-async-storage/async-storage';
import { apiBaseUrl } from '@/components/customer-catalog-api';
import { liveRequest } from './live-api';
import {
  FarmerOrder,
  FarmerPublicDetails,
  FarmerStats,
  OrderStatus,
  ProduceListing,
  ListingStatus,
} from '@/types/farmer';
import {
  base64Bytes,
  harvestIsoDate,
  harvestLabel,
  photoSource,
  splitDataUrl,
} from '@/components/listing-details';

/** Photos are resized before upload; the API rejects anything larger than this. */
export const MAX_PHOTO_BYTES = 1_500_000;

export type PhotoUpload = { contentType: 'image/jpeg' | 'image/png' | 'image/webp'; base64: string };

/** The listing was published, but its photo was not saved. */
export class ListingPhotoError extends Error {}

const LISTINGS_STORAGE_KEY = '@mavuno_farmer_listings_clean';
const ORDERS_STORAGE_KEY = '@mavuno_farmer_orders_clean';

type ApiListing = {
  id: string; version: number; product_id: string; title: string; category_slug: string;
  price_amount: string; available_quantity: string; quantity_unit: ProduceListing['unit'];
  harvest_date: string | null; description: string | null; status: string; created_at: string;
  images?: Array<{ id: string; object_key: string; alt_text?: string; sort_order: number; url?: string | null }>;
};

type ApiFarmerProfile = {
  farm_name: string | null; county: string | null; locality: string | null;
  farming_practices: string | null; offers_pickup: boolean; offers_delivery: boolean;
  delivery_radius_km: number | null;
};

type ApiFarmerOrder = {
  id: string; order_number: string; customer_name: string; customer_phone: string | null;
  delivery_location: string | null; total_amount: string; status: string; created_at: string;
  reservation_expires_at?: string | null; fulfilment_status?: string | null;
  fulfilment_version?: number | null; other_farmers?: number;
  items: Array<{ listing_id: string; listing_title: string; quantity: string;
    quantity_unit: ProduceListing['unit']; unit_price: string; line_total: string }>;
};

type ApiFulfilment = { status: string; version: number; method: 'pickup' | 'delivery' };

const categoryLabels: Record<string, ProduceListing['category']> = {
  vegetables: 'Vegetables', fruits: 'Fruits', 'grains-cereals': 'Grains & Cereals',
  'tubers-roots': 'Tubers & Roots', 'dairy-poultry': 'Dairy & Poultry',
};

function listingImage(item: ApiListing): string | undefined {
  const source = photoSource(item.images, apiBaseUrl());
  if (source.kind === 'preset') return `preset:${source.key}`;
  if (source.kind === 'uploaded') return source.uri;
  return undefined;
}

function fromApi(item: ApiListing): ProduceListing {
  return {
    id: item.id, version: item.version, productId: item.product_id, title: item.title,
    category: categoryLabels[item.category_slug] ?? 'Vegetables', price: Number(item.price_amount),
    quantity: Number(item.available_quantity), unit: item.quantity_unit,
    harvestDate: harvestLabel(item.harvest_date) ?? 'Harvest date not given',
    description: item.description ?? '',
    status: item.status === 'active' && Number(item.available_quantity) <= 10 ? 'low_stock'
      : item.status === 'sold_out' ? 'sold_out' : item.status === 'active' ? 'active' : 'paused',
    imageUrl: listingImage(item),
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
    listingData: Omit<ProduceListing, 'id' | 'createdAt'>,
    photo?: PhotoUpload,
  ): Promise<ProduceListing> {
    if (apiBaseUrl()) {
      if (!listingData.productId) throw new Error('Select a produce type before publishing.');
      if (!Number.isInteger(listingData.price)) {
        throw new Error('Enter the price in whole shillings — M-PESA cannot charge cents.');
      }
      const upload = photo ?? (listingData.imageUrl?.startsWith('data:')
        ? splitDataUrl(listingData.imageUrl) : null);
      if (upload && base64Bytes(upload.base64) > MAX_PHOTO_BYTES) {
        throw new Error('That photo is too large. Choose a smaller one or crop it.');
      }
      const created = await liveRequest<ApiListing>('/listings', {
        method: 'POST', body: {
          product_id: listingData.productId, title: listingData.title,
          // Only what the farmer wrote; nothing is claimed on their behalf.
          description: listingData.description.trim() || null,
          price_amount: listingData.price,
          available_quantity: listingData.quantity, quantity_unit: listingData.unit,
          harvest_date: harvestIsoDate(listingData.harvestDate),
        },
      });

      let photoWarning = false;
      if (upload) {
        try {
          await liveRequest(`/listings/${created.id}/photos`, {
            method: 'POST',
            body: { content_type: upload.contentType, content_base64: upload.base64, alt_text: listingData.title },
          });
        } catch {
          photoWarning = true;
        }
      } else if (listingData.imageUrl?.startsWith('preset:')) {
        await liveRequest(`/listings/${created.id}/images`, {
          method: 'POST',
          body: {
            object_key: `preset/${listingData.imageUrl.slice('preset:'.length)}`,
            alt_text: `Illustration of ${listingData.title}`,
            sort_order: 0,
          },
        }).catch(() => { photoWarning = true; });
      }

      const active = await liveRequest<ApiListing>(`/listings/${created.id}`, {
        method: 'PATCH', body: { expected_version: created.version, status: 'active' },
      });
      if (photoWarning) {
        throw new ListingPhotoError('Your listing is live, but the photo could not be saved. Try adding it again later.');
      }
      return fromApi(active);
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
        // The farmer's own hand-over for their items in this order.
        const plan = order.fulfilment_status
          ? await liveRequest<ApiFulfilment>(`/fulfilments/${order.id}`) : null;
        const part = plan?.status ?? order.fulfilment_status ?? null;
        const status: OrderStatus = order.status === 'pending_payment' ? 'awaiting_payment'
          : ['cancelled', 'refunded', 'expired'].includes(order.status) || part === 'cancelled' ? 'cancelled'
          : order.status === 'completed' || part === 'completed' ? 'completed'
          : !part || part === 'pending' ? 'pending'
          : part === 'scheduled' ? 'accepted'
          : part === 'ready_for_handover' ? 'ready_for_pickup'
          : part === 'in_transit' ? 'dispatched' : 'pending';
        return {
        id: order.id, orderNumber: order.order_number, customerName: order.customer_name,
        customerPhone: order.customer_phone ?? (order.status === 'pending_payment'
          ? 'Shown once paid' : 'Not provided'),
        deliveryLocation: order.delivery_location ?? (order.status === 'pending_payment'
          ? 'Shown once paid' : 'Not provided'),
        totalAmount: Number(order.total_amount),
        status,
        paymentMethod: 'M-Pesa', createdAt: order.created_at,
        fulfilmentStatus: part ?? undefined,
        fulfilmentVersion: plan?.version ?? order.fulfilment_version ?? undefined,
        fulfilmentMethod: plan?.method,
        reservationExpiresAt: order.reservation_expires_at ?? undefined,
        otherFarmers: order.other_farmers ?? 0,
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

  /** The farmer can no longer supply their items: their stock returns and the buyer is refunded. */
  async withdrawFromOrder(order: FarmerOrder, reason: string): Promise<void> {
    if (!apiBaseUrl() || !order.fulfilmentVersion) throw new Error('This order has no hand-over plan yet.');
    await liveRequest(`/fulfilments/${order.id}/status`, {
      method: 'POST', body: { status: 'cancelled', expected_version: order.fulfilmentVersion, reason },
    });
  },

  async getPublicDetails(): Promise<FarmerPublicDetails | null> {
    if (!apiBaseUrl()) return null;
    const value = await liveRequest<ApiFarmerProfile>('/users/me/farmer');
    return {
      farmName: value.farm_name ?? '', county: value.county ?? '', locality: value.locality ?? '',
      farmingPractices: value.farming_practices ?? '', offersPickup: value.offers_pickup,
      offersDelivery: value.offers_delivery,
      deliveryRadiusKm: value.delivery_radius_km ? String(value.delivery_radius_km) : '',
    };
  },

  async savePublicDetails(details: FarmerPublicDetails): Promise<void> {
    const radius = details.deliveryRadiusKm.trim() ? Number(details.deliveryRadiusKm) : null;
    if (radius !== null && (!Number.isInteger(radius) || radius < 1 || radius > 500)) {
      throw new Error('Delivery radius must be a whole number of kilometres between 1 and 500.');
    }
    await liveRequest('/users/me/farmer', {
      method: 'PATCH', body: {
        farm_name: details.farmName.trim() || null, county: details.county.trim() || null,
        locality: details.locality.trim() || null,
        farming_practices: details.farmingPractices.trim() || null,
        offers_pickup: details.offersPickup, offers_delivery: details.offersDelivery,
        delivery_radius_km: details.offersDelivery ? radius : null,
      },
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
