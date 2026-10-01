export type Unit = 'kg' | 'g' | 'crate' | 'piece' | 'bunch' | 'bag';
export type Conversation = {
  id: string; scope_type: 'listing' | 'order'; scope_id: string;
  buyer_id: string; farmer_id: string; last_message_at: string | null;
  counterpart_name: string; scope_label: string; last_message_preview: string | null; unread_count: number;
};
export type Message = { id: string; conversation_id: string; sender_id: string;
  client_message_id: string; body: string; created_at: string };
export type MessagePage = { items: Message[]; next_cursor: string | null };
export type Notification = { id: string; title: string; body: string; kind: string;
  data: Record<string, unknown>; read_at: string | null; created_at: string };
export type Preferences = { messages_push: boolean; orders_push: boolean };
export type Plan = { id: string; name: string; audience: 'buyer' | 'farmer'; active: boolean;
  price_amount: string; currency: string; billing_interval: 'month' | 'year'; features: string[] };
export type Subscription = { id: string; plan_id: string; status: string; account_reference: string;
  verified_at: string | null; current_period_start: string | null; current_period_end: string | null };
export type PremiumFeature = 'prebooking' | 'insights';
export type Entitlements = { premium: boolean; features: string[]; provider: string | null;
  expires_at: string | null; purchases_available: boolean };
export type Prebooking = { id: string; buyer_id: string; farmer_id: string; product_id: string;
  listing_id: string | null; quantity: string; quantity_unit: Unit; target_price: string | null;
  currency: string; window_start: string; window_end: string; notes: string | null;
  status: string; version: number };
export type Insights = { active_listings: number; units_available: string;
  completed_order_lines: number; gross_sales: string };
export type BookingListing = { id: string; title: string; farmer_id: string; product_id: string;
  quantity_unit: Unit; farmer?: { display_name: string } | null };
export type RequestOptions = { method?: string; body?: unknown; idempotencyKey?: string };
export type Request = <T>(path: string, options?: RequestOptions) => Promise<T>;

export function uuid(value: string): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
    throw new Error('This link is invalid. Open the item again from Mavuno.');
  }
  return value;
}

export function instant(value: string): number {
  return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function mergeMessages(current: Message[], incoming: Message[]): Message[] {
  const unique = new Map(current.map(message => [message.id, message]));
  for (const message of incoming) unique.set(message.id, message);
  return [...unique.values()].sort((a, b) => instant(a.created_at) - instant(b.created_at) || a.id.localeCompare(b.id));
}

/** Premium is decided by the backend; store purchases count only once it has verified them. */
export function hasEntitlement(entitlements: Entitlements | null | undefined, feature: PremiumFeature): boolean {
  return !!entitlements?.premium && entitlements.features.includes(feature);
}

export function bookingActions(booking: Prebooking, userId: string): Array<'accepted' | 'rejected' | 'cancelled' | 'fulfilled'> {
  if (booking.buyer_id === userId && ['requested', 'accepted'].includes(booking.status)) return ['cancelled'];
  if (booking.farmer_id === userId) {
    if (booking.status === 'requested') return ['accepted', 'rejected'];
    if (booking.status === 'accepted') return ['fulfilled'];
  }
  return [];
}

/** Kenyan dates are converted explicitly; handset timezone does not change the requested harvest window. */
export function harvestWindow(startDay: string, endDay: string, now = Date.now()) {
  for (const day of [startDay, endDay]) {
    const parsed = new Date(`${day}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== day) {
      throw new Error('Enter valid harvest dates as YYYY-MM-DD.');
    }
  }
  const start = new Date(`${startDay}T08:00:00+03:00`);
  const end = new Date(`${endDay}T18:00:00+03:00`);
  if (start.valueOf() <= now || end.valueOf() <= start.valueOf()) throw new Error('Choose a future harvest window ending on or after the start date.');
  return { window_start: start.toISOString(), window_end: end.toISOString() };
}

export function createSocialApi(request: Request) {
  return {
    conversations: () => request<Conversation[]>('/conversations/summary'),
    start: (scope: 'listing' | 'order', scopeId: string, farmerId?: string) => request<{ id: string }>('/conversations', {
      method: 'POST', body: { scope_type: scope, scope_id: uuid(scopeId), ...(farmerId ? { farmer_id: uuid(farmerId) } : {}) },
    }),
    messages: (id: string, cursor?: string) => request<MessagePage>(`/conversations/${uuid(id)}/messages?latest_first=true&limit=50${cursor ? `&cursor=${uuid(cursor)}` : ''}`),
    send: (id: string, clientId: string, body: string) => {
      const normalized = body.trim();
      if (!normalized || normalized.length > 4000) throw new Error('Write a message between 1 and 4,000 characters.');
      return request<Message>(`/conversations/${uuid(id)}/messages`, { method: 'POST', body: { client_message_id: uuid(clientId), body: normalized } });
    },
    read: (id: string, messageId: string) => request<void>(`/conversations/${uuid(id)}/read`, { method: 'PUT', body: { last_read_message_id: uuid(messageId) } }),
    notifications: () => request<Notification[]>('/notifications'),
    readNotification: (id: string) => request<Notification>(`/notifications/${uuid(id)}/read`, { method: 'PUT' }),
    preferences: () => request<Preferences>('/notification-preferences'),
    updatePreferences: (preferences: Preferences) => request<Preferences>('/notification-preferences', { method: 'PUT', body: preferences }),
    availability: () => request<{ subscriptions_available: boolean }>('/premium/availability'),
    plans: () => request<Plan[]>('/premium/plans'),
    subscriptions: () => request<Subscription[]>('/premium/subscriptions'),
    subscribe: (planId: string, key: string) => request<Subscription>('/premium/subscriptions', { method: 'POST', body: { plan_id: uuid(planId) }, idempotencyKey: key }),
    entitlements: () => request<Entitlements>('/premium/entitlements'),
    syncStorePurchases: () => request<Entitlements>('/premium/store/sync', { method: 'POST' }),
    bookings: () => request<Prebooking[]>('/prebookings'),
    listing: (id: string) => request<BookingListing>(`/listings/${uuid(id)}`),
    createBooking: (body: { farmer_id: string; product_id: string; listing_id: string; quantity: string; quantity_unit: Unit; target_price: string | null; notes: string | null; window_start: string; window_end: string }) => request<Prebooking>('/prebookings', { method: 'POST', body }),
    transitionBooking: (booking: Prebooking, status: string) => request<Prebooking>(`/prebookings/${uuid(booking.id)}/status`, { method: 'POST', body: { status, expected_version: booking.version } }),
    insights: () => request<Insights>('/premium/insights/farmer'),
  };
}
