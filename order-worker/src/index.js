// Ghorer Poshak one-page Cash-on-Delivery order endpoint.
//
// Contract (theme/assets/rcb-order.js):
//   POST { attemptId, items:[{id, quantity}], name, phone, address, deliveryZone:'inside'|'outside', website, ... }
//   →    { ok: true, orderNumber: '#1001' }
//   or   { ok: false, field?: 'name'|'phone'|'address', message: '<Bangla text shown to the buyer>' }
//   POST /quote { items:[{id, quantity}] } → { ok: true, subtotal, comboSaved }
//     What /order would charge for these items (no order is made). Used to check prices and combos.
// The browser only reads `ok`, `field`, `message` and `orderNumber`, so every failure is a 200 with ok:false.

import { checkOrder, checkItems, splitName } from './validate.js';
import { loadVariants, createOrder, findOrCreateCustomer } from './shopify.js';
import { comboUnitPrices } from './combo.js';

const MSG = {
  generic: 'অর্ডারটি এই মুহূর্তে নেওয়া যায়নি। কয়েক সেকেন্ড পরে আবার চেষ্টা করুন, অথবা নিচের নম্বরে মেসেজ দিন।',
  empty: 'আপনার ব্যাগে কোনো পণ্য পাওয়া যায়নি। পেজটি রিফ্রেশ করে আবার চেষ্টা করুন।',
  gone: 'ব্যাগের একটি পণ্য আর পাওয়া যাচ্ছে না। পেজটি রিফ্রেশ করে আবার দেখুন।',
  stock: (title) => `"${title}" এখন স্টকে নেই বা চাওয়া পরিমাণে নেই। পরিমাণ কমিয়ে বা অন্য সাইজ বেছে আবার চেষ্টা করুন।`,
  tooMany: 'অল্প সময়ে অনেকবার অর্ডারের চেষ্টা হয়েছে। কিছুক্ষণ পরে আবার চেষ্টা করুন, অথবা আমাদের ফোন করুন।',
};

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get('Origin') || '';
    const cors = corsHeaders(origin, env);

    if (request.method === 'OPTIONS') return new Response(null, { status: cors ? 204 : 403, headers: cors || {} });

    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/health') return json({ ok: true }, cors);
    const quote = url.pathname === '/quote';
    if (request.method !== 'POST' || (url.pathname !== '/order' && !quote)) return json({ ok: false, message: 'not found' }, cors, 404);
    if (!cors) return json({ ok: false, message: 'origin not allowed' }, null, 403);

    let body;
    try {
      const text = await request.text();
      if (text.length > 20000) return json({ ok: false, message: MSG.generic }, cors);
      body = JSON.parse(text);
    } catch {
      return json({ ok: false, message: MSG.generic }, cors);
    }

    try {
      return json(await (quote ? handleQuote(body, request, env) : handleOrder(body, request, env, ctx)), cors);
    } catch (error) {
      console.error('order failed', error && error.stack ? error.stack : String(error));
      return json({ ok: false, message: MSG.generic }, cors);
    }
  },
};

async function handleOrder(body, request, env) {
  const checked = checkOrder(body);
  if (!checked.ok) {
    if (checked.field) return { ok: false, field: checked.field, message: checked.message };
    return { ok: false, message: checked.message === 'items' ? MSG.empty : MSG.generic };
  }
  const input = checked.value;

  // Bots fill the hidden "website" field; pretend it worked so they don't retry.
  if (input.honeypot) return { ok: true, orderNumber: '' };

  const kv = env.ORDERS;
  const attemptKey = input.attemptId ? `attempt:${input.attemptId}` : '';

  // Same attempt sent twice (double tap, flaky network): return the first result instead of a second order.
  if (kv && attemptKey) {
    const prior = await kv.get(attemptKey, 'json');
    if (prior && prior.ok) return prior;
  }

  // Abuse limits: per IP and per phone number.
  if (kv) {
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const hour = Math.floor(Date.now() / 3600000);
    const limited =
      (await bump(kv, `rl:ip:${ip}:${hour}`, Number(env.MAX_ORDERS_PER_IP_HOUR || 6))) ||
      (await bump(kv, `rl:ph:${input.phone}:${hour}`, Number(env.MAX_ORDERS_PER_PHONE_HOUR || 4)));
    if (limited) return { ok: false, message: MSG.tooMany };
  }

  const lines = await priceItems(env, input.items);
  if (!lines.ok) return { ok: false, message: lines.message };
  const { lineItems, subtotal, comboSaved } = lines;

  const inside = input.zone === 'inside';
  const deliveryCharge = Number(inside ? env.DELIVERY_INSIDE || 80 : env.DELIVERY_OUTSIDE || 120);
  const deliveryTitle = inside ? 'ঢাকার ভেতরে' : 'ঢাকার বাইরে';
  const { firstName, lastName } = splitName(input.name);
  const address = {
    firstName,
    lastName: lastName || '-',
    address1: input.address,
    city: inside ? 'Dhaka' : 'Bangladesh',
    countryCode: 'BD',
    phone: input.phone,
  };

  const order = {
    currency: 'BDT',
    presentmentCurrency: 'BDT',
    financialStatus: 'PENDING',
    phone: input.phone,
    lineItems,
    shippingAddress: address,
    billingAddress: address,
    shippingLines: [
      { title: deliveryTitle, code: inside ? 'dhaka-inside' : 'dhaka-outside', source: 'ghorer-poshak', priceSet: { shopMoney: { amount: String(deliveryCharge), currencyCode: 'BDT' } } },
    ],
    note: [
      `ক্যাশ অন ডেলিভারি — ${deliveryTitle}`,
      `নাম: ${input.name}`,
      `ফোন: ${input.phoneLocal}`,
      `ঠিকানা: ${input.address}`,
      ...(comboSaved > 0 ? [`কম্বো দাম ধরা হয়েছে — ছাড় ${comboSaved} টাকা`] : []),
    ].join('\n'),
    tags: ['website-cod', inside ? 'dhaka-inside' : 'dhaka-outside'],
    customAttributes: [
      { key: 'ডেলিভারি এলাকা', value: deliveryTitle },
      { key: 'অর্ডার ফর্ম', value: 'one-page-cod' },
    ],
    sourceIdentifier: input.attemptId || undefined,
  };
  if (comboSaved > 0) {
    order.tags.push('combo');
    order.customAttributes.push({ key: 'কম্বো ছাড়', value: `${comboSaved} টাকা` });
  }
  if (input.referrer && /^https?:\/\//.test(input.referrer)) order.referringSite = input.referrer;
  if (input.pageUrl && /^https?:\/\//.test(input.pageUrl)) order.sourceUrl = input.pageUrl;

  const customerId = await findOrCreateCustomer(env, { phone: input.phone, firstName, lastName, address });
  if (customerId) order.customer = { toAssociate: { id: customerId } };

  let result;
  try {
    result = await createOrder(env, order);
  } catch (error) {
    if (!order.customer) throw error;
    console.warn('orderCreate with customer failed, retrying without', String(error));
    result = null;
  }
  // The order matters more than the customer link: if linking caused a problem, retry once without it.
  if (order.customer && (!result || !result.order)) {
    delete order.customer;
    result = await createOrder(env, order);
  }

  if (!result || !result.order) {
    const errors = (result && result.userErrors) || [];
    console.error('orderCreate userErrors', JSON.stringify(errors));
    const text = JSON.stringify(errors);
    if (/inventory|stock|available/i.test(text)) return { ok: false, message: MSG.stock(lineItems[0].title) };
    return { ok: false, message: MSG.generic };
  }

  const response = { ok: true, orderNumber: result.order.name, total: subtotal + deliveryCharge };
  if (kv && attemptKey) await kv.put(attemptKey, JSON.stringify(response), { expirationTtl: 2 * 24 * 60 * 60 });
  return response;
}

/**
 * Prices the items the way the order will be charged. Prices, titles and stock come from Shopify.
 * Returns { ok: true, lineItems, subtotal, comboSaved } or { ok: false, message }.
 */
async function priceItems(env, items) {
  const variants = await loadVariants(env, items);
  const lineItems = [];
  const priced = [];
  for (const item of items) {
    const v = variants.get(item.id);
    if (!v || !v.product || v.product.status !== 'ACTIVE') return { ok: false, message: MSG.gone };
    if (!v.availableForSale) return { ok: false, message: MSG.stock(v.product.title) };
    priced.push({
      quantity: item.quantity,
      price: Number(v.price),
      group: String((v.product.comboGroup && v.product.comboGroup.value) || '').trim(),
      comboPrice: Number(v.product.comboPrice && v.product.comboPrice.value) || 0,
    });
    lineItems.push({
      variantId: v.id,
      quantity: item.quantity,
      title: v.product.title,
      variantTitle: v.title === 'Default Title' ? null : v.title,
      sku: v.sku || null,
      vendor: v.product.vendor || null,
      requiresShipping: true,
      priceSet: { shopMoney: { amount: v.price, currencyCode: 'BDT' } },
    });
  }

  // Combo price: 2+ pieces from one combo group are charged the group's combo price each.
  let subtotal = 0;
  let comboSaved = 0;
  comboUnitPrices(priced).forEach((unit, i) => {
    const line = priced[i];
    subtotal += unit * line.quantity;
    if (unit === line.price) return;
    comboSaved += (line.price - unit) * line.quantity;
    lineItems[i].priceSet = { shopMoney: { amount: String(unit), currencyCode: 'BDT' } };
  });
  return { ok: true, lineItems, subtotal, comboSaved };
}

/** POST /quote: the same sum /order would charge, without making an order. */
async function handleQuote(body, request, env) {
  const checked = checkItems(body && body.items);
  if (!checked.ok) return { ok: false, message: MSG.empty };
  if (env.ORDERS) {
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const hour = Math.floor(Date.now() / 3600000);
    if (await bump(env.ORDERS, `rl:quote:${ip}:${hour}`, Number(env.MAX_QUOTES_PER_IP_HOUR || 120))) return { ok: false, message: MSG.tooMany };
  }
  const lines = await priceItems(env, checked.items);
  if (!lines.ok) return { ok: false, message: lines.message };
  return { ok: true, subtotal: lines.subtotal, comboSaved: lines.comboSaved };
}

/** Increments a counter; returns true when the limit is exceeded. */
async function bump(kv, key, limit) {
  const count = Number((await kv.get(key)) || 0) + 1;
  await kv.put(key, String(count), { expirationTtl: 3700 });
  return count > limit;
}

function corsHeaders(origin, env) {
  const allowed = String(env.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  if (!origin || !allowed.includes(origin)) return null;
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function json(data, cors, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...(cors || {}) },
  });
}
