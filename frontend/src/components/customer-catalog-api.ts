import { isFarmerSummary, type FarmerSummary } from './listing-details.ts';

export type Category = { id: string; name: string; slug: string };

/**
 * The hosted API runs on a free plan that sleeps when idle; the first request after a pause can
 * take 30-60 seconds while it starts. Requests wait this long before giving up.
 */
export const SERVER_TIMEOUT_MS = 60_000;
export const SERVER_WAKING_MESSAGE =
  'The Mavuno server may be temporarily unavailable or starting up after being idle. Wait a minute, then try again.';
export type { FarmerSummary };

export const LISTING_UNITS = ['kg', 'g', 'crate', 'piece', 'bunch', 'bag'] as const;
export type ListingUnit = (typeof LISTING_UNITS)[number];

export type Listing = {
  id: string;
  title: string;
  product_name: string;
  category_slug: string;
  description: string | null;
  price_amount: string;
  currency: string;
  available_quantity: string;
  quantity_unit: ListingUnit;
  images: Array<{ object_key: string; alt_text: string | null; url?: string | null }>;
  farmer_id?: string;
  harvest_date?: string | null;
  farmer?: FarmerSummary | null;
};

export type FarmerProfile = FarmerSummary & {
  bio: string | null;
  farm_size_acres: string | null;
  farming_since_year: number | null;
  delivery_radius_km: number | null;
  categories: string[];
  cancelled_handovers: number;
};

export type ListingPage = { items: Listing[]; next_cursor: string | null };
type ListingPayload = Omit<Listing, 'price_amount' | 'available_quantity'> & {
  price_amount: string | number;
  available_quantity: string | number;
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isCategory(value: unknown): value is Category {
  return record(value) && typeof value.id === 'string' &&
    typeof value.name === 'string' && typeof value.slug === 'string';
}

function isAmount(value: unknown, allowZero: boolean): boolean {
  return (typeof value === 'number' ||
      (typeof value === 'string' && /^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value))) &&
    Number.isFinite(Number(value)) &&
    (allowZero ? Number(value) >= 0 : Number(value) > 0);
}

function isImageKey(value: string): boolean {
  return value.length > 0 && !value.startsWith('/') && !value.includes('://') &&
    value.split('/').every((segment) =>
      segment.length > 0 && segment !== '.' && segment !== '..' && !segment.includes('\\'));
}

function isListing(value: unknown): value is ListingPayload {
  return record(value) && typeof value.id === 'string' &&
    typeof value.title === 'string' && typeof value.product_name === 'string' &&
    typeof value.category_slug === 'string' &&
    (value.description === null || typeof value.description === 'string') &&
    isAmount(value.price_amount, false) &&
    typeof value.currency === 'string' &&
    isAmount(value.available_quantity, true) &&
    LISTING_UNITS.some((unit) => unit === value.quantity_unit) && Array.isArray(value.images) &&
    value.images.every((image: unknown) => record(image) &&
      typeof image.object_key === 'string' && isImageKey(image.object_key) &&
      (image.alt_text === null || typeof image.alt_text === 'string') &&
      (image.url === undefined || image.url === null || typeof image.url === 'string')) &&
    (value.harvest_date === undefined || value.harvest_date === null ||
      typeof value.harvest_date === 'string') &&
    (value.farmer === undefined || value.farmer === null || isFarmerSummary(value.farmer));
}

function normalizeListing(value: ListingPayload): Listing {
  return {
    ...value,
    price_amount: String(value.price_amount),
    available_quantity: String(value.available_quantity),
  };
}

async function getJson(url: string, signal: AbortSignal): Promise<unknown> {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  signal.addEventListener('abort', abort, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, SERVER_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) {
      throw new Error(`Catalog request failed (HTTP ${response.status}). Check the API and try again.`);
    }
    return await response.json();
  } catch (error) {
    if (timedOut) throw new Error(SERVER_WAKING_MESSAGE);
    if (error instanceof TypeError && !signal.aborted) {
      throw new Error('Cannot reach the catalog API. Check its address, CORS settings and your connection.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}

export function apiBaseUrl(): string | null {
  const configured = process.env.EXPO_PUBLIC_MAVUNO_API_URL?.trim();
  if (!configured) return null;
  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    throw new Error('EXPO_PUBLIC_MAVUNO_API_URL must be an HTTP(S) URL ending in /api/v1.');
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash ||
      url.username || url.password || !url.hostname ||
      !url.pathname.replace(/\/+$/, '').endsWith('/api/v1')) {
    throw new Error('EXPO_PUBLIC_MAVUNO_API_URL must be an HTTP(S) URL ending in /api/v1.');
  }
  return url.toString().replace(/\/+$/, '');
}

export function imageBaseUrl(): string | null {
  const base = process.env.EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL?.trim();
  if (!base) return null;
  let url: URL;
  try {
    url = new URL(base);
  } catch {
    throw new Error('EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL must be an HTTP(S) URL without a query or fragment.');
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.search || url.hash ||
      url.username || url.password || !url.hostname) {
    throw new Error('EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL must be an HTTP(S) URL without a query or fragment.');
  }
  return base.replace(/\/+$/, '');
}

export function listingImageUrl(objectKey: string | undefined): string | null {
  const base = imageBaseUrl();
  if (!base || !objectKey) return null;
  if (!isImageKey(objectKey)) {
    throw new Error('The listing contains an invalid image key.');
  }
  return `${base}/${objectKey.split('/').map(encodeURIComponent).join('/')}`;
}

export async function getCategories(base: string, signal: AbortSignal): Promise<Category[]> {
  const data = await getJson(`${base}/catalog/categories`, signal);
  if (!Array.isArray(data) || !data.every(isCategory)) {
    throw new Error('The catalog categories response is invalid.');
  }
  return data;
}

export async function getListings(
  base: string,
  filters: { search: string; category: string | null; cursor?: string; farmerId?: string },
  signal: AbortSignal,
): Promise<ListingPage> {
  const params = ['limit=20'];
  if (filters.search) params.push(`search=${encodeURIComponent(filters.search)}`);
  if (filters.category) params.push(`category=${encodeURIComponent(filters.category)}`);
  if (filters.cursor) params.push(`cursor=${encodeURIComponent(filters.cursor)}`);
  if (filters.farmerId) params.push(`farmer_id=${encodeURIComponent(filters.farmerId)}`);
  const data = await getJson(`${base}/listings?${params.join('&')}`, signal);
  if (!record(data) || !Array.isArray(data.items) || !data.items.every(isListing) ||
      !(data.next_cursor === null || typeof data.next_cursor === 'string')) {
    throw new Error('The listings response is invalid.');
  }
  return { items: data.items.map(normalizeListing), next_cursor: data.next_cursor };
}

export async function getListing(base: string, id: string, signal: AbortSignal): Promise<Listing> {
  const data = await getJson(`${base}/listings/${encodeURIComponent(id)}`, signal);
  if (!isListing(data)) throw new Error('The listing response is invalid.');
  return normalizeListing(data);
}

export async function getFarmer(base: string, id: string, signal: AbortSignal): Promise<FarmerProfile> {
  const data = await getJson(`${base}/farmers/${encodeURIComponent(id)}`, signal);
  if (!isFarmerSummary(data) || !Array.isArray((data as { categories?: unknown }).categories)) {
    throw new Error('The farmer profile response is invalid.');
  }
  return data as FarmerProfile;
}

/** Starts waking a sleeping server without waiting for it, e.g. when the sign-in screen opens. */
export function wakeServer(base: string | null = apiBaseUrl()): void {
  if (!base) return;
  const origin = base.replace(/\/+$/, '').replace(/\/api\/v1$/, '');
  fetch(`${origin}/health/live`).catch(() => undefined);
}
