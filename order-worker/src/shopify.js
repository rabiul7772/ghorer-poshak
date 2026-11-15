// Minimal Shopify Admin API client for the order Worker.
// Auth: client credentials grant (Dev Dashboard app installed on the store). The token lasts 24h;
// we cache it in KV for 23h so most requests skip the token call.

const API_VERSION = '2026-10';

export async function getToken(env) {
  const cached = env.ORDERS ? await env.ORDERS.get('admin-token') : null;
  if (cached) return cached;

  const res = await fetch(`https://${env.SHOPIFY_SHOP}.myshopify.com/admin/oauth/access_token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      client_id: env.SHOPIFY_CLIENT_ID,
      client_secret: env.SHOPIFY_CLIENT_SECRET,
      grant_type: 'client_credentials',
    }),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data || !data.access_token) {
    throw new Error(`token request failed (${res.status}): ${data ? JSON.stringify(data).slice(0, 300) : 'no body'}`);
  }
  if (env.ORDERS) await env.ORDERS.put('admin-token', data.access_token, { expirationTtl: 23 * 60 * 60 });
  return data.access_token;
}

export async function admin(env, query, variables, retry = true) {
  const token = await getToken(env);
  const res = await fetch(`https://${env.SHOPIFY_SHOP}.myshopify.com/admin/api/${API_VERSION}/graphql.json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Shopify-Access-Token': token },
    body: JSON.stringify({ query, variables }),
  });
  if (res.status === 401 && retry && env.ORDERS) {
    await env.ORDERS.delete('admin-token');
    return admin(env, query, variables, false);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok || !data) throw new Error(`admin api ${res.status}`);
  if (data.errors) throw new Error('admin api: ' + JSON.stringify(data.errors).slice(0, 500));
  return data.data;
}

const VARIANTS_QUERY = `
  query Variants($ids: [ID!]!) {
    nodes(ids: $ids) {
      ... on ProductVariant {
        id
        title
        sku
        price
        availableForSale
        product { id title status vendor }
      }
    }
  }`;

/** Looks up the requested variants and returns them keyed by numeric id. Prices come from Shopify, never the browser. */
export async function loadVariants(env, items) {
  const ids = items.map((i) => `gid://shopify/ProductVariant/${i.id}`);
  const data = await admin(env, VARIANTS_QUERY, { ids });
  const map = new Map();
  for (const node of data.nodes || []) {
    if (!node || !node.id) continue;
    map.set(Number(node.id.split('/').pop()), node);
  }
  return map;
}

const CUSTOMER_SEARCH = `
  query FindCustomer($q: String!) {
    customers(first: 1, query: $q) { nodes { id } }
  }`;

const CUSTOMER_CREATE = `
  mutation NewCustomer($input: CustomerInput!) {
    customerCreate(input: $input) { customer { id } userErrors { field message } }
  }`;

/**
 * Finds the customer with this phone number or creates one, so repeat buyers collect their order history.
 * Buyers here give phone numbers, not emails, and orderCreate can only link a customer by id or email.
 * Returns the customer GID, or null if anything fails (the order is then placed without a customer link).
 */
export async function findOrCreateCustomer(env, { phone, firstName, lastName, address }) {
  try {
    const found = await admin(env, CUSTOMER_SEARCH, { q: `phone:${phone}` });
    const hit = found.customers && found.customers.nodes && found.customers.nodes[0];
    if (hit) return hit.id;
    const made = await admin(env, CUSTOMER_CREATE, {
      input: {
        firstName,
        lastName: lastName || undefined,
        phone,
        tags: ['website-cod'],
        addresses: [{ ...address }],
      },
    });
    const result = made.customerCreate;
    if (result && result.customer) return result.customer.id;
    console.warn('customerCreate userErrors', JSON.stringify(result && result.userErrors));
  } catch (error) {
    console.warn('customer link skipped', String(error));
  }
  return null;
}

const ORDER_MUTATION = `
  mutation CreateOrder($order: OrderCreateOrderInput!, $options: OrderCreateOptionsInput) {
    orderCreate(order: $order, options: $options) {
      order { id name totalPriceSet { shopMoney { amount } } }
      userErrors { field message }
    }
  }`;

export async function createOrder(env, order) {
  const data = await admin(env, ORDER_MUTATION, {
    order,
    options: { inventoryBehaviour: 'DECREMENT_OBEYING_POLICY', sendReceipt: false, sendFulfillmentReceipt: false },
  });
  return data.orderCreate;
}
