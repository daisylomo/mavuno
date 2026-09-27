import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_FARMER_LABEL,
  farmerListingToProduct,
  farmerListingsToProducts,
} from '../src/components/farmer-listings-bridge.ts';

function listing(overrides = {}) {
  return {
    id: 'prod_1',
    title: 'Fresh Kale',
    category: 'Vegetables',
    price: 150,
    quantity: 9,
    unit: 'bunch',
    harvestDate: '2026-09-20',
    description: 'Picked this morning.',
    status: 'active',
    createdAt: '2026-09-20T06:00:00.000Z',
    ...overrides,
  };
}

test('uses the price the farmer entered, not a sample price', () => {
  const product = farmerListingToProduct(listing({ price: 275 }));
  assert.equal(product.price, 275);
  assert.equal(product.stock, 9);
  assert.equal(product.unit, 'bunch');
  assert.equal(product.name, 'Fresh Kale');
});

test('maps farmer-only categories onto the customer filters', () => {
  assert.equal(farmerListingToProduct(listing({ category: 'Grains & Cereals' })).category, 'Pantry');
  assert.equal(farmerListingToProduct(listing({ category: 'Tubers & Roots' })).category, 'Vegetables');
  assert.equal(farmerListingToProduct(listing({ category: 'Dairy & Poultry' })).category, 'Pantry');
  assert.equal(farmerListingToProduct(listing({ category: 'Fruits' })).category, 'Fruits');
});

test('carries an image url through, and tolerates listings without one', () => {
  assert.deepEqual(
    farmerListingToProduct(listing({ imageUrl: 'https://example.test/kale.jpg' })).image,
    { uri: 'https://example.test/kale.jpg' },
  );
  assert.equal(farmerListingToProduct(listing()).image, null);
});

test('labels the seller, with an override available', () => {
  assert.equal(farmerListingToProduct(listing()).farmer, DEFAULT_FARMER_LABEL);
  assert.equal(farmerListingToProduct(listing(), 'Maua Farm').farmer, 'Maua Farm');
});

test('shows active and low stock listings only', () => {
  const products = farmerListingsToProducts([
    listing({ id: 'a', status: 'active' }),
    listing({ id: 'b', status: 'low_stock' }),
    listing({ id: 'c', status: 'sold_out' }),
    listing({ id: 'd', status: 'paused' }),
  ]);
  assert.deepEqual(
    products.map((product) => product.id),
    ['a', 'b'],
  );
});

test('drops listings that cannot be bought', () => {
  const products = farmerListingsToProducts([
    listing({ id: 'zero-stock', quantity: 0 }),
    listing({ id: 'zero-price', price: 0 }),
    listing({ id: 'negative-price', price: -10 }),
    listing({ id: 'not-a-number', price: Number.NaN }),
    listing({ id: 'good' }),
  ]);
  assert.deepEqual(
    products.map((product) => product.id),
    ['good'],
  );
});

test('returns an empty list when the farmer has listed nothing', () => {
  assert.deepEqual(farmerListingsToProducts([]), []);
});
