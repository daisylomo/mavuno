// Display helpers for the live catalog, kept apart from the screen so they can
// be tested without a bundler.

/**
 * Renders an API quantity for reading. The API sends a fixed-scale decimal, so
 * a whole 40 arrives as "40.000"; printing that raw reads as a measurement
 * rather than a count. A genuine fraction keeps its detail.
 */
export function formatQuantity(value: string): string {
  const amount = Number(value);
  if (value.trim() === '' || !Number.isFinite(amount)) return value;
  return amount.toLocaleString('en-KE', { maximumFractionDigits: 3 });
}

/**
 * The shorter product name sits under the listing title, but only when it adds
 * something: repeating the title verbatim just looks like a mistake.
 */
export function secondaryName(title: string, productName: string): string | null {
  return productName.trim().toLowerCase() === title.trim().toLowerCase() ? null : productName;
}
