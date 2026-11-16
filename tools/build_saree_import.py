"""Turn data/sarees.json into Shopify productSet inputs (data/import/batch-NN.json), 5 products per batch.
Stock is unlimited: inventory is not tracked, so products never sell out.
Reference sold counts are deliberately NOT copied (they were the old shop's sales)."""
import json
import os
import sys

src, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)
products = json.load(open(src, encoding='utf-8'))


def clean_html(raw):
    """Keep only simple formatting tags (no attributes); drop wrappers like <div class="markdown ...">/<span>."""
    import re
    s = re.sub(r'<(/?)(div|span)\b[^>]*>', '', raw or '', flags=re.I)
    s = re.sub(r'<(p|br|strong|b|em|i|ul|ol|li)\b[^>]*?(/?)>', r'<\1\2>', s, flags=re.I)
    s = re.sub(r'<(?!/?(p|br|strong|b|em|i|ul|ol|li)\b)[^>]+>', '', s, flags=re.I)
    s = re.sub(r'\s*\n\s*', '\n', s).strip()
    return s


def to_input(p):
    metafields = []
    if p['reasons']:
        metafields.append({'namespace': 'custom', 'key': 'reasons', 'type': 'list.single_line_text_field', 'value': json.dumps(p['reasons'], ensure_ascii=False)})
    if p['specs']:
        metafields.append({'namespace': 'custom', 'key': 'specs', 'type': 'list.single_line_text_field', 'value': json.dumps(p['specs'], ensure_ascii=False)})
    if p['faq']:
        metafields.append({'namespace': 'custom', 'key': 'faq', 'type': 'multi_line_text_field', 'value': '\n'.join(p['faq'])})
    variant = {
        'optionValues': [{'optionName': 'Title', 'name': 'Default Title'}],
        'price': p['price'],
        'inventoryItem': {'tracked': False},
        'inventoryPolicy': 'CONTINUE',
    }
    if p['compare']:
        variant['compareAtPrice'] = p['compare']
    return {
        'title': p['title'],
        'handle': p['handle'],
        'productType': 'Saree',
        'vendor': 'Ghorer Poshak',
        'status': 'ACTIVE',
        'tags': ['শাড়ি', p['category_tag'], p['category_label']],
        'descriptionHtml': clean_html(p['description_html']),
        'files': [{'originalSource': u} for u in p['images']],
        'productOptions': [{'name': 'Title', 'values': [{'name': 'Default Title'}]}],
        'variants': [variant],
        'metafields': metafields,
    }


batch = 5
for i in range(0, len(products), batch):
    chunk = products[i:i + batch]
    variables = {f'p{j}': to_input(p) for j, p in enumerate(chunk)}
    path = os.path.join(out_dir, f'batch-{i // batch + 1:02d}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(variables, f, ensure_ascii=False, separators=(',', ':'))
    print(path, len(chunk), os.path.getsize(path))
