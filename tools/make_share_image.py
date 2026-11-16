"""Ghorer Poshak social sharing image (1200x628) for Shopify Preferences → Social sharing image.
Brand colours from the theme: bottle green #1f5240 → #163d30, antique gold #d9b567, ivory text."""
import sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
W, H = 1200, 628
GREEN, GREEN_DARK = (31, 82, 64), (22, 61, 48)
GOLD, IVORY, MINT = (217, 181, 103), (250, 248, 243), (205, 224, 214)
SERIF_B = '/usr/share/fonts/truetype/noto/NotoSerifBengali-Bold.ttf'
SANS_B = '/usr/share/fonts/truetype/noto/NotoSansBengali-Bold.ttf'
SANS_M = '/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf'

top = Image.new('RGB', (W, H), GREEN)
bottom = Image.new('RGB', (W, H), GREEN_DARK)
img = Image.composite(bottom, top, Image.linear_gradient('L').rotate(90).resize((W, H)))
d = ImageDraw.Draw(img)

# thin gold inner frame
m = 28
d.rounded_rectangle([m, m, W - m, H - m], radius=22, outline=GOLD, width=3)

# monogram tile (same design as the favicon), left
tile = 250
tx, ty = 110, (H - tile) // 2
d.rounded_rectangle([tx, ty, tx + tile, ty + tile], radius=int(tile * 0.22), fill=GREEN_DARK, outline=GOLD, width=4)
f_mono = ImageFont.truetype(SERIF_B, int(tile * 0.68))
l, t, r, b = d.textbbox((0, 0), 'ঘ', font=f_mono)
d.text((tx + (tile - (r - l)) / 2 - l, ty + (tile - (b - t)) / 2 - t + 4), 'ঘ', font=f_mono, fill=GOLD)

# text block, right
x = tx + tile + 70
f_name = ImageFont.truetype(SERIF_B, 92)
f_latin = ImageFont.truetype('/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf', 32)  # Bangla fonts have no Latin glyphs
f_tag = ImageFont.truetype(SANS_B, 40)
f_small = ImageFont.truetype(SANS_M, 28)

y = 150
d.text((x, y), 'ঘরের পোশাক', font=f_name, fill=IVORY)
y += 130
gx = x
for ch in 'GHORER POSHAK':  # letter-spaced wordmark
    d.text((gx, y), ch, font=f_latin, fill=GOLD)
    gx += d.textlength(ch, font=f_latin) + 6
y += 62
d.line([x, y, x + 120, y], fill=GOLD, width=3)
y += 28
d.text((x, y), 'সাধ্যের মধ্যে স্বপ্নের সাজ', font=f_tag, fill=IVORY)
y += 66
cx = x
for i, word in enumerate(['শাড়ি', 'শার্ট', 'প্যান্ট', 'টি-শার্ট']):  # gold dot separators drawn, not typed
    if i:
        cy = y + 15
        d.ellipse([cx + 10, cy - 4, cx + 18, cy + 4], fill=GOLD)
        cx += 30
    d.text((cx, y), word, font=f_small, fill=MINT)
    cx += d.textlength(word, font=f_small)
y += 44
d.text((x, y), 'সারা বাংলাদেশে ক্যাশ অন ডেলিভারি', font=f_small, fill=MINT)

img.save(OUT, quality=92, optimize=True)
print('ok', OUT)
