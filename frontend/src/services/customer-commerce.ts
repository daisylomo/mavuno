import { liveRequest } from './live-api';

export type Cart = {
  items: Array<{ listing_id: string; title: string; quantity: string; quantity_unit: string;
    unit_price: string; line_total: string; available_quantity: string }>;
  subtotal_amount: string;
  currency: string;
};

export type Order = { id: string; status: string; total_amount: string; currency: string };
export type Payment = { id: string; state: string; amount: string; currency: string; failure_code: string | null };
export type Address = { id: string; label: string; line_1: string; locality: string; county: string };

export const customerCommerce = {
  cart: () => liveRequest<Cart>('/cart'),
  add: (listingId: string, quantity: number) => liveRequest<Cart>(`/cart/items/${listingId}`, {
    method: 'PUT', body: { quantity },
  }),
  remove: (listingId: string) => liveRequest<void>(`/cart/items/${listingId}`, { method: 'DELETE' }),
  checkout: (key: string, addressId: string) => liveRequest<Order>('/orders', {
    method: 'POST', body: { delivery_address_id: addressId }, idempotencyKey: key,
  }),
  addresses: () => liveRequest<Address[]>('/users/me/addresses'),
  createAddress: (input: { line_1: string; locality: string; county: string }) =>
    liveRequest<Address>('/users/me/addresses', {
      method: 'POST', body: { label: 'Delivery', ...input, country_code: 'KE', is_default: true },
    }),
  pay: (orderId: string, phone: string, key: string) => liveRequest<Payment>('/payments', {
    method: 'POST', body: { order_id: orderId, rail: 'mpesa', phone_e164: phone }, idempotencyKey: key,
  }),
  payment: (id: string) => liveRequest<Payment>(`/payments/${id}`),
  order: (id: string) => liveRequest<Order>(`/orders/${id}`),
  orders: () => liveRequest<Order[]>('/users/me/orders'),
  payments: (orderId: string) => liveRequest<Payment[]>(`/orders/${orderId}/payments`),
};
