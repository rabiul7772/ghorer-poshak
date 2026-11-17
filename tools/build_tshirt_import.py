"""Turn data/tshirts.json into Shopify productSet inputs (data/import/tshirt-NN.json), one product per file.

Each product has Color x Size variants. Unlike sarees, stock is counted: every variant is tracked,
gets its quantity at the shop location, and cannot be ordered once it reaches zero.
Photos are grouped by colour (model front, model back, flat front, flat back); every variant of a
colour points at that colour's first photo, so picking a colour on the product page jumps to it.

Usage: build_tshirt_import.py <tshirts.json> <out_dir>
"""
import html
import json
import os
import sys

LOCATION = 'gid://shopify/Location/88953127002'  # Mirpur 10
SKU_PREFIX = 'GP-WFS'

src, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
products = json.load(open(src, encoding='utf-8'))


def to_input(p):
    files, variants = [], []
    for c in p['colors']:
        colour_files = [{'originalSource': u, 'alt': a, 'contentType': 'IMAGE'}
                        for u, a in zip(c['images'], c['image_alts'])]
        files += colour_files
        for size in p['sizes']:
            variants.append({
                'optionValues': [{'optionName': 'Color', 'name': c['name']}, {'optionName': 'Size', 'name': size}],
                'sku': f"{p.get('sku_prefix', SKU_PREFIX)}-{c['sku_code']}-{size}",
                'price': p['price'],
                'compareAtPrice': p['compare'],
                'inventoryItem': {'tracked': True},
                'inventoryPolicy': 'DENY',
                'inventoryQuantities': [{'locationId': LOCATION, 'name': 'available', 'quantity': c['stock'][size]}],
                'file': colour_files[0],
            })
    features = ''.join(f'<li>{html.escape(f)}</li>' for f in p['features'])
    return {
        'title': p['title'],
        'handle': p['handle'],
        'productType': p['product_type'],
        'vendor': 'Ghorer Poshak',
        'status': 'ACTIVE',
        'tags': p['tags'],
        'descriptionHtml': f"<p>{html.escape(p['summary'])}</p><ul>{features}</ul>",
        'seo': {'title': f"{p['title']} | {p['title_en']}"},
        'files': files,
        'productOptions': [
            {'name': 'Color', 'values': [{'name': c['name']} for c in p['colors']]},
            {'name': 'Size', 'values': [{'name': s} for s in p['sizes']]},
        ],
        'variants': variants,
        'metafields': [
            {'namespace': 'custom', 'key': 'summary', 'type': 'multi_line_text_field', 'value': p['summary']},
            {'namespace': 'custom', 'key': 'reasons', 'type': 'list.single_line_text_field', 'value': json.dumps(p['reasons'], ensure_ascii=False)},
            {'namespace': 'custom', 'key': 'specs', 'type': 'list.single_line_text_field', 'value': json.dumps(p['specs'], ensure_ascii=False)},
            {'namespace': 'custom', 'key': 'faq', 'type': 'multi_line_text_field', 'value': '\n'.join(p['faq'])},
        ],
    }


for i, p in enumerate(products, 1):
    path = os.path.join(out_dir, f'tshirt-{i:02d}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'p0': to_input(p)}, f, ensure_ascii=False, separators=(',', ':'))
    print(path, len(p['colors']) * len(p['sizes']), 'variants', os.path.getsize(path), 'bytes')
