"""Locate the old shop's "Ready Cart BD" text overlay in product photos.

Usage: find_brand_text.py <work.json> <out.json> <debug_dir>

work.json: {"A": [keys...], "paths": {key: image path}}
Runs tesseract on white-pixel masks of each photo (the overlay is pure white
text), then derives the full phrase box from whichever of the three words
were recognised. Writes {key: [x1, y1, x2, y2]} plus a debug crop per photo.
"""
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys

from PIL import Image, ImageChops, ImageDraw

work = json.load(open(sys.argv[1]))
out_path = sys.argv[2]
dbg = sys.argv[3]
os.makedirs(dbg, exist_ok=True)

# Offset and width of each word inside the phrase, in units of the phrase width.
REL = {'ready': (0.0, 0.415), 'cart': (0.477, 0.279), 'bd': (0.812, 0.188)}


def words(img_path):
    tsv = subprocess.run(['tesseract', img_path, '-', '--psm', '11', 'tsv'],
                         capture_output=True, text=True, timeout=300).stdout
    res = []
    for line in tsv.splitlines()[1:]:
        c = line.split('\t')
        if len(c) >= 12 and c[11].strip():
            res.append((c[11].strip(), int(c[6]), int(c[7]), int(c[8]), int(c[9])))
    return res


def phrase_boxes(ws):
    cands = []
    for t, x, y, w, h in ws:
        k = re.sub(r'[^a-z]', '', t.lower())
        if k == 'cartbd':
            pw = w / (1 - 0.477)
            cands.append((x - 0.477 * pw, y, pw, h))
        elif k in REL and 12 < h < 140:
            off, frac = REL[k]
            pw = w / frac
            cands.append((x - off * pw, y, pw, h))
    return cands


def locate(key):
    im = Image.open(work['paths'][key]).convert('RGB')
    r, g, b = im.split()
    mn = ImageChops.darker(ImageChops.darker(r, g), b)
    cands = []
    for thr in (225, 195):
        p = f'{dbg}/{key}_mask{thr}.png'
        mn.point(lambda v, t=thr: 0 if v > t else 255).save(p)
        cands += phrase_boxes(words(p))
    if not cands:
        return key, None, 0
    cands.sort(key=lambda c: c[1])
    mid = cands[len(cands) // 2]
    good = [c for c in cands if abs(c[1] - mid[1]) < 40 and abs(c[0] - mid[0]) < 90]
    x = min(c[0] for c in good)
    y = min(c[1] for c in good)
    x2 = max(c[0] + c[2] for c in good)
    y2 = max(c[1] + c[3] for c in good)
    box = [int(x), int(y), int(x2), int(y2)]
    pad = 70
    crop = im.crop((max(0, box[0] - pad), max(0, box[1] - pad),
                    min(im.width, box[2] + pad), min(im.height, box[3] + pad)))
    d = ImageDraw.Draw(crop)
    ox, oy = box[0] - max(0, box[0] - pad), box[1] - max(0, box[1] - pad)
    d.rectangle([ox, oy, ox + box[2] - box[0], oy + box[3] - box[1]], outline=(0, 255, 0))
    crop.save(f'{dbg}/{key}_box.png')
    return key, box, len(good)


result = {}
with cf.ThreadPoolExecutor(6) as ex:
    for key, box, n in ex.map(locate, work['A']):
        print(key, box, n, flush=True)
        if box:
            result[key] = box
json.dump(result, open(out_path, 'w'), indent=1)
