import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clampCartToStock,
  parseStoredCart,
} from '../src/components/customer-cart-storage.ts';

test('reads a saved cart back', () => {
  assert.deepEqual(parseStoredCart('{"tomatoes":2,"honey":1}'), { tomatoes: 2, honey: 1 });
});

test('an empty or missing cart is not an error', () => {
  assert.deepEqual(parseStoredCart(null), {});
  assert.deepEqual(parseStoredCart(''), {});
  assert.deepEqual(parseStoredCart('{}'), {});
});

test('rubbish in storage does not break the basket', () => {
  assert.deepEqual(parseStoredCart('not json'), {});
  assert.deepEqual(parseStoredCart('[1,2,3]'), {});
  assert.deepEqual(parseStoredCart('"a string"'), {});
  assert.deepEqual(parseStoredCart('null'), {});
});

test('drops quantities that are not whole positive numbers', () => {
  assert.deepEqual(
    parseStoredCart('{"good":3,"zero":0,"negative":-2,"fraction":1.5,"text":"4","nothing":null}'),
    { good: 3 },
  );
});

test('holds quantities down to the stock on offer', () => {
  assert.deepEqual(clampCartToStock({ kale: 10 }, { kale: 4 }), { kale: 4 });
  assert.deepEqual(clampCartToStock({ kale: 2 }, { kale: 4 }), { kale: 2 });
});

test('forgets a product that has sold out', () => {
  assert.deepEqual(clampCartToStock({ kale: 3, honey: 1 }, { kale: 0, honey: 5 }), { honey: 1 });
});

test('forgets a product the catalogue no longer offers', () => {
  // A farmer can withdraw a listing while it sits in someone's basket. Once the
  // catalogue is loaded, anything missing from it is gone for good and must not
  // linger in storage waiting to reappear.
  assert.deepEqual(clampCartToStock({ withdrawn: 2, honey: 1 }, { honey: 5 }), { honey: 1 });
});

test('an empty cart stays empty', () => {
  assert.deepEqual(clampCartToStock({}, { kale: 4 }), {});
});
