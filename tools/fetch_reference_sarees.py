"""Collect saree products from the reference store (readycartbd.com, the owner's previous shop; the same
supplier now stocks Ghorer Poshak) into data/sarees.json, ready for import.

For each product: title, handle, description, price/compare, images, and the page-only details the
reference theme shows (reasons, specs, product FAQ, sold count)."""
import html
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

BASE = 'https://readycartbd.com'
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
# reference collection handle -> (Ghorer Poshak sub-collection tag, Bangla label)
CATEGORIES = {
    'nokshi-par-saree': ('nokshi-par', 'নকশী পাড় শাড়ি'),
    'lama-silk-saree': ('lama-silk', 'লামা সিল্ক শাড়ি'),
    'kota-cotton-saree': ('kota-cotton', 'কোটা সুতি শাড়ি'),
    'premium-half-silk': ('half-silk', 'হাফসিল্ক শাড়ি'),
    'jamdani-saree': ('jamdani', 'জামদানি শাড়ি'),
}
BN = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
STANDARD_FAQ = ('রিটার্ন', 'ক্যাশ অন ডেলিভারি', 'ডেলিভারি চার্জ')


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en;q=0.9'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8')


class Sections(HTMLParser):
    """Collects text of elements by class: rcb-why__t, rcb-triad__label, dt/dd inside rcb-spec,
    rcb-faq summary + rcb-faq__a."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.why, self.triad, self.spec, self.faq = [], [], [], []
        self.cur = None
        self.buf = []
        self.in_spec = 0
        self.in_faq = 0

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get('class') or ''
        self.stack.append((tag, cls))
        if 'rcb-spec' in cls.split():
            self.in_spec += 1
        if tag == 'details' and 'rcb-faq' in cls.split():
            self.in_faq += 1
            self.faq.append(['', ''])
        target = None
        if 'rcb-why__t' in cls:
            target = 'why'
        elif 'rcb-triad__label' in cls:
            target = 'triad'
        elif self.in_spec and tag in ('dt', 'dd'):
            target = tag
        elif self.in_faq and tag == 'summary':
            target = 'q'
        elif self.in_faq and 'rcb-faq__a' in cls:
            target = 'a'
        if target and self.cur is None:
            self.cur = (target, len(self.stack))
            self.buf = []

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if self.cur and len(self.stack) == self.cur[1]:
            text = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
            kind = self.cur[0]
            if kind == 'why':
                self.why.append(text)
            elif kind == 'triad':
                self.triad.append(text)
            elif kind in ('dt', 'dd'):
                self.spec.append((kind, text))
            elif kind == 'q' and self.faq:
                self.faq[-1][0] = text
            elif kind == 'a' and self.faq:
                self.faq[-1][1] = text
            self.cur = None
        t, cls = self.stack.pop()
        if 'rcb-spec' in cls.split():
            self.in_spec -= 1
        if t == 'details' and 'rcb-faq' in cls.split():
            self.in_faq -= 1

    def handle_data(self, data):
        if self.cur:
            self.buf.append(data)


def page_details(handle):
    p = Sections()
    p.feed(get(f'{BASE}/products/{handle}'))
    sold = None
    for t in p.triad:
        m = re.search(r'([০-৯0-9]+)\s*পিস', t)
        if m:
            sold = int(m.group(1).translate(BN))
    specs, label = [], None
    for kind, text in p.spec:
        if kind == 'dt':
            label = text
        elif label:
            specs.append(f'{label}: {text}')
            label = None
    faq = [f'{q} | {a}' for q, a in p.faq if q and a and not any(s in q for s in STANDARD_FAQ)]
    # the page shows the FAQ block twice on some layouts; keep unique
    faq = list(dict.fromkeys(faq))
    return {'reasons': list(dict.fromkeys(p.why))[:5], 'specs': list(dict.fromkeys(specs)), 'faq': faq, 'sold': sold}


def main(out_path):
    products, seen = [], set()
    for ref_handle, (tag, label) in CATEGORIES.items():
        data = json.loads(get(f'{BASE}/collections/{ref_handle}/products.json?limit=250'))
        for p in data['products']:
            if p['handle'] in seen:
                continue
            seen.add(p['handle'])
            v = p['variants'][0]
            price = v['price']
            compare = v.get('compare_at_price')
            if compare and float(compare) <= float(price):
                compare = None
            item = {
                'handle': p['handle'],
                'title': html.unescape(p['title']).strip(),
                'category_tag': tag,
                'category_label': label,
                'description_html': (p.get('body_html') or '').strip(),
                'price': price,
                'compare': compare,
                'images': [img['src'].split('?')[0] for img in p.get('images', [])],
                'image_alts': [html.unescape(img.get('alt') or p['title']) for img in p.get('images', [])],
            }
            item.update(page_details(p['handle']))
            products.append(item)
            print(f"{len(products):2d} {tag:12s} {item['handle'][:44]:44s} {price:>8s} imgs={len(item['images'])} why={len(item['reasons'])} specs={len(item['specs'])} faq={len(item['faq'])} sold={item['sold']}", flush=True)
            time.sleep(0.4)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=1)
    print('saved', len(products), out_path)


if __name__ == '__main__':
    main(sys.argv[1])
