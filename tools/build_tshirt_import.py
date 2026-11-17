"""Turn data/tshirts.json into Shopify productSet inputs (data/import/tshirt-<handle>.json).

Every colour of a style is its own product ("<style title> — <colour>") with Size variants and that
colour's photos, so each colour gets its own card in the collection. Unlike sarees, stock is counted:
every variant is tracked, gets its quantity at the shop location, and cannot be ordered at zero.

Combo price: all colours of a style share custom.combo_group; taking 2 or more pieces from the group
makes each piece cost custom.combo_price. The cart (theme) and the order Worker both read these two
metafields, so the offer is changed in Shopify admin, not in code.

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
styles = json.load(open(src, encoding='utf-8'))


def to_input(p, c):
    if c.get('media_ids'):  # photos already in the store's Files
        files = [{'id': i} for i in c['media_ids']]
    else:
        files = [{'originalSource': u, 'alt': a, 'contentType': 'IMAGE'} for u, a in zip(c['images'], c['image_alts'])]
    variants = [{
        'optionValues': [{'optionName': 'Size', 'name': size}],
        'sku': f"{p.get('sku_prefix', SKU_PREFIX)}-{c['sku_code']}-{size}",
        'price': p['price'],
        'compareAtPrice': p['compare'],
        'inventoryItem': {'tracked': True},
        'inventoryPolicy': 'DENY',
        'inventoryQuantities': [{'locationId': LOCATION, 'name': 'available', 'quantity': c['stock'][size]}],
    } for size in p['sizes']]
    features = ''.join(f'<li>{html.escape(f)}</li>' for f in p['features'])
    metafields = [
        {'namespace': 'custom', 'key': 'summary', 'type': 'multi_line_text_field', 'value': p['summary']},
        {'namespace': 'custom', 'key': 'reasons', 'type': 'list.single_line_text_field', 'value': json.dumps(p['reasons'], ensure_ascii=False)},
        {'namespace': 'custom', 'key': 'specs', 'type': 'list.single_line_text_field', 'value': json.dumps(p['specs'], ensure_ascii=False)},
        {'namespace': 'custom', 'key': 'faq', 'type': 'multi_line_text_field', 'value': '\n'.join(p['faq'])},
    ]
    if p.get('combo'):
        metafields += [
            {'namespace': 'custom', 'key': 'combo_group', 'type': 'single_line_text_field', 'value': p['combo']['group']},
            {'namespace': 'custom', 'key': 'combo_price', 'type': 'number_integer', 'value': str(p['combo']['price'])},
        ]
    return {
        'title': c['title'],
        'handle': c['handle'],
        'productType': p['product_type'],
        'vendor': 'Ghorer Poshak',
        'status': 'ACTIVE',
        'tags': p['tags'],
        'descriptionHtml': f"<p>{html.escape(p['summary'])}</p><ul>{features}</ul>",
        'seo': {'title': f"{c['title']} | {p['title_en']}"},
        'files': files,
        'productOptions': [{'name': 'Size', 'values': [{'name': s} for s in p['sizes']]}],
        'variants': variants,
        'metafields': metafields,
    }


for p in styles:
    for c in p['colors']:
        path = os.path.join(out_dir, f"tshirt-{c['handle']}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'p0': to_input(p, c)}, f, ensure_ascii=False, separators=(',', ':'))
        print(path, len(p['sizes']), 'variants', os.path.getsize(path), 'bytes')
