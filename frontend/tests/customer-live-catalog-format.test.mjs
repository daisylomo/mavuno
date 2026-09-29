import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatQuantity,
  secondaryName,
} from '../src/components/customer-live-catalog-format.ts';

test('a whole quantity reads as a count, not a measurement', () => {
  // The API sends a fixed-scale decimal, so 40 arrives as "40.000".
  assert.equal(formatQuantity('40.000'), '40');
  assert.equal(formatQuantity('8.000'), '8');
});

test('a genuine fraction keeps its detail', () => {
  assert.equal(formatQuantity('1.500'), '1.5');
  assert.equal(formatQuantity('0.250'), '0.25');
});

test('large quantities are grouped for reading', () => {
  assert.equal(formatQuantity('1200.000'), '1,200');
});

test('a quantity that is not a number is shown untouched', () => {
  assert.equal(formatQuantity('unknown'), 'unknown');
  assert.equal(formatQuantity(''), '');
});

test('the product name is hidden when it only repeats the title', () => {
  assert.equal(secondaryName('Sukuma Wiki', 'Sukuma Wiki'), null);
  assert.equal(secondaryName('Sukuma Wiki', 'sukuma wiki'), null);
  assert.equal(secondaryName('Sukuma Wiki', '  Sukuma Wiki  '), null);
});

test('the product name is kept when it adds something', () => {
  assert.equal(secondaryName('Fresh Sukuma Wiki, Grade 1', 'Sukuma Wiki'), 'Sukuma Wiki');
});
