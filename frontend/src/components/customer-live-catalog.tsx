import { Image } from 'expo-image';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from 'react-native';

import {
  getCategories,
  getFarmer,
  getListing,
  getListings,
  listingImageUrl,
  type Category,
  type FarmerProfile,
  type FarmerSummary,
  type Listing,
} from '@/components/customer-catalog-api';
import { formatQuantity, secondaryName } from '@/components/customer-live-catalog-format';
import {
  farmerPlace,
  handoverOptions,
  harvestLabel,
  memberSince,
  photoSource,
  reservationDeadline,
  type PresetPhotoKey,
} from '@/components/listing-details';
import { customerCommerce, type Address, type Cart, type Fulfilment, type Order, type Payment } from '@/services/customer-commerce';
import { normalizePhone, userService } from '@/services/user-service';

const PRESET_PHOTOS: Record<PresetPhotoKey, number> = {
  tomatoes: require('@/assets/products/tomatoes.jpg'),
  spinach: require('@/assets/products/spinach.jpg'),
  mangoes: require('@/assets/products/mangoes.jpg'),
  bananas: require('@/assets/products/bananas.jpg'),
  carrots: require('@/assets/products/carrots.jpg'),
  avocados: require('@/assets/products/avocados.jpg'),
  potatoes: require('@/assets/products/potatoes.jpg'),
  honey: require('@/assets/products/honey.jpg'),
};

const PAYMENT_POLL_MS = 5_000;
const PAYMENT_POLL_LIMIT = 36;
const OPEN_PAYMENT_STATES = ['pending_customer', 'processing'];

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The catalog request failed. Try again.';
}

function Photo({ listing, style, baseUrl }: {
  listing: Listing;
  style: { width: number | `${number}%`; height: number };
  baseUrl: string;
}) {
  const [failed, setFailed] = useState(false);
  const resolved = photoSource(listing.images, baseUrl);
  let legacy: string | null = null;
  try { legacy = resolved.kind === 'none' ? listingImageUrl(listing.images[0]?.object_key) : null; }
  catch { legacy = null; }
  const uri = resolved.kind === 'uploaded' ? resolved.uri : legacy;
  useEffect(() => setFailed(false), [uri]);
  if (resolved.kind === 'preset') {
    return (
      <View>
        <Image source={PRESET_PHOTOS[resolved.key]} style={style} contentFit="cover"
          accessibilityLabel={`Illustration of ${listing.title}`} />
        <Text style={styles.illustrationNote}>Illustration — not the farmer&apos;s own photo</Text>
      </View>
    );
  }
  return uri && !failed ? (
    <Image
      source={{ uri }}
      style={style}
      contentFit="cover"
      accessibilityLabel={listing.images[0]?.alt_text || listing.title}
      onError={() => setFailed(true)}
    />
  ) : (
    <View style={[style, styles.photoUnavailable]}>
      <Text style={styles.photoUnavailableText}>No photo from the farmer yet</Text>
    </View>
  );
}

function FarmerLine({ farmer }: { farmer: FarmerSummary | null | undefined }) {
  if (!farmer) return null;
  const place = farmerPlace(farmer);
  return (
    <Text style={styles.farmerLine} numberOfLines={1}>
      Sold by {farmer.display_name}{place ? ` · ${place}` : ''}
      {farmer.verification_status === 'verified' ? ' · ✓ Verified' : ''}
    </Text>
  );
}

function FarmerPanel({ farmer, onOpen }: { farmer: FarmerSummary; onOpen: () => void }) {
  const place = farmerPlace(farmer);
  const since = memberSince(farmer.member_since);
  return (
    <View style={styles.farmerPanel}>
      <Text style={styles.farmerPanelTitle}>About the farmer</Text>
      <Text style={styles.productName}>
        {farmer.display_name}{farmer.verification_status === 'verified' ? '  ✓' : ''}
      </Text>
      {!!farmer.farm_name && <Text style={styles.muted}>{farmer.farm_name}</Text>}
      {!!place && <Text style={styles.muted}>📍 {place}</Text>}
      <Text style={styles.muted}>
        {farmer.completed_orders} completed {farmer.completed_orders === 1 ? 'order' : 'orders'}
        {' · '}{farmer.active_listings} active {farmer.active_listings === 1 ? 'listing' : 'listings'}
      </Text>
      <Text style={styles.muted}>🚚 {handoverOptions(farmer)}</Text>
      {!!farmer.farming_practices && (
        <Text style={styles.muted}>🌱 {farmer.farming_practices} (as described by the farmer)</Text>
      )}
      {!!since && <Text style={styles.muted}>{since}</Text>}
      <Text style={styles.muted}>
        {farmer.verification_status === 'verified'
          ? 'Identity verified by Mavuno.' : 'Not yet verified by Mavuno.'}
      </Text>
      <Pressable accessibilityRole="button" onPress={onOpen}>
        <Text style={styles.link}>See this farmer&apos;s profile and produce</Text>
      </Pressable>
    </View>
  );
}

function Price({ listing }: { listing: Listing }) {
  const amount = Number(listing.price_amount);
  const formatted = Number.isFinite(amount)
    ? `${listing.currency} ${amount.toLocaleString('en-KE', { maximumFractionDigits: 2 })}`
    : `${listing.currency} ${listing.price_amount}`;
  return <Text style={styles.price}>{formatted} / {listing.quantity_unit}</Text>;
}

export default function CustomerLiveCatalog({ baseUrl }: { baseUrl: string }) {
  const { width } = useWindowDimensions();
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryError, setCategoryError] = useState<string | null>(null);
  const [categoryRetry, setCategoryRetry] = useState(0);
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [items, setItems] = useState<Listing[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailRetry, setDetailRetry] = useState(0);
  const [cart, setCart] = useState<Cart | null>(null);
  const [commerceError, setCommerceError] = useState<string | null>(null);
  const [commerceBusy, setCommerceBusy] = useState(false);
  const [phone, setPhone] = useState('');
  const [order, setOrder] = useState<Order | null>(null);
  const [payment, setPayment] = useState<Payment | null>(null);
  const [fulfilments, setFulfilments] = useState<Fulfilment[]>([]);
  const [farmerId, setFarmerId] = useState<string | null>(null);
  const [farmer, setFarmer] = useState<FarmerProfile | null>(null);
  const [farmerListings, setFarmerListings] = useState<Listing[]>([]);
  const [farmerError, setFarmerError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [, setClock] = useState(0);
  const [deliveryDay, setDeliveryDay] = useState('');
  const [recentOrders, setRecentOrders] = useState<Order[]>([]);
  const [checkoutKey, setCheckoutKey] = useState<string | null>(null);
  const [paymentKey, setPaymentKey] = useState<string | null>(null);
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [addressId, setAddressId] = useState<string | null>(null);
  const [street, setStreet] = useState('');
  const [locality, setLocality] = useState('');
  const [county, setCounty] = useState('');

  useEffect(() => {
    customerCommerce.cart().then(setCart).catch((error: unknown) => setCommerceError(errorMessage(error)));
    userService.getCurrentUser().then((user) => setPhone(user?.phone ?? ''));
    customerCommerce.addresses().then((items) => {
      setAddresses(items);
      if (items.length) setAddressId(items[0].id);
    }).catch((error: unknown) => setCommerceError(errorMessage(error)));
    customerCommerce.orders().then(async (orders) => {
      setRecentOrders(orders);
      const unfinished = orders.find((item) => item.status === 'pending_payment');
      if (!unfinished) return;
      setOrder(unfinished);
      const attempts = await customerCommerce.payments(unfinished.id);
      if (attempts.length) setPayment(attempts[0]);
    }).catch((error: unknown) => setCommerceError(errorMessage(error)));
  }, []);

  async function commerceAction(action: () => Promise<void>) {
    setCommerceBusy(true);
    setCommerceError(null);
    try { await action(); } catch (error) { setCommerceError(errorMessage(error)); }
    finally { setCommerceBusy(false); }
  }

  async function addToCart(listing: Listing) {
    await commerceAction(async () => {
      setCart(await customerCommerce.add(listing.id, 1));
      setSelectedId(null);
    });
  }

  async function checkout() {
    await commerceAction(async () => {
      let chosenAddress = addressId;
      if (!chosenAddress) {
        if (!street.trim() || !locality.trim() || !county.trim()) {
          throw new Error('Enter your street, locality and county for delivery.');
        }
        const created = await customerCommerce.createAddress({
          line_1: street.trim(), locality: locality.trim(), county: county.trim(),
        });
        setAddresses((items) => [created, ...items]);
        setAddressId(created.id);
        chosenAddress = created.id;
      }
      const key = checkoutKey ?? `checkout-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      setCheckoutKey(key);
      const created = await customerCommerce.checkout(key, chosenAddress);
      setOrder(created);
      setRecentOrders((current) => [created, ...current]);
      setPayment(null);
      setFulfilments([]);
      setCart(await customerCommerce.cart());
      setCheckoutKey(null);
    });
  }

  async function initiatePayment() {
    await commerceAction(async () => {
      if (!order) throw new Error('Create the order first.');
      const normalized = normalizePhone(phone);
      if (!/^\+254[17]\d{8}$/.test(normalized)) throw new Error('Enter a valid Kenyan M-Pesa phone number.');
      const key = paymentKey ?? `mpesa-${order.id}-${Date.now()}`;
      setPaymentKey(key);
      const created = await customerCommerce.pay(order.id, normalized, key);
      setPayment(created);
      setPaymentKey(null);
      setPollCount(0);
    });
  }

  async function checkPayment() {
    await commerceAction(async () => {
      if (!payment || !order) return;
      const current = OPEN_PAYMENT_STATES.includes(payment.state)
        ? await customerCommerce.refreshPayment(payment.id)
        : await customerCommerce.payment(payment.id);
      setPayment(current);
      const updatedOrder = await customerCommerce.order(order.id);
      setOrder(updatedOrder);
      setRecentOrders((items) => items.map((item) => item.id === updatedOrder.id ? updatedOrder : item));
    });
  }

  async function openOrder(item: Order) {
    await commerceAction(async () => {
      const current = await customerCommerce.order(item.id);
      setOrder(current);
      setPayment((await customerCommerce.payments(item.id))[0] ?? null);
      setFulfilments(['fulfilment', 'completed'].includes(current.status)
        ? await customerCommerce.fulfilments(item.id) : []);
    });
  }

  async function createDeliveryPlan() {
    await commerceAction(async () => {
      if (!order || order.status !== 'paid') throw new Error('Payment must be confirmed first.');
      const address = addresses.find((item) => item.id === addressId);
      if (!address) throw new Error('Select a delivery address.');
      await customerCommerce.createDeliveryPlan(order.id, address, deliveryDay.trim());
      setFulfilments(await customerCommerce.fulfilments(order.id));
      const current = await customerCommerce.order(order.id);
      setOrder(current);
      setRecentOrders((items) => items.map((item) => item.id === current.id ? current : item));
    });
  }

  async function completeDelivery(part: Fulfilment) {
    await commerceAction(async () => {
      if (!order) return;
      await customerCommerce.completeDelivery(part);
      setFulfilments(await customerCommerce.fulfilments(order.id));
      const current = await customerCommerce.order(order.id);
      setOrder(current);
      setRecentOrders((items) => items.map((item) => item.id === current.id ? current : item));
    });
  }

  async function cancelOrder() {
    await commerceAction(async () => {
      if (!order) return;
      const current = await customerCommerce.cancelOrder(order.id, 'Cancelled by buyer in the app');
      setOrder(current);
      setFulfilments(current.status === 'cancelled' ? fulfilments.map((part) => ({ ...part, status: 'cancelled' })) : fulfilments);
      setRecentOrders((items) => items.map((item) => item.id === current.id ? current : item));
    });
  }

  // While the M-PESA prompt is open, ask the server to check every few seconds so the order
  // updates on its own once the buyer approves (or dismisses) the prompt.
  useEffect(() => {
    if (!payment || !order || !OPEN_PAYMENT_STATES.includes(payment.state) || pollCount >= PAYMENT_POLL_LIMIT) {
      return;
    }
    const timer = setTimeout(() => {
      customerCommerce.refreshPayment(payment.id).then(async (current) => {
        setPayment(current);
        if (!OPEN_PAYMENT_STATES.includes(current.state)) {
          const updated = await customerCommerce.order(order.id);
          setOrder(updated);
          setRecentOrders((items) => items.map((item) => item.id === updated.id ? updated : item));
        }
      }).catch(() => undefined).finally(() => setPollCount((count) => count + 1));
    }, PAYMENT_POLL_MS);
    return () => clearTimeout(timer);
  }, [order, payment, pollCount]);

  // Keep the reservation countdown current.
  useEffect(() => {
    if (order?.status !== 'pending_payment') return;
    const timer = setInterval(() => setClock((value) => value + 1), 30_000);
    return () => clearInterval(timer);
  }, [order?.status]);

  useEffect(() => {
    if (farmerId === null) return;
    const controller = new AbortController();
    setFarmer(null);
    setFarmerListings([]);
    setFarmerError(null);
    Promise.all([
      getFarmer(baseUrl, farmerId, controller.signal),
      getListings(baseUrl, { search: '', category: null, farmerId }, controller.signal),
    ]).then(([profile, page]) => {
      if (controller.signal.aborted) return;
      setFarmer(profile);
      setFarmerListings(page.items);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setFarmerError(errorMessage(error));
    });
    return () => controller.abort();
  }, [baseUrl, farmerId]);

  useEffect(() => {
    const controller = new AbortController();
    setCategoryError(null);
    getCategories(baseUrl, controller.signal).then(setCategories).catch((error: unknown) => {
      if (!controller.signal.aborted) setCategoryError(errorMessage(error));
    });
    return () => controller.abort();
  }, [baseUrl, categoryRetry]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    const controller = new AbortController();
    setListError(null);
    if (search.trim().length === 1) {
      setLoading(false);
      setLoadingMore(false);
      setItems([]);
      setNextPage(null);
      return () => controller.abort();
    }
    if (search.trim() !== debouncedSearch) {
      setLoading(true);
      return () => controller.abort();
    }
    if (cursor === null) {
      setLoading(true);
      setItems([]);
    } else {
      setLoadingMore(true);
    }
    getListings(baseUrl, { search: debouncedSearch, category, cursor: cursor ?? undefined }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setItems((current) => cursor === null ? page.items : [
          ...current,
          ...page.items.filter((item) => !current.some((existing) => existing.id === item.id)),
        ]);
        setNextPage(page.next_cursor);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setListError(errorMessage(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
          setLoadingMore(false);
        }
      });
    return () => controller.abort();
  }, [baseUrl, category, cursor, debouncedSearch, retry, search]);

  useEffect(() => {
    if (selectedId === null) return;
    const controller = new AbortController();
    setSelected(null);
    setDetailError(null);
    getListing(baseUrl, selectedId, controller.signal)
      .then((listing) => { if (!controller.signal.aborted) setSelected(listing); })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setDetailError(errorMessage(error));
      });
    return () => controller.abort();
  }, [baseUrl, selectedId, detailRetry]);

  function changeFilter(nextCategory: string | null) {
    setItems([]);
    setNextPage(null);
    setCursor(null);
    setCategory(nextCategory);
  }

  function changeSearch(value: string) {
    setItems([]);
    setNextPage(null);
    setCursor(null);
    setSearch(value);
  }

  return (
    <View style={styles.page}>
      <ScrollView contentContainerStyle={styles.scrollContent} keyboardShouldPersistTaps="handled">
        <View style={styles.content}>
          <View style={styles.topRow}>
            <Text style={styles.liveBadge}>LIVE CATALOG</Text>
          </View>
          <View style={styles.hero}>
            <Text style={styles.heroTitle}>Welcome to the Customer Marketplace</Text>
            <Text style={styles.heroSubtitle}>Browse fresh produce from local farmers</Text>
          </View>
          <Text style={styles.disclaimer}>Live listings and secure checkout from Mavuno.</Text>
          {process.env.EXPO_PUBLIC_MAVUNO_PAYMENTS_SANDBOX === '1' && (
            <Text style={styles.disclaimer}>M-Pesa is in sandbox test mode. No real payment will be collected.</Text>
          )}
          {commerceError && <Text style={styles.error}>{commerceError}</Text>}
          <View style={styles.message}>
            <Text style={styles.sectionTitle}>Your cart</Text>
            {cart?.items.length ? cart.items.map((item) => (
              <View key={item.listing_id} style={styles.cartRow}>
                <Text style={styles.productName}>{item.title} · {item.quantity} {item.quantity_unit}</Text>
                <Text style={styles.price}>KES {item.line_total}</Text>
                <Pressable accessibilityRole="button" disabled={commerceBusy} onPress={() => commerceAction(async () => {
                  await customerCommerce.remove(item.listing_id);
                  setCart(await customerCommerce.cart());
                })}><Text style={styles.link}>Remove</Text></Pressable>
              </View>
            )) : <Text style={styles.muted}>Your cart is empty.</Text>}
            {!!cart?.items.length && !order && <>
              <Text style={styles.price}>Subtotal: KES {cart.subtotal_amount}</Text>
              <Text style={styles.productName}>Delivery address</Text>
              {addresses.map((address) => (
                <Pressable key={address.id} accessibilityRole="button"
                  onPress={() => setAddressId(address.id)} style={styles.cartRow}>
                  <Text style={styles.muted}>{addressId === address.id ? '● ' : '○ '}
                    {address.line_1}, {address.locality}, {address.county}</Text>
                </Pressable>
              ))}
              <Pressable accessibilityRole="button" onPress={() => setAddressId(null)}>
                <Text style={styles.link}>Use a new address</Text>
              </Pressable>
              {!addressId && <>
                <TextInput accessibilityLabel="Street address" value={street} onChangeText={setStreet}
                  placeholder="Street or building" style={styles.search} />
                <TextInput accessibilityLabel="Locality" value={locality} onChangeText={setLocality}
                  placeholder="Town or locality" style={styles.search} />
                <TextInput accessibilityLabel="County" value={county} onChangeText={setCounty}
                  placeholder="County" style={styles.search} />
              </>}
              <Pressable accessibilityRole="button" disabled={commerceBusy} onPress={checkout} style={styles.loadMore}>
                <Text style={styles.loadMoreText}>Place order</Text>
              </Pressable>
            </>}
            {order && <>
              <Text style={styles.productName}>Order {order.id.slice(0, 8)} · {order.status.replace(/_/g, ' ')}</Text>
              <Text style={styles.price}>Total: {order.currency} {order.total_amount}</Text>
              {!!order.subtotal_amount && Number(order.subtotal_amount) !== Number(order.total_amount) && (
                <Text style={styles.muted}>
                  Items come to {order.currency} {order.subtotal_amount}; M-PESA charges whole shillings, so
                  you pay the lower amount.
                </Text>
              )}
              {order.status === 'pending_payment' && !!order.reservation_expires_at && (
                <Text style={styles.muted}>
                  Your produce is reserved until {reservationDeadline(order.reservation_expires_at) ?? 'soon'}.
                  After that it goes back on sale.
                </Text>
              )}
              {order.status === 'pending_payment' && !payment && <>
                <TextInput accessibilityLabel="M-Pesa phone number" keyboardType="phone-pad" value={phone}
                  onChangeText={setPhone} placeholder="M-Pesa phone, e.g. 0712345678" style={styles.search} />
                <Pressable accessibilityRole="button" disabled={commerceBusy} onPress={initiatePayment} style={styles.loadMore}>
                  <Text style={styles.loadMoreText}>Request M-Pesa payment</Text>
                </Pressable>
              </>}
              {payment && <>
                <Text style={styles.description}>{payment.state === 'succeeded'
                  ? `M-Pesa payment confirmed${payment.provider_transaction_ref ? ` · receipt ${payment.provider_transaction_ref}` : ''}.`
                  : payment.state === 'reversed'
                    ? 'This payment was returned to your M-Pesa.'
                    : OPEN_PAYMENT_STATES.includes(payment.state)
                      ? 'M-Pesa request sent. Enter your PIN on your phone — this page updates by itself.'
                      : `M-Pesa: ${payment.state.replace(/_/g, ' ')}.`}</Text>
                {payment.failure_code && !OPEN_PAYMENT_STATES.includes(payment.state) && payment.state !== 'succeeded' && (
                  <Text style={styles.error}>
                    Payment not completed{payment.failure_message ? `: ${payment.failure_message}` : ''}.
                  </Text>
                )}
                {OPEN_PAYMENT_STATES.includes(payment.state) && pollCount < PAYMENT_POLL_LIMIT && (
                  <ActivityIndicator accessibilityLabel="Waiting for M-Pesa" color="#2196F3" />
                )}
                <Pressable accessibilityRole="button" disabled={commerceBusy} onPress={checkPayment} style={styles.loadMore}>
                  <Text style={styles.loadMoreText}>Check payment status now</Text>
                </Pressable>
                {order.status === 'pending_payment' && ['failed', 'cancelled', 'expired'].includes(payment.state) && (
                  <Pressable accessibilityRole="button" onPress={() => { setPayment(null); setPaymentKey(null); }}>
                    <Text style={styles.link}>Try M-Pesa again</Text>
                  </Pressable>
                )}
              </>}
              {(order.status === 'pending_payment' || (order.status === 'paid' && !fulfilments.length) ||
                (order.status === 'fulfilment' &&
                  fulfilments.every((part) => ['pending', 'scheduled', 'cancelled'].includes(part.status)))) &&
                !(payment && OPEN_PAYMENT_STATES.includes(payment.state)) && (
                <Pressable accessibilityRole="button" disabled={commerceBusy} onPress={cancelOrder}>
                  <Text style={styles.link}>
                    {order.status === 'pending_payment'
                      ? 'Cancel order and release the produce'
                      : 'Cancel order and request a refund'}
                  </Text>
                </Pressable>
              )}
              {!!order.refunds?.length && order.refunds.map((refund) => (
                <Text key={refund.id} style={styles.muted}>
                  Refund of {refund.currency} {Number(refund.amount).toLocaleString('en-KE')}:{' '}
                  {refund.state === 'completed' ? 'sent to you'
                    : refund.state === 'submitted' ? 'on its way to your M-Pesa'
                    : 'being processed by Mavuno'}
                </Text>
              ))}
              {order.status === 'paid' && !fulfilments.length && <>
                <Text style={styles.productName}>Plan delivery</Text>
                <Text style={styles.muted}>Choose an address and a delivery date. The window is 9:00–17:00 East Africa Time.
                  If your order has produce from more than one farmer, each farmer delivers their own items.</Text>
                {addresses.map((address) => (
                  <Pressable key={address.id} accessibilityRole="button"
                    onPress={() => setAddressId(address.id)} style={styles.cartRow}>
                    <Text style={styles.muted}>{addressId === address.id ? '● ' : '○ '}
                      {address.line_1}, {address.locality}, {address.county}</Text>
                  </Pressable>
                ))}
                <TextInput accessibilityLabel="Delivery date" value={deliveryDay} onChangeText={setDeliveryDay}
                  placeholder="YYYY-MM-DD" style={styles.search} />
                <Pressable accessibilityRole="button" disabled={commerceBusy} onPress={createDeliveryPlan} style={styles.loadMore}>
                  <Text style={styles.loadMoreText}>Send delivery plan to the farmers</Text>
                </Pressable>
              </>}
              {fulfilments.map((part) => {
                const items = order.items?.filter((item) => item.farmer_id === part.farmer_id) ?? [];
                return (
                  <View key={part.id} style={styles.cartRow}>
                    <Text style={styles.productName}>
                      {items.length ? items.map((item) => item.listing_title).join(', ') : 'Your produce'}
                    </Text>
                    <Text style={styles.description}>
                      {part.method === 'delivery' ? 'Delivery' : 'Pickup'}: {part.status.replace(/_/g, ' ')}
                      {' · '}{part.location_details}
                    </Text>
                    {['in_transit', 'ready_for_handover'].includes(part.status) && (
                      <Pressable accessibilityRole="button" disabled={commerceBusy}
                        onPress={() => completeDelivery(part)} style={styles.loadMore}>
                        <Text style={styles.loadMoreText}>I have received these items</Text>
                      </Pressable>
                    )}
                  </View>
                );
              })}
              <Pressable accessibilityRole="button" onPress={() => { setOrder(null); setPayment(null); setFulfilments([]); }}>
                <Text style={styles.link}>Shop for another order</Text>
              </Pressable>
            </>}
            {!!recentOrders.length && <>
              <Text style={styles.sectionTitle}>Recent orders</Text>
              {recentOrders.slice(0, 5).map((item) => (
                <Pressable key={item.id} accessibilityRole="button" onPress={() => openOrder(item)}>
                  <Text style={styles.link}>{item.id.slice(0, 8)} · {item.status} · {item.currency} {item.total_amount}</Text>
                </Pressable>
              ))}
            </>}
          </View>
          <TextInput
            accessibilityLabel="Search listings"
            placeholder="Search produce (at least 2 letters)..."
            placeholderTextColor="#71869A"
            value={search}
            onChangeText={changeSearch}
            style={styles.search}
            returnKeyType="search"
          />
          {categoryError && (
            <View style={styles.message}>
              <Text style={styles.error}>{categoryError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setCategoryRetry((value) => value + 1)}>
                <Text style={styles.link}>Retry categories</Text>
              </Pressable>
            </View>
          )}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categories}>
            {[{ id: 'all', name: 'All', slug: '' }, ...categories].map((option) => (
              <Pressable
                key={option.id}
                accessibilityRole="button"
                accessibilityState={{ selected: category === (option.slug || null) }}
                onPress={() => changeFilter(option.slug || null)}
                style={[styles.categoryChip, category === (option.slug || null) && styles.activeChip]}
              >
                <Text style={[styles.categoryText, category === (option.slug || null) && styles.activeChipText]}>{option.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <Text style={styles.sectionTitle}>Available listings</Text>
          {search.trim().length === 1 ? (
            <Text style={styles.muted}>Type one more letter to search.</Text>
          ) : loading ? (
            <ActivityIndicator accessibilityLabel="Loading listings" color="#2196F3" style={styles.loader} />
          ) : listError && !items.length ? (
            <View style={styles.message}>
              <Text style={styles.error}>{listError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setRetry((value) => value + 1)}>
                <Text style={styles.link}>Retry listings</Text>
              </Pressable>
            </View>
          ) : items.length === 0 ? (
            <Text style={styles.muted}>No active listings match your search.</Text>
          ) : (
            <View style={styles.grid}>
              {items.map((listing) => (
                <Pressable
                  key={listing.id}
                  accessibilityRole="button"
                  accessibilityLabel={`View ${listing.title} details`}
                  onPress={() => setSelectedId(listing.id)}
                  style={[styles.card, { width: width >= 680 ? '48%' : '100%' }]}
                >
                  <Photo listing={listing} style={styles.cardPhoto} baseUrl={baseUrl} />
                  <View style={styles.cardInfo}>
                    <Text style={styles.categoryLabel}>{listing.category_slug.replace(/-/g, ' ').toUpperCase()}</Text>
                    <Text style={styles.productName}>{listing.title}</Text>
                    {secondaryName(listing.title, listing.product_name) && (
                      <Text style={styles.muted}>{listing.product_name}</Text>
                    )}
                    <Price listing={listing} />
                    <Text style={styles.muted}>{formatQuantity(listing.available_quantity)} {listing.quantity_unit} available</Text>
                    {!!(harvestLabel(listing.harvest_date)) && (
                      <Text style={styles.muted}>🌾 {harvestLabel(listing.harvest_date)}</Text>
                    )}
                    <FarmerLine farmer={listing.farmer} />
                  </View>
                </Pressable>
              ))}
            </View>
          )}
          {listError && items.length > 0 && (
            <View style={styles.message}>
              <Text style={styles.error}>{listError}</Text>
              <Pressable accessibilityRole="button" onPress={() => setRetry((value) => value + 1)}>
                <Text style={styles.link}>Retry page</Text>
              </Pressable>
            </View>
          )}
          {nextPage && !loading && !loadingMore && !listError && (
            <Pressable accessibilityRole="button" onPress={() => setCursor(nextPage)} style={styles.loadMore}>
              <Text style={styles.loadMoreText}>Load more listings</Text>
            </Pressable>
          )}
          {loadingMore && <ActivityIndicator accessibilityLabel="Loading more listings" color="#2196F3" style={styles.loader} />}
        </View>
      </ScrollView>

      <Modal visible={selectedId !== null} transparent animationType="fade" onRequestClose={() => setSelectedId(null)}>
        <View style={styles.modalBackdrop}>
          <ScrollView style={styles.modalCard} contentContainerStyle={styles.modalContent}>
            <Pressable accessibilityRole="button" accessibilityLabel="Close listing details" onPress={() => setSelectedId(null)}>
              <Text style={styles.close}>Close</Text>
            </Pressable>
            {detailError ? (
              <View style={styles.message}>
                <Text style={styles.error}>{detailError}</Text>
                <Pressable accessibilityRole="button" onPress={() => setDetailRetry((value) => value + 1)}>
                  <Text style={styles.link}>Retry details</Text>
                </Pressable>
              </View>
            ) : selected ? (
              <>
                <Photo listing={selected} style={styles.detailPhoto} baseUrl={baseUrl} />
                <Text style={styles.categoryLabel}>{selected.category_slug.replace(/-/g, ' ').toUpperCase()}</Text>
                <Text style={styles.heroTitle}>{selected.title}</Text>
                {secondaryName(selected.title, selected.product_name) && (
                  <Text style={styles.muted}>{selected.product_name}</Text>
                )}
                <Text style={styles.description}>{selected.description || 'No description provided.'}</Text>
                <Price listing={selected} />
                <Text style={styles.muted}>{formatQuantity(selected.available_quantity)} {selected.quantity_unit} available</Text>
                {!!(harvestLabel(selected.harvest_date)) && (
                  <Text style={styles.muted}>🌾 {harvestLabel(selected.harvest_date)}</Text>
                )}
                <Pressable accessibilityRole="button" disabled={commerceBusy || Number(selected.available_quantity) <= 0}
                  onPress={() => addToCart(selected)} style={styles.loadMore}>
                  <Text style={styles.loadMoreText}>Add to cart</Text>
                </Pressable>
                {selected.farmer && (
                  <FarmerPanel farmer={selected.farmer} onOpen={() => {
                    setFarmerId(selected.farmer?.id ?? null);
                    setSelectedId(null);
                  }} />
                )}
              </>
            ) : (
              <ActivityIndicator accessibilityLabel="Loading listing details" color="#2196F3" style={styles.loader} />
            )}
          </ScrollView>
        </View>
      </Modal>

      <Modal visible={farmerId !== null} transparent animationType="fade" onRequestClose={() => setFarmerId(null)}>
        <View style={styles.modalBackdrop}>
          <ScrollView style={styles.modalCard} contentContainerStyle={styles.modalContent}>
            <Pressable accessibilityRole="button" accessibilityLabel="Close farmer profile" onPress={() => setFarmerId(null)}>
              <Text style={styles.close}>Close</Text>
            </Pressable>
            {farmerError ? (
              <Text style={styles.error}>{farmerError}</Text>
            ) : farmer ? (
              <>
                <Text style={styles.heroTitle}>
                  {farmer.display_name}{farmer.verification_status === 'verified' ? '  ✓' : ''}
                </Text>
                {!!farmer.farm_name && <Text style={styles.productName}>{farmer.farm_name}</Text>}
                {!!(farmerPlace(farmer)) && <Text style={styles.muted}>📍 {farmerPlace(farmer)}</Text>}
                {!!farmer.bio && <Text style={styles.description}>{farmer.bio}</Text>}
                <View style={styles.farmerFacts}>
                  <Text style={styles.muted}>✅ {farmer.completed_orders} completed orders</Text>
                  <Text style={styles.muted}>🧺 {farmer.active_listings} listings on sale</Text>
                  <Text style={styles.muted}>🚚 {handoverOptions(farmer)}
                    {farmer.offers_delivery && farmer.delivery_radius_km ? ` (within ${farmer.delivery_radius_km} km)` : ''}</Text>
                  {!!farmer.farm_size_acres && <Text style={styles.muted}>📐 {Number(farmer.farm_size_acres)} acres</Text>}
                  {!!farmer.farming_since_year && <Text style={styles.muted}>🌱 Farming since {farmer.farming_since_year}</Text>}
                  {!!farmer.farming_practices && (
                    <Text style={styles.muted}>🌿 {farmer.farming_practices} (as described by the farmer)</Text>
                  )}
                  {!!farmer.categories.length && <Text style={styles.muted}>Grows: {farmer.categories.join(', ')}</Text>}
                  {farmer.cancelled_handovers > 0 && (
                    <Text style={styles.muted}>{farmer.cancelled_handovers} cancelled hand-over(s)</Text>
                  )}
                  {!!(memberSince(farmer.member_since)) && <Text style={styles.muted}>{memberSince(farmer.member_since)}</Text>}
                </View>
                <Text style={styles.sectionTitle}>On sale from this farmer</Text>
                {farmerListings.length ? farmerListings.map((listing) => (
                  <Pressable key={listing.id} accessibilityRole="button" style={styles.cartRow}
                    onPress={() => { setFarmerId(null); setSelectedId(listing.id); }}>
                    <Text style={styles.productName}>{listing.title}</Text>
                    <Price listing={listing} />
                  </Pressable>
                )) : <Text style={styles.muted}>Nothing on sale right now.</Text>}
              </>
            ) : (
              <ActivityIndicator accessibilityLabel="Loading farmer profile" color="#2196F3" style={styles.loader} />
            )}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: '#F5F9FC' },
  scrollContent: { flexGrow: 1, paddingHorizontal: 20, paddingBottom: 64 },
  content: { width: '100%', maxWidth: 1040, alignSelf: 'center' },
  topRow: { flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center', paddingVertical: 24 },
  liveBadge: { color: '#1164A7', backgroundColor: '#E1F1FE', borderRadius: 15, overflow: 'hidden', padding: 8, fontSize: 11, fontWeight: '800' },
  hero: { backgroundColor: '#DCEFFE', borderRadius: 24, padding: 30, marginBottom: 14 },
  heroTitle: { color: '#153C59', fontSize: 28, fontWeight: '800', marginBottom: 10 },
  heroSubtitle: { color: '#3B6077', fontSize: 16 },
  disclaimer: { color: '#456276', fontSize: 14, marginBottom: 18, marginTop: 6 },
  search: { backgroundColor: '#fff', borderRadius: 14, borderWidth: 1, borderColor: '#DCE6EE', paddingHorizontal: 18, paddingVertical: 14, fontSize: 16, color: '#17364D', marginBottom: 18 },
  categories: { gap: 10, paddingBottom: 26 },
  categoryChip: { backgroundColor: '#fff', borderColor: '#DCE6EE', borderWidth: 1, borderRadius: 20, paddingHorizontal: 18, paddingVertical: 10 },
  activeChip: { backgroundColor: '#2196F3', borderColor: '#2196F3' },
  categoryText: { color: '#456276', fontWeight: '600' },
  activeChipText: { color: '#fff' },
  sectionTitle: { color: '#17364D', fontSize: 22, fontWeight: '800', marginBottom: 16 },
  muted: { color: '#668096', fontSize: 14 },
  loader: { paddingVertical: 40 },
  message: { gap: 12, paddingVertical: 25 },
  error: { color: '#A4262C', fontSize: 15 },
  link: { color: '#1164A7', fontWeight: '700', paddingVertical: 8 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 16 },
  card: { backgroundColor: '#fff', borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: '#E5EDF3' },
  cardPhoto: { width: '100%', height: 170 },
  cardInfo: { padding: 18, gap: 6 },
  categoryLabel: { color: '#27865B', letterSpacing: 1, fontSize: 11, fontWeight: '800' },
  productName: { fontSize: 18, fontWeight: '700', color: '#17364D' },
  price: { fontSize: 16, fontWeight: '800', color: '#153C59', marginTop: 8 },
  photoUnavailable: { backgroundColor: '#E8EFF4', alignItems: 'center', justifyContent: 'center' },
  photoUnavailableText: { color: '#456276', fontWeight: '600' },
  loadMore: { backgroundColor: '#E1F1FE', borderRadius: 12, padding: 14, alignItems: 'center', marginTop: 22 },
  loadMoreText: { color: '#1164A7', fontWeight: '800' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(13, 35, 52, 0.6)', justifyContent: 'center', alignItems: 'center', padding: 20 },
  modalCard: { width: '100%', maxWidth: 440, maxHeight: '90%', backgroundColor: '#fff', borderRadius: 22 },
  modalContent: { padding: 24 },
  farmerLine: { color: '#27865B', fontSize: 13, fontWeight: '700', marginTop: 4 },
  farmerPanel: { backgroundColor: '#F1F8F4', borderRadius: 14, padding: 16, marginTop: 20, gap: 4 },
  farmerPanelTitle: { color: '#27865B', fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' },
  farmerFacts: { gap: 6, marginVertical: 12 },
  illustrationNote: { color: '#668096', fontSize: 11, paddingHorizontal: 8, paddingTop: 4 },
  close: { color: '#1164A7', fontWeight: '700', alignSelf: 'flex-end', padding: 8, marginBottom: 10 },
  detailPhoto: { width: '100%', height: 180 },
  description: { color: '#456276', fontSize: 15, lineHeight: 23, marginVertical: 18 },
  cartRow: { backgroundColor: '#fff', borderRadius: 12, padding: 14, gap: 4 },
});
