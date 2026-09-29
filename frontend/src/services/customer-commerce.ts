import { liveRequest } from './live-api';

export type Cart = {
  items: Array<{ listing_id: string; title: string; quantity: string; quantity_unit: string;
    unit_price: string; line_total: string; available_quantity: string }>;
  subtotal_amount: string;
  currency: string;
};

export type Refund = {
  id: string; amount: string; currency: string; reason: string; state: string;
  farmer_id: string | null; provider_ref: string | null; completed_at: string | null;
};
export type OrderItem = {
  listing_id: string; farmer_id: string; listing_title: string; quantity: string;
  quantity_unit: string; unit_price: string; line_total: string;
};
export type Order = {
  id: string; status: string; total_amount: string; subtotal_amount?: string; currency: string;
  reservation_expires_at?: string; paid_at?: string | null; items?: OrderItem[]; refunds?: Refund[];
};
export type Payment = {
  id: string; state: string; amount: string; currency: string; failure_code: string | null;
  failure_message?: string | null; provider_transaction_ref?: string | null;
};
export type Address = { id: string; label: string; line_1: string; locality: string; county: string };
export type Fulfilment = {
  id: string; order_id: string; farmer_id: string; method: 'pickup' | 'delivery'; status: string;
  location_label: string; location_details: string; window_start: string;
  window_end: string; version: number;
};

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
  /** One hand-over per farmer in the order. */
  fulfilments: (orderId: string) => liveRequest<Fulfilment[]>(`/fulfilments/${orderId}/parts`),
  createDeliveryPlan: (orderId: string, address: Address, day: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) throw new Error('Enter a delivery date as YYYY-MM-DD.');
    const calendarDay = new Date(`${day}T00:00:00Z`);
    const start = new Date(`${day}T09:00:00+03:00`);
    const end = new Date(`${day}T17:00:00+03:00`);
    if (Number.isNaN(calendarDay.valueOf()) || calendarDay.toISOString().slice(0, 10) !== day ||
        start.valueOf() <= Date.now()) throw new Error('Choose a valid future delivery date.');
    // The first plan covers every farmer in the order; each then hands over separately.
    return liveRequest<Fulfilment>(`/fulfilments/${orderId}`, {
      method: 'PATCH', body: {
        method: 'delivery', location_label: address.label,
        location_details: `${address.line_1}, ${address.locality}, ${address.county}`,
        window_start: start.toISOString(), window_end: end.toISOString(),
      },
    });
  },
  completeDelivery: (part: Fulfilment) =>
    liveRequest<Fulfilment>(
      `/fulfilments/${part.order_id}/status?farmer_id=${encodeURIComponent(part.farmer_id)}`, {
        method: 'POST', body: { status: 'completed', expected_version: part.version },
      }),
  cancelOrder: (orderId: string, reason?: string) => liveRequest<Order>(`/orders/${orderId}/cancel`, {
    method: 'POST', body: { reason: reason ?? null },
  }),
  /** Asks the server to check with M-PESA now instead of waiting for the callback. */
  refreshPayment: (id: string) => liveRequest<Payment>(`/payments/${id}/refresh`, { method: 'POST' }),
  pay: (orderId: string, phone: string, key: string) => liveRequest<Payment>('/payments', {
    method: 'POST', body: { order_id: orderId, rail: 'mpesa', phone_e164: phone }, idempotencyKey: key,
  }),
  payment: (id: string) => liveRequest<Payment>(`/payments/${id}`),
  order: (id: string) => liveRequest<Order>(`/orders/${id}`),
  orders: () => liveRequest<Order[]>('/users/me/orders'),
  payments: (orderId: string) => liveRequest<Payment[]>(`/orders/${orderId}/payments`),
};
