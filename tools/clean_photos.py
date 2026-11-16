"""Clean product photos that still carry the old shop's overlays.

Usage: clean_photos.py <work.json> <boxes.json> <out_dir>

Per photo, in this order:
  1. "Ready Cart BD" text (box from find_brand_text.py) is inpainted away and
     "Ghorer Poshak" is written in the same place and style.
  2. Price / promo stickers at the top are cropped off (TOP_CROP fractions,
     picked by eye per photo - the stickers show an outdated price).
  3. Black phone-screenshot bars and video-player strips are trimmed.
Output is always JPEG. Needs opencv-python-headless, numpy, pillow.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'
BRAND = 'Ghorer Poshak'

# Fraction of the height to cut from the top (sticker / promo text lives there).
TOP_CROP = {
    '17_1': .13, '17_2': .13, '17_3': .13, '18_1': .15, '18_2': .13,
    '19_1': .24, '19_2': .15, '19_3': .15, '19_4': .14,
    '20_1': .16, '20_2': .16, '20_3': .16, '21_1': .18, '21_2': .20,
    '22_1': .19, '23_1': .17, '39_2': .16, '39_3': .20, '42_1': .22,
}
# Fraction to cut from the bottom (video-player controls).
BOTTOM_CROP = {'39_2': .10}
# Photos where the brand text falls inside the cropped strip: no rewrite needed.
TEXT_CROPPED = {'19_1'}


def remove_text(img, box):
    """Inpaint the white overlay text inside box; returns (image, tight box)."""
    h_img, w_img = img.shape[:2]
    x1, y1, x2, y2 = box
    est_h = max(18, int((x2 - x1) * 0.13))
    padx, pady = int(est_h * 1.1), int(est_h * 0.5)
    rx1, ry1 = max(0, x1 - padx), max(0, y1 - pady)
    rx2, ry2 = min(w_img, x2 + padx), min(h_img, y2 + pady)
    roi = img[ry1:ry2, rx1:rx2]
    mn = roi.min(axis=2)
    mx = roi.max(axis=2)
    # The overlay is neutral white, clearly brighter than the fabric around it.
    # Compare each pixel with a wide median so shiny or pale fabric is not masked.
    k = (int(est_h * 1.6) | 1)
    bg = cv2.medianBlur(mn, min(k, 255))
    lift = mn.astype(np.int16) - bg.astype(np.int16)
    spread = mx.astype(np.int16) - mn.astype(np.int16)
    if est_h >= 30:
        text = (lift > 28) & (mn > 140) & ((spread < 30) | (mn > 228))
        core = cv2.morphologyEx(text.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    else:
        # Tiny captions are grey and colour-fringed after compression: go by brightness alone.
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        lift_g = gray.astype(np.int16) - cv2.medianBlur(gray, min(k, 255)).astype(np.int16)
        core = (lift_g > 20).astype(np.uint8) * 255
    ys, xs = np.nonzero(core)
    if len(xs) == 0:
        return img, box
    # Where to write the new name: the located box horizontally, the masked rows vertically.
    rows = np.nonzero(core.sum(axis=1) > core.sum(axis=1).max() * 0.25)[0]
    tight = [x1, ry1 + int(rows.min()), x2, ry1 + int(rows.max())]
    r = max(3, int(est_h * 0.2))
    mask = cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    filled = cv2.inpaint(roi, mask, r + 3, cv2.INPAINT_TELEA)
    # match the fabric grain so the patch does not look airbrushed
    blur = cv2.GaussianBlur(roi, (0, 0), 2.0)
    ring = cv2.dilate(mask, np.ones((4 * r + 1, 4 * r + 1), np.uint8)) & ~mask
    resid = roi.astype(np.float32) - blur.astype(np.float32)
    sigma = float(resid[ring > 0].std()) if (ring > 0).any() else 4.0
    rng = np.random.default_rng(7)
    noise = rng.normal(0, sigma * 0.8, roi.shape[:2]).astype(np.float32)[..., None]
    grain = np.clip(filled.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    soft = cv2.GaussianBlur(mask, (0, 0), 1.5).astype(np.float32)[..., None] / 255.0
    out = (grain * soft + roi * (1 - soft)).astype(np.uint8)
    img = img.copy()
    img[ry1:ry2, rx1:rx2] = out
    return img, tight


def write_brand(img, box):
    """Draw BRAND in white with a soft shadow, fitted to box width, centred on it."""
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).convert('RGBA')
    x1, y1, x2, y2 = box
    target_w = x2 - x1
    size = 10
    font = ImageFont.truetype(FONT, size)
    while font.getbbox(BRAND)[2] - font.getbbox(BRAND)[0] < target_w and size < 400:
        size += 1
        font = ImageFont.truetype(FONT, size)
    bx = font.getbbox(BRAND)
    tw, th = bx[2] - bx[0], bx[3] - bx[1]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ox, oy = int(cx - tw / 2 - bx[0]), int(cy - th / 2 - bx[1])
    shadow = Image.new('RGBA', pil.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((ox, oy + max(1, size // 22)), BRAND, font=font, fill=(0, 0, 0, 170),
                                stroke_width=max(1, size // 18), stroke_fill=(0, 0, 0, 170))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(1.0, size / 14)))
    pil = Image.alpha_composite(pil, shadow)
    ImageDraw.Draw(pil).text((ox, oy), BRAND, font=font, fill=(255, 255, 255, 255))
    return cv2.cvtColor(np.array(pil.convert('RGB')), cv2.COLOR_RGB2BGR)


def trim_bars(img):
    """Keep the tallest run of rows that are not flat black."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    content = (gray.mean(axis=1) > 14) & (gray.std(axis=1) > 4)
    best, start = (0, len(content)), None
    runs = []
    for i, c in enumerate(list(content) + [False]):
        if c and start is None:
            start = i
        elif not c and start is not None:
            runs.append((start, i))
            start = None
    if runs:
        best = max(runs, key=lambda r: r[1] - r[0])
    if best[1] - best[0] < len(content) * 0.5:
        return img
    return img[best[0]:best[1]]


def main():
    work = json.load(open(sys.argv[1]))
    boxes = json.load(open(sys.argv[2]))
    out_dir = sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    for key in work['A'] + work['B'] + work['C']:
        pil = Image.open(work['paths'][key])
        if pil.mode == 'RGBA':
            bg = Image.new('RGB', pil.size, 'white')
            bg.paste(pil, mask=pil.split()[3])
            pil = bg
        img = cv2.cvtColor(np.array(pil.convert('RGB')), cv2.COLOR_RGB2BGR)
        h = img.shape[0]
        if key in boxes and key not in TEXT_CROPPED:
            img, tight = remove_text(img, boxes[key])
            img = write_brand(img, tight)
        top = int(h * TOP_CROP.get(key, 0))
        bottom = h - int(h * BOTTOM_CROP.get(key, 0))
        img = trim_bars(img[top:bottom])
        out = f'{out_dir}/{key}.jpg'
        cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(key, pil.size, '->', (img.shape[1], img.shape[0]), flush=True)


if __name__ == '__main__':
    main()
