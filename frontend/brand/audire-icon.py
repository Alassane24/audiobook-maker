"""
Audire — app icon generator (Art Deco "Golden Age Broadcast").
Open book above a centered gold soundwave => "book becomes audio".

Run with the audiobook venv:
    A:/Cowork/audiobooks/.venv/Scripts/python.exe frontend/brand/audire-icon.py

Renders a 1024 master (saved here in brand/) then emits the PWA asset set
into frontend/public/ — served at the site root by FastAPI StaticFiles:
    apple-touch-icon.png (180)  icon-192.png  icon-512.png
    icon-512-maskable.png (Android adaptive, content in the safe zone)
    favicon.ico (16/32/48)
"""
import os, math
from PIL import Image, ImageDraw, ImageFilter

BRAND = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.normpath(os.path.join(BRAND, "..", "public"))
os.makedirs(PUBLIC, exist_ok=True)

FINAL = 1024
SS = 4
S = FINAL * SS

BG_BASE   = (0x0d, 0x1f, 0x17)
BG_EDGE   = (0x08, 0x16, 0x10)
RAISED    = (0x16, 0x32, 0x26)
GOLD      = (0xc8, 0xa2, 0x4a)
GOLD_HI   = (0xd9, 0xb7, 0x65)
CREAM     = (0xf2, 0xe8, 0xce)
DARK_GOLD = (0x14, 0x13, 0x0b)

def lerp(a, b, t): return a + (b - a) * t
def lerp_color(c1, c2, t): return tuple(int(round(lerp(c1[i], c2[i], t))) for i in range(3))

def radial_background(size):
    img = Image.new("RGB", (size, size), BG_BASE)
    px = img.load()
    cx = cy = size / 2.0
    maxd = math.hypot(cx, cy)
    center = lerp_color(BG_BASE, RAISED, 0.20)
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / maxd
            t = min(1.0, d ** 1.35)
            px[x, y] = lerp_color(center, BG_EDGE, t)
    return img

def add_glow(base, shape_img, color, blur, opacity):
    glow = Image.new("RGB", base.size, color)
    mask = shape_img.filter(ImageFilter.GaussianBlur(blur))
    if opacity < 1.0:
        mask = mask.point(lambda v: int(v * opacity))
    base.paste(glow, (0, 0), mask)
    return base

img = radial_background(S)
cx = cy = S / 2.0
safe = S * 0.82

# ---- deco frame ----
frame = ImageDraw.Draw(img, "RGBA")
off = S * 0.092
frame.rectangle([off, off, S - off, S - off], outline=GOLD + (60,), width=max(2, int(S * 0.0013)))

def l_bracket(d, ox, oy, sx, sy):
    arm = S * 0.085
    inset = S * 0.072
    w = max(3, int(S * 0.0052))
    x = ox + sx * inset
    y = oy + sy * inset
    d.line([(x, y), (x + sx * arm, y)], fill=GOLD_HI + (235,), width=w)
    d.line([(x, y), (x, y + sy * arm)], fill=GOLD_HI + (235,), width=w)

l_bracket(frame, 0, 0, +1, +1)
l_bracket(frame, S, 0, -1, +1)
l_bracket(frame, 0, S, +1, -1)
l_bracket(frame, S, S, -1, -1)

# ---- open book ----
book_cx = cx
book_cy = cy - S * 0.10
book_w  = safe * 0.70
book_h  = book_w * 0.50
half_w  = book_w / 2.0

spine_top = (book_cx, book_cy - book_h * 0.42)
spine_bot = (book_cx, book_cy + book_h * 0.56)
lift = book_h * 0.32
L_outer_top = (book_cx - half_w, book_cy - book_h * 0.16 - lift)
L_outer_bot = (book_cx - half_w, book_cy + book_h * 0.40)
left_page = [spine_top, L_outer_top, L_outer_bot, spine_bot]
R_outer_top = (book_cx + half_w, book_cy - book_h * 0.16 - lift)
R_outer_bot = (book_cx + half_w, book_cy + book_h * 0.40)
right_page = [spine_top, R_outer_top, R_outer_bot, spine_bot]

book_mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(book_mask).polygon(left_page, fill=255)
ImageDraw.Draw(book_mask).polygon(right_page, fill=255)
img = add_glow(img, book_mask, lerp_color(GOLD, BG_BASE, 0.32), blur=S * 0.022, opacity=0.55)

draw = ImageDraw.Draw(img, "RGBA")
draw.polygon(left_page,  fill=lerp_color(CREAM, GOLD_HI, 0.10))
draw.polygon(right_page, fill=lerp_color(CREAM, GOLD, 0.16))

spine_w = book_w * 0.014
draw.polygon([
    (book_cx - spine_w, spine_top[1] + book_h * 0.03),
    (book_cx + spine_w, spine_top[1] + book_h * 0.03),
    (book_cx + spine_w * 1.7, spine_bot[1]),
    (book_cx - spine_w * 1.7, spine_bot[1]),
], fill=lerp_color(DARK_GOLD, GOLD, 0.35) + (235,))

lw_page = max(4, int(S * 0.0072))
draw.line(left_page + [left_page[0]],   fill=GOLD, width=lw_page, joint="curve")
draw.line(right_page + [right_page[0]], fill=GOLD, width=lw_page, joint="curve")
draw.line([spine_top, L_outer_top], fill=GOLD_HI, width=max(3, int(S * 0.0044)))
draw.line([spine_top, R_outer_top], fill=GOLD_HI, width=max(3, int(S * 0.0044)))

def ruled(page_top_spine, page_top_outer, page_bot_outer, page_bot_spine):
    n = 3
    lc = lerp_color(GOLD, DARK_GOLD, 0.12)
    for i in range(n):
        t = 0.16 + i * 0.16
        sx = lerp(page_top_spine[0], page_bot_spine[0], t)
        sy = lerp(page_top_spine[1], page_bot_spine[1], t)
        ox = lerp(page_top_outer[0], page_bot_outer[0], t)
        oy = lerp(page_top_outer[1], page_bot_outer[1], t)
        ax = lerp(sx, ox, 0.16); ay = lerp(sy, oy, 0.16)
        bx = lerp(sx, ox, 0.88 - i * 0.05); by = lerp(sy, oy, 0.88 - i * 0.05)
        draw.line([(ax, ay), (bx, by)], fill=lc + (210,), width=max(3, int(S * 0.0066)))

ruled(spine_top, L_outer_top, L_outer_bot, spine_bot)
ruled(spine_top, R_outer_top, R_outer_bot, spine_bot)

# ---- soundwave ----
wave_cx = cx
wave_baseline = cy + S * 0.265
wave_span = safe * 0.72
n_bars = 9
gap_ratio = 0.34
slot_w = wave_span / n_bars
bar_w = slot_w * (1 - gap_ratio)
max_h = safe * 0.150
min_h = max_h * 0.30
heights = [0.40, 0.66, 0.52, 0.86, 1.00, 0.86, 0.52, 0.66, 0.40]

wave_mask = Image.new("L", (S, S), 0)
wm = ImageDraw.Draw(wave_mask)
bar_round = bar_w * 0.45
bars_geo = []
start_x = wave_cx - wave_span / 2.0 + slot_w / 2.0
for i in range(n_bars):
    bx = start_x + i * slot_w
    bh = min_h + (max_h - min_h) * heights[i]
    x0, x1 = bx - bar_w / 2.0, bx + bar_w / 2.0
    y1, y0 = wave_baseline, wave_baseline - bh
    bars_geo.append((x0, y0, x1, y1))
    wm.rounded_rectangle([x0, y0, x1, y1], radius=bar_round, fill=255)

img = add_glow(img, wave_mask, lerp_color(GOLD, BG_BASE, 0.28), blur=S * 0.015, opacity=0.50)

for (x0, y0, x1, y1) in bars_geo:
    w_px = max(1, int(round(x1 - x0))); h_px = max(1, int(round(y1 - y0)))
    strip = Image.new("RGB", (w_px, h_px)); sp = strip.load()
    for yy in range(h_px):
        t = yy / max(1, h_px - 1)
        col = lerp_color(GOLD_HI, GOLD, t)
        for xx in range(w_px):
            sp[xx, yy] = col
    m = Image.new("L", (w_px, h_px), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w_px - 1, h_px - 1], radius=max(1, int(bar_round)), fill=255)
    img.paste(strip, (int(round(x0)), int(round(y0))), m)

draw = ImageDraw.Draw(img, "RGBA")
base_lw = max(3, int(S * 0.0042))
bl_x0, bl_x1 = wave_cx - wave_span / 2.0, wave_cx + wave_span / 2.0
draw.line([(bl_x0, wave_baseline), (bl_x1, wave_baseline)], fill=GOLD_HI + (235,), width=base_lw)
cap_r = base_lw * 1.7
for ex in (bl_x0, bl_x1):
    draw.ellipse([ex - cap_r, wave_baseline - cap_r, ex + cap_r, wave_baseline + cap_r], fill=GOLD_HI)

bright = img.filter(ImageFilter.GaussianBlur(S * 0.010))
img = Image.blend(img, bright, 0.12)
master = img.resize((FINAL, FINAL), Image.LANCZOS).convert("RGB")

# ---- emit assets ----
master.save(os.path.join(BRAND, "audire-master-1024.png"), "PNG")

def out(name): return os.path.join(PUBLIC, name)

master.resize((512, 512), Image.LANCZOS).save(out("icon-512.png"), "PNG")
master.resize((192, 192), Image.LANCZOS).save(out("icon-192.png"), "PNG")
master.resize((180, 180), Image.LANCZOS).save(out("apple-touch-icon.png"), "PNG")

# Maskable: shrink content into the central safe zone on a flat emerald
# field (matched to the master's corner colour) so Android's adaptive mask
# never clips the book or wave.
corner = master.getpixel((3, 3))
mask_canvas = Image.new("RGB", (512, 512), corner)
scaled = master.resize((int(512 * 0.84), int(512 * 0.84)), Image.LANCZOS)
off = (512 - scaled.width) // 2
mask_canvas.paste(scaled, (off, off))
mask_canvas.save(out("icon-512-maskable.png"), "PNG")

master.save(out("favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])

print("master:", os.path.join(BRAND, "audire-master-1024.png"))
for n in ("apple-touch-icon.png", "icon-192.png", "icon-512.png", "icon-512-maskable.png", "favicon.ico"):
    p = out(n)
    print(f"  {n}: {os.path.getsize(p)} bytes")
