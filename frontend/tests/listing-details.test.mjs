import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  apiOrigin,
  base64Bytes,
  farmerPlace,
  handoverOptions,
  harvestIsoDate,
  harvestLabel,
  isFarmerSummary,
  memberSince,
  photoSource,
  presetFromKey,
  reservationDeadline,
  splitDataUrl,
} from '../src/components/listing-details.ts';

const API = 'https://mavuno-api.onrender.com/api/v1';

test('uploaded photos resolve against the API origin', () => {
  assert.equal(apiOrigin(API), 'https://mavuno-api.onrender.com');
  assert.deepEqual(
    photoSource([{ object_key: 'uploads/abc', url: '/api/v1/listing-images/abc' }], API),
    { kind: 'uploaded', uri: 'https://mavuno-api.onrender.com/api/v1/listing-images/abc' },
  );
  assert.deepEqual(
    photoSource([{ object_key: 'uploads/abc', url: 'https://cdn.example/x.jpg' }], API),
    { kind: 'uploaded', uri: 'https://cdn.example/x.jpg' },
  );
  assert.deepEqual(photoSource([{ object_key: 'uploads/abc', url: '/x' }], null), { kind: 'none' });
});

test('preset keys, including the first build’s form, map to bundled illustrations', () => {
  assert.equal(presetFromKey('preset/tomatoes'), 'tomatoes');
  assert.equal(presetFromKey('listings/honey.jpg'), 'honey');
  assert.equal(presetFromKey('listings/abc/photo_1.jpg'), null);
  assert.equal(presetFromKey('preset/durian'), null);
  assert.deepEqual(photoSource([{ object_key: 'preset/mangoes' }], API), { kind: 'preset', key: 'mangoes' });
  assert.deepEqual(photoSource([], API), { kind: 'none' });
  assert.deepEqual(photoSource([{ object_key: 'listings/x/photo.jpg', url: null }], API), { kind: 'none' });
});

test('data URLs split into upload payloads', () => {
  assert.deepEqual(splitDataUrl('data:image/png;base64,iVBORw0KGgo='), {
    contentType: 'image/png', base64: 'iVBORw0KGgo=',
  });
  assert.equal(splitDataUrl('data:image/gif;base64,R0lGOD'), null);
  assert.equal(base64Bytes('AAAA'), 3);
  assert.equal(base64Bytes('AAA='), 2);
  assert.equal(base64Bytes('AA=='), 1);
});

test('harvest options become Kenyan calendar dates and read back naturally', () => {
  // 22:30 UTC is already the next day in Nairobi.
  const now = new Date('2026-09-28T22:30:00Z');
  assert.equal(harvestIsoDate('Harvested Today', now), '2026-09-29');
  assert.equal(harvestIsoDate('Harvested Yesterday', now), '2026-09-28');
  assert.equal(harvestIsoDate('Harvesting Tomorrow', now), '2026-09-30');
  assert.equal(harvestIsoDate('Fresh harvest', now), null);
  assert.equal(harvestLabel('2026-09-29', now), 'Harvested today');
  assert.equal(harvestLabel('2026-09-28', now), 'Harvested yesterday');
  assert.equal(harvestLabel('2026-09-30', now), 'Harvest due tomorrow');
  assert.equal(harvestLabel('2026-09-25', now), 'Harvested 4 days ago');
  assert.match(harvestLabel('2026-01-02', now), /^Harvested /);
  assert.match(harvestLabel('2026-12-01', now), /^Harvest due /);
  assert.equal(harvestLabel(null, now), null);
  assert.equal(harvestLabel('soon', now), null);
});

test('farmer summaries are validated and described', () => {
  const farmer = {
    id: 'f1', display_name: 'Wanjiru Kamau', farm_name: 'Kamau Greens', county: 'Kiambu',
    locality: 'Limuru', verification_status: 'verified', member_since: '2026-03-02T08:00:00',
    active_listings: 3, completed_orders: 12, offers_pickup: true, offers_delivery: true,
    farming_practices: null,
  };
  assert.equal(isFarmerSummary(farmer), true);
  assert.equal(isFarmerSummary({ ...farmer, active_listings: '3' }), false);
  assert.equal(isFarmerSummary(null), false);
  assert.equal(farmerPlace(farmer), 'Limuru, Kiambu');
  assert.equal(farmerPlace({ locality: null, county: ' ' }), null);
  assert.match(memberSince(farmer.member_since), /^Member since /);
  assert.equal(memberSince('not a date'), null);
  assert.equal(handoverOptions(farmer), 'Pickup or delivery');
  assert.equal(handoverOptions({ offers_pickup: false, offers_delivery: true }), 'Delivery only');
  assert.equal(handoverOptions({ offers_pickup: true, offers_delivery: false }), 'Pickup from the farm');
});

test('reservation deadlines show Kenyan time and minutes left', () => {
  const now = new Date('2026-09-29T08:30:00Z');
  assert.equal(reservationDeadline('2026-09-29T08:42:00', now), '11:42 EAT (in 12 min)');
  assert.equal(reservationDeadline('2026-09-29T08:00:00Z', now), '11:00 EAT (expired)');
  assert.equal(reservationDeadline('nope', now), null);
});
