import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DEFAULT_FARMER_LABEL,
  farmerListingToProduct,
  farmerListingsToProducts,
  pickImageKey,
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

test('carries a farmer photograph through, and tolerates listings without one', () => {
  const own = farmerListingToProduct(listing({ imageUrl: 'https://example.test/kale.jpg' }));
  assert.equal(own.imageUri, 'https://example.test/kale.jpg');
  assert.equal(own.illustrated, false, 'a real photograph is not an illustration');

  const withoutPhoto = farmerListingToProduct(listing());
  assert.equal(withoutPhoto.imageUri, null);
  assert.equal(withoutPhoto.illustrated, true);
  assert.ok(withoutPhoto.imageKey, 'still gets an illustration to show');
});

test('matches an illustration to what the farmer typed', () => {
  assert.equal(pickImageKey('Sukuma Wiki', 'Vegetables'), 'spinach');
  assert.equal(pickImageKey('Hass Avocados', 'Fruits'), 'avocados');
  assert.equal(pickImageKey('Nyanya', 'Vegetables'), 'tomatoes');
  assert.equal(pickImageKey('Ndizi', 'Fruits'), 'bananas');
  assert.equal(pickImageKey('Viazi', 'Vegetables'), 'potatoes');
  assert.equal(pickImageKey('Mahindi', 'Pantry'), 'honey');
});

test('matching ignores capitals and surrounding words', () => {
  assert.equal(pickImageKey('ORGANIC HASS AVOCADOS, GRADE 1', 'Fruits'), 'avocados');
  assert.equal(pickImageKey('  Fresh Sukuma Wiki bundles  ', 'Vegetables'), 'spinach');
});

test('falls back to a category picture when nothing matches', () => {
  assert.equal(pickImageKey('Xyz Produce', 'Vegetables'), 'spinach');
  assert.equal(pickImageKey('Xyz Produce', 'Fruits'), 'mangoes');
  assert.equal(pickImageKey('Xyz Produce', 'Pantry'), 'honey');
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
