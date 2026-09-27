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
  image: number | { uri: string } | null;
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

export function farmerListingToProduct(
  listing: ProduceListing,
  farmerLabel: string = DEFAULT_FARMER_LABEL,
): DemoProduct {
  return {
    id: listing.id,
    name: listing.title,
    category: CATEGORY_MAP[listing.category] ?? 'Pantry',
    price: listing.price,
    unit: listing.unit,
    farmer: farmerLabel,
    description: listing.description,
    stock: listing.quantity,
    image: listing.imageUrl ? { uri: listing.imageUrl } : null,
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
