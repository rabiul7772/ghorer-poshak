// Combo price. Products that share a combo group (product metafield custom.combo_group) cost the
// group's combo price (custom.combo_price, whole taka) per piece once the buyer takes
// COMBO_MIN_PIECES or more pieces from that group, in any mix of products and sizes.
// The cart page (theme/sections/rcb-cart.liquid) shows the same sum; this one decides what the order costs.

export const COMBO_MIN_PIECES = 2;

/**
 * @param {{quantity: number, price: number, group: string, comboPrice: number}[]} lines
 * @returns {number[]} the unit price to charge for each line, in the same order
 */
export function comboUnitPrices(lines) {
  const pieces = new Map();
  for (const line of lines) {
    if (line.group && line.comboPrice > 0) pieces.set(line.group, (pieces.get(line.group) || 0) + line.quantity);
  }
  return lines.map((line) => {
    const earned = line.group && line.comboPrice > 0 && pieces.get(line.group) >= COMBO_MIN_PIECES;
    return earned && line.comboPrice < line.price ? line.comboPrice : line.price;
  });
}
