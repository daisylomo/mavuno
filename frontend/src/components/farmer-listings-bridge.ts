import type { ListingUnit } from '@/components/customer-catalog-api';
import type { ListingStatus, ProduceCategory, ProduceListing } from '@/types/farmer';

export type DemoCategory = 'Vegetables' | 'Fruits' | 'Pantry';

export type DemoProduct = {
  id: string;
  name: string;
  category: DemoCategory;
  price: number;
  unit: ListingUnit;
  farmer: string;
  description: string;
  stock: number;
  imageUri: string | null;
  // Which bundled picture illustrates this listing when the farmer has no
  // photograph of their own. The screen turns this into an actual image.
  imageKey: ImageKey;
  // True when the picture is a stock illustration rather than the farmer's own
  // photograph, so the marketplace can say so.
  illustrated: boolean;
};

// The farmer form offers more categories than the customer filters, so several
// of them collapse into "Pantry".
const CATEGORY_MAP: Record<ProduceCategory, DemoCategory> = {
  Vegetables: 'Vegetables',
  Fruits: 'Fruits',
  'Grains & Cereals': 'Pantry',
  'Tubers & Roots': 'Vegetables',
  'Dairy & Poultry': 'Pantry',
};

const SELLABLE_STATUSES: readonly ListingStatus[] = ['active', 'low_stock'];

export const DEFAULT_FARMER_LABEL = 'Local farmer';

// Farmers cannot attach their own photograph yet, so a listing is illustrated
// with the closest bundled CC0 picture, matched on what the farmer typed.
// These are stock illustrations, not the farmer's actual harvest, and the
// marketplace labels them as such.
type ImageKey =
  | 'tomatoes'
  | 'spinach'
  | 'mangoes'
  | 'bananas'
  | 'carrots'
  | 'avocados'
  | 'potatoes'
  | 'honey';

// Checked in order, so more specific words must come first: "sweet potato"
// should match the potato picture, not be caught by a broader rule.
const KEYWORD_IMAGES: ReadonlyArray<readonly [readonly string[], ImageKey]> = [
  [['tomato', 'nyanya'], 'tomatoes'],
  [['spinach', 'sukuma', 'kale', 'managu', 'terere', 'saga', 'kunde', 'cabbage', 'lettuce', 'green'], 'spinach'],
  [['mango', 'embe', 'pawpaw', 'papaya', 'pineapple', 'orange', 'passion', 'guava', 'melon'], 'mangoes'],
  [['banana', 'ndizi', 'plantain', 'matoke'], 'bananas'],
  [['carrot', 'karoti', 'pepper', 'pilipili', 'onion', 'kitunguu'], 'carrots'],
  [['avocado', 'parachichi'], 'avocados'],
  [['potato', 'viazi', 'cassava', 'muhogo', 'arrowroot', 'nduma', 'yam', 'beetroot', 'radish', 'turnip'], 'potatoes'],
  [['honey', 'asali', 'milk', 'maziwa', 'egg', 'yai', 'maize', 'mahindi', 'bean', 'maharagwe', 'rice', 'mchele', 'flour', 'unga', 'millet', 'sorghum', 'wheat', 'nut', 'groundnut'], 'honey'],
];

const CATEGORY_FALLBACK_IMAGES: Record<DemoCategory, ImageKey> = {
  Vegetables: 'spinach',
  Fruits: 'mangoes',
  Pantry: 'honey',
};

/** Which bundled picture best illustrates what the farmer typed. */
export function pickImageKey(title: string, category: DemoCategory): ImageKey {
  const haystack = title.toLowerCase();
  for (const [keywords, key] of KEYWORD_IMAGES) {
    if (keywords.some((word) => haystack.includes(word))) {
      return key;
    }
  }
  return CATEGORY_FALLBACK_IMAGES[category];
}

// Kept in the screen rather than here so these bundler-resolved requires do not
// run when the matching rules are unit tested.
export type { ImageKey as ProduceImageKey };

export function farmerListingToProduct(
  listing: ProduceListing,
  farmerLabel: string = DEFAULT_FARMER_LABEL,
): DemoProduct {
  const category = CATEGORY_MAP[listing.category] ?? 'Pantry';
  const isPreset = !!listing.imageUrl && listing.imageUrl.startsWith('preset:');
  const presetKey = isPreset ? (listing.imageUrl!.replace('preset:', '') as ImageKey) : null;

  return {
    id: listing.id,
    name: listing.title,
    category,
    price: listing.price,
    unit: listing.unit,
    farmer: farmerLabel,
    description: listing.description,
    stock: listing.quantity,
    imageUri: isPreset ? null : listing.imageUrl ?? null,
    imageKey: presetKey || pickImageKey(listing.title, category),
    illustrated: !listing.imageUrl || isPreset,
  };
}

export function farmerListingsToProducts(
  listings: readonly ProduceListing[],
  farmerLabel: string = DEFAULT_FARMER_LABEL,
): DemoProduct[] {
  return listings
    .filter(
      (listing) =>
        SELLABLE_STATUSES.includes(listing.status) &&
        Number.isFinite(listing.price) &&
        listing.price > 0 &&
        Number.isFinite(listing.quantity) &&
        listing.quantity > 0,
    )
    .map((listing) => farmerListingToProduct(listing, farmerLabel));
}
