import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  apiBaseUrl,
  getCategories,
  getListing,
  getListings,
  LISTING_UNITS,
  listingImageUrl,
} from '../src/components/customer-catalog-api.ts';

const listing = {
  id: '11111111-1111-4111-8111-111111111111',
  farmer_id: '22222222-2222-4222-8222-222222222222',
  product_id: '33333333-3333-4333-8333-333333333333',
  title: 'Fresh carrots',
  product_name: 'Carrots',
  category_slug: 'root-vegetables',
  description: null,
  price_amount: '115.5000',
  currency: 'KES',
  available_quantity: '12.000',
  quantity_unit: 'kg',
  status: 'active',
  version: 1,
  images: [{ id: '44444444-4444-4444-8444-444444444444', object_key: 'farms/carrots 1.jpg', alt_text: 'Fresh carrots', sort_order: 0 }],
};

test('preview and API share exactly the supported listing units', () => {
  assert.deepEqual(LISTING_UNITS, ['kg', 'g', 'crate', 'piece', 'bunch', 'bag']);
  assert.ok(LISTING_UNITS.includes('piece'));
  assert.ok(!LISTING_UNITS.includes('pair'));
  assert.ok(!LISTING_UNITS.includes('jar'));
});

test('URL configuration distinguishes live from demo and rejects invalid URLs', () => {
  const previous = process.env.EXPO_PUBLIC_MAVUNO_API_URL;
  try {
    delete process.env.EXPO_PUBLIC_MAVUNO_API_URL;
    assert.equal(apiBaseUrl(), null);
    process.env.EXPO_PUBLIC_MAVUNO_API_URL = 'http://localhost:8000/api/v1/';
    assert.equal(apiBaseUrl(), 'http://localhost:8000/api/v1');
    process.env.EXPO_PUBLIC_MAVUNO_API_URL = 'file:///api/v1';
    assert.throws(() => apiBaseUrl(), /HTTP\(S\)/);
  } finally {
    if (previous === undefined) delete process.env.EXPO_PUBLIC_MAVUNO_API_URL;
    else process.env.EXPO_PUBLIC_MAVUNO_API_URL = previous;
  }
});

test('image keys require configured public hosting and are URL-encoded', () => {
  const previous = process.env.EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL;
  try {
    delete process.env.EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL;
    assert.equal(listingImageUrl('farms/carrots 1.jpg'), null);
    process.env.EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL = 'https://images.example.test/products';
    assert.equal(
      listingImageUrl('farms/carrots 1.jpg'),
      'https://images.example.test/products/farms/carrots%201.jpg',
    );
    assert.throws(() => listingImageUrl('../secret'), /invalid image key/);
  } finally {
    if (previous === undefined) delete process.env.EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL;
    else process.env.EXPO_PUBLIC_MAVUNO_IMAGE_BASE_URL = previous;
  }
});

test('listings encode filters and cursor, preserve the page shape and fetch detail', async () => {
  const previous = globalThis.fetch;
  const requested = [];
  globalThis.fetch = async (url) => {
    requested.push(String(url));
    return Response.json(requested.length === 1
      ? { items: [listing], next_cursor: 'next/cursor' }
      : listing);
  };
  try {
    const signal = new AbortController().signal;
    const page = await getListings('https://api.example.test/api/v1', {
      search: 'red onions', category: 'root-vegetables', cursor: 'next/cursor',
    }, signal);
    assert.equal(page.items[0].price_amount, '115.5000');
    assert.equal(page.next_cursor, 'next/cursor');
    assert.match(requested[0], /search=red%20onions&category=root-vegetables&cursor=next%2Fcursor/);
    const detail = await getListing('https://api.example.test/api/v1', listing.id, signal);
    assert.equal(detail.id, listing.id);
    assert.match(requested[1], /\/listings\/11111111-1111-4111-8111-111111111111$/);
  } finally {
    globalThis.fetch = previous;
  }
});

test('invalid catalog payload and HTTP failures are surfaced rather than replaced by demo data', async () => {
  const previous = globalThis.fetch;
  try {
    globalThis.fetch = async () => Response.json({ items: [], next_cursor: 17 });
    await assert.rejects(
      getListings('https://api.example.test/api/v1', { search: '', category: null }, new AbortController().signal),
      /listings response is invalid/,
    );
    globalThis.fetch = async () => new Response('Service unavailable', { status: 503 });
    await assert.rejects(
      getCategories('https://api.example.test/api/v1', new AbortController().signal),
      /HTTP 503/,
    );
  } finally {
    globalThis.fetch = previous;
  }
});

test('rejects unsupported units, invalid price or stock, and unsafe image keys', async () => {
  const previous = globalThis.fetch;
  try {
    for (const invalid of [
      { quantity_unit: 'jar' },
      { price_amount: 'not-a-price' },
      { available_quantity: '-1' },
      { images: [{ object_key: '../private.jpg', alt_text: null }] },
    ]) {
      globalThis.fetch = async () => Response.json({ items: [{ ...listing, ...invalid }], next_cursor: null });
      await assert.rejects(
        getListings('https://api.example.test/api/v1', { search: '', category: null }, new AbortController().signal),
        /listings response is invalid/,
      );
    }
    globalThis.fetch = async () => Response.json({
      items: [{ ...listing, price_amount: 42.5, available_quantity: 0 }],
      next_cursor: null,
    });
    const page = await getListings(
      'https://api.example.test/api/v1', { search: '', category: null }, new AbortController().signal,
    );
    assert.equal(page.items[0].price_amount, '42.5');
    assert.equal(page.items[0].available_quantity, '0');
  } finally {
    globalThis.fetch = previous;
  }
});
