// Pure helpers for listing photos, harvest dates and farmer details. Kept free of
// React Native imports so they can be tested with plain Node.

/** Illustrations bundled with the app, selectable when a farmer has no photo. */
export const PRESET_PHOTO_KEYS = [
  'tomatoes', 'spinach', 'mangoes', 'bananas', 'carrots', 'avocados', 'potatoes', 'honey',
] as const;
export type PresetPhotoKey = (typeof PRESET_PHOTO_KEYS)[number];

export type ListingImageRef = { object_key: string; url?: string | null };

export type PhotoSource =
  | { kind: 'uploaded'; uri: string }
  | { kind: 'preset'; key: PresetPhotoKey }
  | { kind: 'none' };

function isPreset(value: string): value is PresetPhotoKey {
  return (PRESET_PHOTO_KEYS as readonly string[]).includes(value);
}

/**
 * The preset illustration a stored image key names, if any. `preset/tomatoes` is the current
 * form; `listings/tomatoes.jpg` is what the first photo-upload build registered.
 */
export function presetFromKey(objectKey: string | undefined | null): PresetPhotoKey | null {
  if (!objectKey) return null;
  const match = /^(?:preset\/([a-z]+)|listings\/([a-z]+)\.jpg)$/.exec(objectKey);
  const key = match?.[1] ?? match?.[2];
  return key && isPreset(key) ? key : null;
}

/** The API origin, from a base URL that ends in /api/v1. */
export function apiOrigin(apiBase: string): string {
  return apiBase.replace(/\/+$/, '').replace(/\/api\/v1$/, '');
}

/** Where to load a listing's first photo from: an upload the API serves, or an illustration. */
export function photoSource(
  images: readonly ListingImageRef[] | undefined,
  apiBase: string | null,
): PhotoSource {
  const first = images?.[0];
  if (!first) return { kind: 'none' };
  const preset = presetFromKey(first.object_key);
  if (preset) return { kind: 'preset', key: preset };
  if (first.url && apiBase) {
    if (/^https?:\/\//.test(first.url)) return { kind: 'uploaded', uri: first.url };
    if (first.url.startsWith('/')) return { kind: 'uploaded', uri: `${apiOrigin(apiBase)}${first.url}` };
  }
  return { kind: 'none' };
}

/** Splits a `data:image/jpeg;base64,...` URL into what the photo upload endpoint takes. */
export function splitDataUrl(
  dataUrl: string,
): { contentType: 'image/jpeg' | 'image/png' | 'image/webp'; base64: string } | null {
  const match = /^data:(image\/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl);
  if (!match) return null;
  return { contentType: match[1] as 'image/jpeg' | 'image/png' | 'image/webp', base64: match[2] };
}

/** Approximate decoded size of base64 data, in bytes. */
export function base64Bytes(base64: string): number {
  const padding = base64.endsWith('==') ? 2 : base64.endsWith('=') ? 1 : 0;
  return Math.floor((base64.length * 3) / 4) - padding;
}

export const HARVEST_OPTIONS = ['Harvested Today', 'Harvested Yesterday', 'Harvesting Tomorrow'] as const;
export type HarvestOption = (typeof HARVEST_OPTIONS)[number];

const DAY_MS = 24 * 60 * 60 * 1000;
// Kenya does not observe daylight saving, so East Africa Time is always UTC+3.
const EAT_OFFSET_MS = 3 * 60 * 60 * 1000;

function eatDay(now: Date, offsetDays = 0): string {
  return new Date(now.valueOf() + EAT_OFFSET_MS + offsetDays * DAY_MS).toISOString().slice(0, 10);
}

/** The calendar date (in Kenya) a harvest option refers to, as sent to the API. */
export function harvestIsoDate(option: string, now: Date = new Date()): string | null {
  if (option === 'Harvested Today') return eatDay(now);
  if (option === 'Harvested Yesterday') return eatDay(now, -1);
  if (option === 'Harvesting Tomorrow') return eatDay(now, 1);
  return null;
}

/** A buyer-facing description of a harvest date. */
export function harvestLabel(isoDate: string | null | undefined, now: Date = new Date()): string | null {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return null;
  const today = Date.parse(`${eatDay(now)}T00:00:00Z`);
  const day = Date.parse(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(day)) return null;
  const difference = Math.round((today - day) / DAY_MS);
  if (difference === 0) return 'Harvested today';
  if (difference === 1) return 'Harvested yesterday';
  if (difference === -1) return 'Harvest due tomorrow';
  if (difference > 1 && difference <= 14) return `Harvested ${difference} days ago`;
  const formatted = new Date(day).toLocaleDateString('en-KE', {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  });
  return difference < 0 ? `Harvest due ${formatted}` : `Harvested ${formatted}`;
}

export type FarmerSummary = {
  id: string;
  display_name: string;
  farm_name: string | null;
  county: string | null;
  locality: string | null;
  verification_status: string;
  member_since: string;
  active_listings: number;
  completed_orders: number;
  offers_pickup: boolean;
  offers_delivery: boolean;
  farming_practices: string | null;
};

export function isFarmerSummary(value: unknown): value is FarmerSummary {
  if (typeof value !== 'object' || value === null) return false;
  const item = value as Record<string, unknown>;
  const optionalText = (key: string) => item[key] === null || typeof item[key] === 'string';
  return typeof item.id === 'string' && typeof item.display_name === 'string' &&
    optionalText('farm_name') && optionalText('county') && optionalText('locality') &&
    typeof item.verification_status === 'string' && typeof item.member_since === 'string' &&
    typeof item.active_listings === 'number' && typeof item.completed_orders === 'number' &&
    typeof item.offers_pickup === 'boolean' && typeof item.offers_delivery === 'boolean' &&
    optionalText('farming_practices');
}

/** "Limuru, Kiambu", or whichever part is known. */
export function farmerPlace(farmer: Pick<FarmerSummary, 'locality' | 'county'>): string | null {
  const parts = [farmer.locality, farmer.county].filter((part): part is string => !!part?.trim());
  return parts.length ? parts.join(', ') : null;
}

/** "Member since Sep 2026". */
export function memberSince(isoDateTime: string): string | null {
  const value = new Date(isoDateTime.endsWith('Z') ? isoDateTime : `${isoDateTime}Z`);
  if (Number.isNaN(value.valueOf())) return null;
  return `Member since ${value.toLocaleDateString('en-KE', { month: 'short', year: 'numeric', timeZone: 'UTC' })}`;
}

export function handoverOptions(farmer: Pick<FarmerSummary, 'offers_pickup' | 'offers_delivery'>): string {
  if (farmer.offers_pickup && farmer.offers_delivery) return 'Pickup or delivery';
  if (farmer.offers_delivery) return 'Delivery only';
  return 'Pickup from the farm';
}

/**
 * Minutes and a clock time for a reservation deadline, e.g. "11:42 (in 9 min)".
 * API datetimes are UTC without a zone suffix.
 */
export function reservationDeadline(isoDateTime: string, now: Date = new Date()): string | null {
  const value = new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(isoDateTime) ? isoDateTime : `${isoDateTime}Z`);
  if (Number.isNaN(value.valueOf())) return null;
  const clock = new Date(value.valueOf() + EAT_OFFSET_MS).toISOString().slice(11, 16);
  const minutes = Math.ceil((value.valueOf() - now.valueOf()) / 60000);
  if (minutes <= 0) return `${clock} EAT (expired)`;
  return `${clock} EAT (in ${minutes} min)`;
}
