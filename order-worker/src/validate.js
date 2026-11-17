// Server-side copy of the storefront order-form rules (theme/snippets/rcb-cart-validate.liquid).
// The browser checks first for instant feedback; this file is the one that is trusted.

export const COPY = {
  required: 'এই ঘরটি পূরণ করতে হবে।',
  name: 'আপনার পুরো নাম লিখুন।',
  phone: '১১ ডিজিটের মোবাইল নম্বর লিখুন — যেমন 01712345678',
  address: 'পূর্ণ ঠিকানা লিখুন — এলাকা, থানা ও জেলা।',
};

// addressMin 1: any non-blank address is accepted (same rule as the storefront form); the shop confirms by phone.
export const LIMITS = { nameMin: 2, nameMax: 100, addressMin: 1, addressMax: 500, itemsMax: 50, quantityMax: 100 };

const DIGIT_ZEROS = [0x0660, 0x06f0, 0x0966, 0x09e6, 0xff10];

export function clean(value) {
  if (typeof value !== 'string') return '';
  return value.replace(/[​-‍﻿]/g, '').replace(/\s+/g, ' ').trim();
}

export function checkPhone(raw) {
  const text = clean(raw);
  if (!text) return { ok: false, message: COPY.required };
  let digits = text
    .replace(/[٠-٩۰-۹०-९০-৯０-９]/g, (d) => {
      const code = d.charCodeAt(0);
      for (const zero of DIGIT_ZEROS) if (code >= zero && code <= zero + 9) return String(code - zero);
      return d;
    })
    .replace(/\D/g, '');
  if (digits.startsWith('00880')) digits = digits.slice(2);
  if (digits.startsWith('880')) digits = digits.slice(3);
  if (digits.startsWith('0')) digits = digits.slice(1);
  if (!/^1[3-9]\d{8}$/.test(digits)) return { ok: false, message: COPY.phone };
  return { ok: true, value: '+880' + digits, local: '0' + digits };
}

export function checkName(raw) {
  const text = clean(raw);
  if (!text) return { ok: false, message: COPY.required };
  if (text.length < LIMITS.nameMin) return { ok: false, message: COPY.name };
  return { ok: true, value: text.slice(0, LIMITS.nameMax) };
}

export function checkAddress(raw) {
  const text = clean(raw);
  if (!text) return { ok: false, message: COPY.required };
  if (text.length < LIMITS.addressMin) return { ok: false, message: COPY.address };
  return { ok: true, value: text.slice(0, LIMITS.addressMax) };
}

export function splitName(full) {
  const at = full.indexOf(' ');
  if (at === -1) return { firstName: full, lastName: '' };
  return { firstName: full.slice(0, at), lastName: full.slice(at + 1).trim() };
}

/** Validates the items list and merges repeated variants. Returns { ok, items? }. */
export function checkItems(list) {
  if (!Array.isArray(list) || list.length === 0 || list.length > LIMITS.itemsMax) return { ok: false };
  const merged = new Map();
  for (const item of list) {
    const id = Number(item && item.id);
    const quantity = Number(item && item.quantity);
    if (!Number.isSafeInteger(id) || id <= 0) return { ok: false };
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > LIMITS.quantityMax) return { ok: false };
    merged.set(id, Math.min(LIMITS.quantityMax, (merged.get(id) || 0) + quantity));
  }
  return { ok: true, items: [...merged].map(([id, quantity]) => ({ id, quantity })) };
}

/** Validates the whole request body. Returns { ok, field?, message?, value? }. */
export function checkOrder(body) {
  if (!body || typeof body !== 'object') return { ok: false, message: 'invalid' };

  const name = checkName(body.name);
  if (!name.ok) return { ok: false, field: 'name', message: name.message };
  const phone = checkPhone(body.phone);
  if (!phone.ok) return { ok: false, field: 'phone', message: phone.message };
  const address = checkAddress(body.address);
  if (!address.ok) return { ok: false, field: 'address', message: address.message };

  const items = checkItems(body.items);
  if (!items.ok) return { ok: false, message: 'items' };

  const attemptId = typeof body.attemptId === 'string' && /^[\w-]{6,80}$/.test(body.attemptId) ? body.attemptId : '';
  const zone = body.deliveryZone === 'inside' ? 'inside' : 'outside';

  return {
    ok: true,
    value: {
      name: name.value,
      phone: phone.value,
      phoneLocal: phone.local,
      address: address.value,
      items: items.items,
      attemptId,
      zone,
      honeypot: clean(body.website),
      pageUrl: typeof body.pageUrl === 'string' ? body.pageUrl.slice(0, 500) : '',
      referrer: typeof body.referrer === 'string' ? body.referrer.slice(0, 500) : '',
    },
  };
}
