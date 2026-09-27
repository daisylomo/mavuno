import AsyncStorage from '@react-native-async-storage/async-storage';

export const CART_STORAGE_KEY = '@mavuno_customer_cart';

/** Product id to quantity. */
export type Cart = Record<string, number>;

/**
 * Reads a cart back out of whatever was stored, dropping anything that is not a
 * sensible quantity. Stored carts can be old or hand-edited, so nothing here is
 * trusted: a bad entry is skipped rather than allowed to break the basket.
 */
export function parseStoredCart(raw: string | null): Cart {
  if (!raw) return {};
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {};
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};

  const cart: Cart = {};
  for (const [id, quantity] of Object.entries(parsed as Record<string, unknown>)) {
    if (!id) continue;
    if (typeof quantity !== 'number' || !Number.isInteger(quantity) || quantity <= 0) continue;
    cart[id] = quantity;
  }
  return cart;
}

/**
 * Holds every quantity to the stock still on offer, and forgets products that
 * are no longer for sale.
 *
 * Callers must only run this once the catalogue is fully loaded: anything the
 * catalogue does not know about is treated as withdrawn and dropped. Farmer
 * listings arrive a moment after the page does, so clamping too early would
 * throw away a perfectly good basket line.
 */
export function clampCartToStock(cart: Cart, stockById: Record<string, number>): Cart {
  const clamped: Cart = {};
  for (const [id, quantity] of Object.entries(cart)) {
    const stock = stockById[id];
    if (stock === undefined || stock <= 0) continue;
    clamped[id] = Math.min(quantity, stock);
  }
  return clamped;
}

export async function loadCart(): Promise<Cart> {
  try {
    return parseStoredCart(await AsyncStorage.getItem(CART_STORAGE_KEY));
  } catch {
    return {};
  }
}

export async function saveCart(cart: Cart): Promise<void> {
  try {
    if (Object.keys(cart).length === 0) {
      await AsyncStorage.removeItem(CART_STORAGE_KEY);
      return;
    }
    await AsyncStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
  } catch {
    // A cart that cannot be saved is not worth interrupting the shopper over;
    // it simply will not survive a refresh.
  }
}
