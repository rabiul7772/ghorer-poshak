import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/index.js';

const ORIGIN = 'https://ghorerposhak.com';

function makeKv() {
  const store = new Map();
  return {
    store,
    async get(key, type) {
      const v = store.get(key);
      if (v == null) return null;
      return type === 'json' ? JSON.parse(v) : v;
    },
    async put(key, value) { store.set(key, value); },
    async delete(key) { store.delete(key); },
  };
}

let env;
let calls;
let shopifyState;

beforeEach(() => {
  env = {
    SHOPIFY_SHOP: 'test-shop',
    SHOPIFY_CLIENT_ID: 'id',
    SHOPIFY_CLIENT_SECRET: 'secret',
    ALLOWED_ORIGINS: `${ORIGIN},http://127.0.0.1:9292`,
    DELIVERY_INSIDE: '80',
    DELIVERY_OUTSIDE: '120',
    ORDERS: makeKv(),
  };
  calls = [];
  shopifyState = { orderCount: 1000, failCustomerOnce: false, stockError: false };
  globalThis.fetch = async (url, init) => {
    const body = init && init.body ? JSON.parse(init.body) : null;
    calls.push({ url: String(url), body });
    if (String(url).endsWith('/admin/oauth/access_token')) {
      return new Response(JSON.stringify({ access_token: 'tok', expires_in: 86399 }), { status: 200 });
    }
    if (body.query.includes('nodes(ids')) {
      const nodes = body.variables.ids.map((gid) => {
        const n = Number(gid.split('/').pop());
        if (n === 999) return null;
        return {
          id: gid,
          title: n === 1 ? 'Default Title' : 'L',
          sku: 'SKU' + n,
          price: n === 1 ? '1250.00' : '450.00',
          availableForSale: n !== 3,
          product: { id: 'gid://shopify/Product/' + n, title: 'পণ্য ' + n, status: 'ACTIVE', vendor: 'Ghorer Poshak' },
        };
      });
      return new Response(JSON.stringify({ data: { nodes } }), { status: 200 });
    }
    if (body.query.includes('customers(first')) {
      const known = shopifyState.knownPhones || [];
      const phone = body.variables.q.replace('phone:', '');
      return new Response(JSON.stringify({ data: { customers: { nodes: known.includes(phone) ? [{ id: 'gid://shopify/Customer/777' }] : [] } } }), { status: 200 });
    }
    if (body.query.includes('customerCreate')) {
      shopifyState.createdCustomers = (shopifyState.createdCustomers || 0) + 1;
      return new Response(JSON.stringify({ data: { customerCreate: { customer: { id: 'gid://shopify/Customer/888' }, userErrors: [] } } }), { status: 200 });
    }
    if (body.query.includes('orderCreate')) {
      const customer = body.variables.order.customer;
      // Real Shopify rejects toUpsert without id/email as a top-level GraphQL error.
      if (customer && customer.toUpsert && !customer.toUpsert.id && !customer.toUpsert.email) {
        return new Response(JSON.stringify({ errors: [{ message: 'OrderCreateUpsertCustomerAttributesInput requires at least one of id, email' }] }), { status: 200 });
      }
      if (shopifyState.failCustomerOnce && customer) {
        shopifyState.failCustomerOnce = false;
        return new Response(JSON.stringify({ errors: [{ message: 'customer problem' }] }), { status: 200 });
      }
      if (shopifyState.stockError) {
        return new Response(JSON.stringify({ data: { orderCreate: { order: null, userErrors: [{ field: ['order'], message: 'Not enough inventory available' }] } } }), { status: 200 });
      }
      shopifyState.orderCount += 1;
      return new Response(JSON.stringify({ data: { orderCreate: { order: { id: 'gid://shopify/Order/1', name: '#' + shopifyState.orderCount, totalPriceSet: { shopMoney: { amount: '0' } } }, userErrors: [] } } }), { status: 200 });
    }
    throw new Error('unexpected fetch ' + url);
  };
});

function post(body, origin = ORIGIN, ip = '1.1.1.1') {
  return new Request('https://w.example/order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Origin: origin, 'CF-Connecting-IP': ip },
    body: JSON.stringify(body),
  });
}

const good = (extra = {}) => ({
  attemptId: 'p2_test-attempt-1',
  items: [{ id: 1, quantity: 1 }, { id: 2, quantity: 2 }],
  name: 'রহিম উদ্দিন',
  phone: '+8801712345678',
  address: 'বাড়ি ১, রোড ২, মিরপুর ১০, ঢাকা',
  deliveryZone: 'inside',
  website: '',
  clientTotal: 99999,
  ...extra,
});

const orderCall = () => calls.find((c) => c.body && c.body.query && c.body.query.includes('orderCreate'));

test('creates a COD order with Shopify prices and the Dhaka delivery charge', async () => {
  const res = await worker.fetch(post(good()), env);
  const data = await res.json();
  assert.equal(data.ok, true);
  assert.equal(data.orderNumber, '#1001');
  assert.equal(data.total, 1250 + 2 * 450 + 80);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  const order = orderCall().body.variables.order;
  assert.equal(order.financialStatus, 'PENDING');
  assert.equal(order.shippingLines[0].title, 'ঢাকার ভেতরে');
  assert.equal(order.shippingLines[0].priceSet.shopMoney.amount, '80');
  assert.equal(order.lineItems[0].priceSet.shopMoney.amount, '1250.00', 'price comes from Shopify, not clientTotal');
  assert.equal(order.lineItems[0].variantTitle, null);
  assert.equal(order.lineItems[1].variantTitle, 'L');
  assert.equal(order.shippingAddress.countryCode, 'BD');
  assert.equal(order.phone, '+8801712345678');
  assert.ok(order.note.includes('মিরপুর ১০'));
});

test('outside Dhaka uses the 120 charge', async () => {
  await worker.fetch(post(good({ deliveryZone: 'outside' })), env);
  const order = orderCall().body.variables.order;
  assert.equal(order.shippingLines[0].title, 'ঢাকার বাইরে');
  assert.equal(order.shippingLines[0].priceSet.shopMoney.amount, '120');
});

test('same attemptId twice creates only one order', async () => {
  const a = await (await worker.fetch(post(good()), env)).json();
  const b = await (await worker.fetch(post(good()), env)).json();
  assert.deepEqual(a, b);
  assert.equal(calls.filter((c) => c.body && c.body.query && c.body.query.includes('orderCreate')).length, 1);
});

test('field errors map to the form field', async () => {
  const bad = await (await worker.fetch(post(good({ phone: '12345' })), env)).json();
  assert.equal(bad.ok, false);
  assert.equal(bad.field, 'phone');
  const noName = await (await worker.fetch(post(good({ name: ' ' })), env)).json();
  assert.equal(noName.field, 'name');
  const blankAddress = await (await worker.fetch(post(good({ address: '   ' })), env)).json();
  assert.equal(blankAddress.field, 'address');
});

test('a one-character address is accepted', async () => {
  const data = await (await worker.fetch(post(good({ address: 'ক', attemptId: 'p2_addr1' })), env)).json();
  assert.equal(data.ok, true);
  assert.equal(orderCall().body.variables.order.shippingAddress.address1, 'ক');
});

test('Bangla digits in the phone are accepted', async () => {
  const data = await (await worker.fetch(post(good({ phone: '০১৭১২৩৪৫৬৭৮', attemptId: 'p2_bn' })), env)).json();
  assert.equal(data.ok, true);
  assert.equal(orderCall().body.variables.order.phone, '+8801712345678');
});

test('sold-out and missing variants are refused before ordering', async () => {
  const soldOut = await (await worker.fetch(post(good({ items: [{ id: 3, quantity: 1 }], attemptId: 'p2_so' })), env)).json();
  assert.equal(soldOut.ok, false);
  assert.match(soldOut.message, /স্টকে নেই/);
  const missing = await (await worker.fetch(post(good({ items: [{ id: 999, quantity: 1 }], attemptId: 'p2_ms' })), env)).json();
  assert.equal(missing.ok, false);
  assert.equal(orderCall(), undefined);
});

test('honeypot submissions get a fake success and no order', async () => {
  const data = await (await worker.fetch(post(good({ website: 'http://spam' })), env)).json();
  assert.equal(data.ok, true);
  assert.equal(orderCall(), undefined);
});

test('unknown origins are rejected; preflight works for allowed ones', async () => {
  const res = await worker.fetch(post(good(), 'https://evil.example'), env);
  assert.equal(res.status, 403);
  const pre = await worker.fetch(new Request('https://w.example/order', { method: 'OPTIONS', headers: { Origin: ORIGIN } }), env);
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get('Access-Control-Allow-Methods'), 'POST, OPTIONS');
});

test('new buyers get a customer record; returning buyers are linked by phone', async () => {
  await worker.fetch(post(good({ attemptId: 'p2_newc' })), env);
  assert.equal(shopifyState.createdCustomers, 1);
  assert.deepEqual(orderCall().body.variables.order.customer, { toAssociate: { id: 'gid://shopify/Customer/888' } });

  shopifyState.knownPhones = ['+8801812345678'];
  calls = [];
  await worker.fetch(post(good({ attemptId: 'p2_oldc', phone: '01812345678' })), env);
  assert.equal(shopifyState.createdCustomers, 1, 'no duplicate customer');
  assert.deepEqual(orderCall().body.variables.order.customer, { toAssociate: { id: 'gid://shopify/Customer/777' } });
});

test('customer conflict retries without the customer link', async () => {
  shopifyState.failCustomerOnce = true;
  const data = await (await worker.fetch(post(good({ attemptId: 'p2_cust' })), env)).json();
  assert.equal(data.ok, true);
  const creates = calls.filter((c) => c.body && c.body.query && c.body.query.includes('orderCreate'));
  assert.equal(creates.length, 2);
  assert.equal(creates[1].body.variables.order.customer, undefined);
});

test('inventory errors from Shopify become a stock message', async () => {
  shopifyState.stockError = true;
  const data = await (await worker.fetch(post(good({ attemptId: 'p2_inv' })), env)).json();
  assert.equal(data.ok, false);
  assert.match(data.message, /স্টকে নেই/);
});

test('rate limit per phone', async () => {
  let last;
  for (let i = 0; i < 5; i++) {
    last = await (await worker.fetch(post(good({ attemptId: 'p2_rl' + i }), ORIGIN, '9.9.9.' + i), env)).json();
  }
  assert.equal(last.ok, false);
  assert.match(last.message, /অনেকবার/);
});

test('token is fetched once and cached', async () => {
  await worker.fetch(post(good({ attemptId: 'p2_t1' })), env);
  await worker.fetch(post(good({ attemptId: 'p2_t2', phone: '01812345678' })), env);
  assert.equal(calls.filter((c) => c.url.endsWith('/admin/oauth/access_token')).length, 1);
});
