export type ProduceCategory = 'Vegetables' | 'Fruits' | 'Grains & Cereals' | 'Tubers & Roots' | 'Dairy & Poultry';

export type ProduceUnit = 'kg' | 'crate' | 'bunch' | 'bag' | 'piece';

export type ListingStatus = 'active' | 'low_stock' | 'sold_out' | 'paused';

export interface ProduceListing {
  id: string;
  title: string;
  category: ProduceCategory;
  price: number; // in KSh
  quantity: number;
  unit: ProduceUnit;
  harvestDate: string;
  description: string;
  status: ListingStatus;
  imageUrl?: string;
  createdAt: string;
}

export type OrderStatus = 'pending' | 'accepted' | 'ready_for_pickup' | 'dispatched' | 'completed' | 'cancelled';

export interface OrderItem {
  listingId: string;
  title: string;
  quantity: number;
  unit: ProduceUnit;
  price: number;
  lineTotal: number;
}

export interface FarmerOrder {
  id: string;
  orderNumber: string;
  customerName: string;
  customerPhone: string;
  deliveryLocation: string;
  items: OrderItem[];
  totalAmount: number;
  status: OrderStatus;
  paymentMethod: 'M-Pesa' | 'Cash on Delivery';
  createdAt: string;
}

export interface FarmerStats {
  activeListingsCount: number;
  pendingOrdersCount: number;
  totalRevenue: number;
}
