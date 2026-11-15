"""Ghorer Poshak favicon: deep bottle-green rounded tile with a gold Bangla "ঘ".
Draws once at 1024px and downsamples, so small sizes stay crisp."""
import sys
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1]
GREEN = (31, 82, 64, 255)        # --rcb-maroon (primary) #1f5240
GREEN_DARK = (22, 61, 48, 255)   # #163d30
GOLD = (217, 181, 103, 255)      # light antique gold, readable on green at 16px
FONT = '/usr/share/fonts/truetype/noto/NotoSerifBengali-Bold.ttf'
S = 1024


def tile(ring):
    r = int(S * 0.22)
    # smooth vertical gradient (primary green → darker green), clipped to the rounded tile
    top = Image.new('RGBA', (S, S), GREEN)
    bottom = Image.new('RGBA', (S, S), GREEN_DARK)
    grad = Image.linear_gradient('L').resize((S, S))
    body = Image.composite(bottom, top, grad)
    mask = Image.new('L', (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=255)
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    img.paste(body, (0, 0), mask)
    d = ImageDraw.Draw(img)
    if ring:
        inset = int(S * 0.055)
        d.rounded_rectangle([inset, inset, S - 1 - inset, S - 1 - inset], radius=r - inset,
                            outline=GOLD, width=max(6, int(S * 0.018)))

    font = ImageFont.truetype(FONT, int(S * 0.70))
    text = 'ঘ'
    l, t, rgt, b = d.textbbox((0, 0), text, font=font)
    w, h = rgt - l, b - t
    x = (S - w) / 2 - l
    y = (S - h) / 2 - t + S * 0.01
    d.text((x, y), text, font=font, fill=GOLD)
    return img


big = tile(ring=True)     # 180px+ (home-screen / share): gold inner ring adds polish
small = tile(ring=False)  # browser-tab sizes: ring would blur, keep it bold

for size, src in [(16, small), (32, small), (48, small), (180, big), (192, big), (512, big)]:
    src.resize((size, size), Image.LANCZOS).save(f'{OUT}/gp-favicon-{size}.png', optimize=True)
small.resize((256, 256), Image.LANCZOS).save(f'{OUT}/gp-favicon-preview.png')
print('ok')
